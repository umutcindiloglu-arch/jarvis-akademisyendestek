"""Gerçek zamanlı sesli çekirdek — OpenAI Realtime API (gpt-realtime).

Eski Whisper→gpt-4o→TTS hattının yerini alır. Tek bir WebSocket bağlantısı
üzerinden konuşma-konuşmaya (speech-to-speech) çalışır: mikrofon sesi anlık
gönderilir, model doğal sesiyle ('marin') anlık yanıt verir. Masaüstü araçları
(takvim, uygulama açma, ses/parlaklık, hafıza…) `core.TOOL_DISPATCH` üzerinden
aynen kullanılır.

Mimari
------
* Bağlantı: doğrudan `wss://api.openai.com/v1/realtime` (GA şekli — beta başlığı
  YOK). TLS doğrulaması için certifi CA paketi kullanılır (macOS Python aksi
  halde sertifika hatası verir).
* Uyandırma: açılışta uykuda; `turn_detection.create_response=false` ile model
  kendiliğinden konuşmaz, sadece konuşmayı yazıya döker. 'JARVIS wake up' (ya da
  metin kutusu) ile uyanınca create_response=true yapılır ve tam hızlı gerçek
  zamanlı sohbet başlar. 'uykuya geç' ile tekrar susar.
* Çift yönsüzlük (half-duplex): JARVIS konuşurken mikrofon beslenmez; böylece
  dizüstü hoparlöründen kendini duyup sözünü kesmez.
* Ses I/O: pyaudio, 24 kHz mono PCM16. Oynatma ayrı bir kuyruk/akış üzerinden.
"""

import asyncio
import base64
import datetime
import json
import queue
import ssl
import threading

import certifi
import pyaudio
import websockets

import core
import ui

MODEL = "gpt-realtime"
WS_URL = f"wss://api.openai.com/v1/realtime?model={MODEL}"
RATE = 24000
CHANNELS = 1
FORMAT = pyaudio.paInt16
FRAMES = 1200  # ~50 ms

# Uyandırma: isim + bir uyandırma fiili birlikte geçmeli.
_WAKE_NAMES = ("jarvis", "carvis", "jarvıs", "carvıs")
_WAKE_VERBS = ("wake", "veyk", "uyan", "kalk", "uyand")

GUNLER = {
    "Monday": "Pazartesi", "Tuesday": "Salı", "Wednesday": "Çarşamba",
    "Thursday": "Perşembe", "Friday": "Cuma", "Saturday": "Cumartesi",
    "Sunday": "Pazar",
}


# Sessizlik/gürültüde Whisper'ın sık ürettiği uydurma kalıplar — yanıtlanmaz.
_NOISE_PHRASES = (
    "altyazı", "abone ol", "iyi seyirler", "izlediğiniz için",
    "subscribe", "thanks for watching", "amara.org",
)


import re as _re

# Hata mesajlarında sızabilecek gizli değerleri maskeler: 'Bearer sk-...' başlığı
# ve serbest 'sk-...' anahtarları. HUD'a yazılan istisnaların API anahtarını
# açığa çıkarmasını engeller.
_SECRET_RE = _re.compile(r"(?i)\b(Bearer\s+)?sk-[A-Za-z0-9_\-]+")


def _scrub(err):
    return _SECRET_RE.sub("***", str(err))


def is_wake(low, names=_WAKE_NAMES):
    # Tek başına 'wake up' da uyandırır; uyandırma kelimesi + fiil de uyandırır.
    # `names` kullanıcı profilindeki uyandırma kelimesinden gelir (varsayılan jarvis).
    if "wake up" in low:
        return True
    return (any(n in low for n in names)
            and any(v in low for v in _WAKE_VERBS))


def wake_names_for(wake_word):
    """Profil uyandırma kelimesi -> eşleşecek varyantlar.

    Varsayılan 'jarvis' için sık karışan biçimleri de kabul ederiz; özel bir
    kelime seçildiyse yalnızca onu kullanırız.
    """
    w = (wake_word or "jarvis").strip().lower()
    return _WAKE_NAMES if w in _WAKE_NAMES else (w,)


def is_sleep(low):
    # "uykuya geç", "uyku moduna geç", "uyku modu"
    if "uyku" in low and ("geç" in low or "mod" in low):
        return True
    # "uyuyabilirsin", "jarvis uyuyabilirsin"
    if "uyuyabilir" in low:
        return True
    # "jarvis uyu", "uyu jarvis"
    return "jarvis" in low and "uyu" in low


# Katılımcılara selam: bu kalıplar geçince küre 'yüz' olup el sallar.
_GREET_PHRASES = (
    "katılımcı", "el salla", "selam ver", "selamla",
    "herkese merhaba", "herkese selam", "izleyicilere",
)


def is_greet(low):
    return any(p in low for p in _GREET_PHRASES)


def _meaningful(low):
    """Gürültü/yankı transkriptlerini ele: en az iki harf/rakam ve uydurma değil."""
    if _is_noise(low):
        return False
    return sum(c.isalnum() for c in low) >= 2


def _is_noise(low):
    return any(p in low for p in _NOISE_PHRASES)


def now_str():
    now = datetime.datetime.now()
    gun = GUNLER.get(now.strftime("%A"), "")
    return now.strftime(f"%d.%m.%Y %H:%M, {gun}")


def _flat_tools():
    """core.TOOLS (chat formatı) → Realtime'ın düz araç şeması."""
    out = []
    for t in core.TOOLS:
        f = t["function"]
        out.append({
            "type": "function",
            "name": f["name"],
            "description": f.get("description", ""),
            "parameters": f.get("parameters", {"type": "object", "properties": {}}),
        })
    return out


class RealtimeClient:
    def __init__(self, hud, keys, profile):
        self.hud = hud
        self.keys = keys
        self.profile = profile
        self._wake_names = wake_names_for(profile.get("uyandirma_kelimesi", "jarvis"))
        self._hitap = profile.get("hitap", "hocam")
        self.awake = False
        self.speaking = False
        self.ws = None
        self._assistant_buf = ""

        self.pa = pyaudio.PyAudio()
        self.out_stream = None
        self.play_queue = None  # asyncio.Queue, olay döngüsünde kurulur
        self._ssl = ssl.create_default_context(cafile=certifi.where())

    # --- Giriş noktası (worker thread) -------------------------------------

    def run(self):
        try:
            asyncio.run(self._main())
        except Exception as e:
            self.hud.set_state("error")
            self.hud.add_message("SİSTEM", f"Realtime bağlanamadı: {_scrub(e)}", ui.RED)

    def stop(self):
        """Kapanırken çalan sesi anında kes."""
        s = self.out_stream
        if s is not None:
            try:
                s.stop_stream()
            except Exception:
                pass

    # --- Ana akış -----------------------------------------------------------

    async def _main(self):
        self.play_queue = asyncio.Queue()
        headers = {"Authorization": f"Bearer {self.keys['openai_api_key']}"}
        async with websockets.connect(
            WS_URL, additional_headers=headers, ssl=self._ssl, max_size=None
        ) as ws:
            self.ws = ws
            await self._configure_session()
            self.hud.set_state("sleeping")  # açılışta sessiz, uyandırma bekler

            tasks = [
                asyncio.create_task(self._mic_loop()),
                asyncio.create_task(self._player_loop()),
                asyncio.create_task(self._typed_loop()),
            ]
            try:
                await self._receive_loop()
            finally:
                for t in tasks:
                    t.cancel()
                self._cleanup_audio()

    async def _configure_session(self):
        instructions = (
            core.build_system_prompt(self.profile, now_str())
            + " Gerçek zamanlı sesli konuşuyorsun; çok kısa, hızlı ve doğal yanıt ver."
        )
        session = {
            "type": "realtime",
            "instructions": instructions,
            "audio": {
                "input": {
                    "format": {"type": "audio/pcm", "rate": RATE},
                    # Dil 'tr' kilitli: aksi halde Whisper sessizlik/gürültüde
                    # uydurma (halüsinasyon) üretir ve bazen yanlış dilde duyar.
                    "transcription": {"model": "whisper-1", "language": "tr"},
                    "noise_reduction": {"type": "far_field"},
                    "turn_detection": self._turn_detection(),
                },
                "output": {
                    "format": {"type": "audio/pcm", "rate": RATE},
                    "voice": self.keys.get("tts_voice", "marin"),
                },
            },
            "output_modalities": ["audio"],
            "tools": _flat_tools(),
            "tool_choice": "auto",
        }
        await self._send({"type": "session.update", "session": session})

    def _turn_detection(self):
        # create_response KAPALI: sunucu kendiliğinden yanıt üretmez. Yanıtı biz
        # yalnızca anlamlı bir kullanıcı transkripti gelince tetikleriz; böylece
        # sessizlik/gürültü/yankı JARVIS'i kendi kendine konuşturmaz. Eşik biraz
        # yüksek tutulur ki ortam gürültüsü turu tetiklemesin. (Barge-in kapalı:
        # JARVIS konuşurken mikrofon beslenmediğinden sözü kesilmez.)
        return {
            "type": "server_vad",
            "threshold": 0.65,
            "prefix_padding_ms": 300,
            "silence_duration_ms": 450,
            "create_response": False,
        }

    async def _set_awake(self, val):
        # Yanıt üretimi artık tamamen istemci tarafında kapılandığı için
        # uyandırma/uyku yalnızca bu bayrağı değiştirir; session güncellemesi
        # gerekmez.
        self.awake = val

    async def _send(self, obj):
        await self.ws.send(json.dumps(obj))

    # --- Ses giriş/çıkış ----------------------------------------------------

    async def _mic_loop(self):
        stream = self.pa.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                              input=True, frames_per_buffer=FRAMES)
        try:
            while not self.hud.should_quit:
                data = await asyncio.to_thread(
                    stream.read, FRAMES, exception_on_overflow=False
                )
                # JARVIS konuşurken / duraklatılmışken mikrofonu besleme
                # (hoparlör yankısını "konuşma" sanıp kendini kesmesin).
                if self.speaking or self.hud.paused:
                    continue
                b64 = base64.b64encode(data).decode("ascii")
                await self._send({"type": "input_audio_buffer.append", "audio": b64})
        except (asyncio.CancelledError, Exception):
            pass
        finally:
            try:
                stream.stop_stream(); stream.close()
            except Exception:
                pass

    async def _player_loop(self):
        stream = self.pa.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True)
        self.out_stream = stream
        try:
            while not self.hud.should_quit:
                chunk = await self.play_queue.get()
                if chunk:
                    await asyncio.to_thread(stream.write, chunk)
        except (asyncio.CancelledError, Exception):
            pass
        finally:
            try:
                stream.stop_stream(); stream.close()
            except Exception:
                pass

    def _cleanup_audio(self):
        try:
            self.pa.terminate()
        except Exception:
            pass

    # --- Yazılı komutlar ----------------------------------------------------

    async def _typed_loop(self):
        while not self.hud.should_quit:
            try:
                txt = self.hud.text_queue.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.15)
                continue
            await self._set_awake(True)  # yazı yazmak doğrudan uyandırır
            self.hud.add_message("SİZ", txt, ui.GREEN)
            await self._send({
                "type": "conversation.item.create",
                "item": {"type": "message", "role": "user",
                         "content": [{"type": "input_text", "text": txt}]},
            })
            await self._send({"type": "response.create"})

    # --- Olay döngüsü -------------------------------------------------------

    async def _receive_loop(self):
        async for raw in self.ws:
            if self.hud.should_quit:
                break
            await self._handle(json.loads(raw))

    async def _handle(self, ev):
        t = ev.get("type", "")

        if t == "response.output_audio.delta":
            b = ev.get("delta")
            if b:
                self.speaking = True
                self.hud.set_state("speaking")
                await self.play_queue.put(base64.b64decode(b))

        elif t == "response.output_audio_transcript.delta":
            self._assistant_buf += ev.get("delta", "")

        elif t == "response.output_audio_transcript.done":
            text = (ev.get("transcript") or self._assistant_buf).strip()
            if text:
                self.hud.add_message("JARVIS", text, ui.CYAN)
            self._assistant_buf = ""

        elif t == "conversation.item.input_audio_transcription.completed":
            await self._on_user_text((ev.get("transcript") or "").strip())

        elif t == "input_audio_buffer.speech_started":
            if self.awake and not self.speaking:
                self.hud.set_state("listening")

        elif t == "response.function_call_arguments.done":
            await self._on_tool_call(ev)

        elif t == "response.done":
            asyncio.create_task(self._after_response())

        elif t == "error":
            err = ev.get("error", {})
            self.hud.add_message("SİSTEM", f"Realtime: {err.get('message', '?')}", ui.AMBER)

    async def _on_user_text(self, text):
        if not text:
            return
        low = text.lower()

        if not self.awake:
            if is_wake(low, self._wake_names):
                await self._set_awake(True)
                self.hud.add_message("SİZ", text, ui.GREEN)
                await self._send({
                    "type": "response.create",
                    "response": {"instructions": f"Çok kısa selam ver: Buradayım {self._hitap}."},
                })
            return  # uykudayken uyandırma dışındaki her şeyi yok say

        # --- Uyanık ---
        if is_sleep(low):
            self.hud.add_message("SİZ", text, ui.GREEN)
            await self._set_awake(False)
            self.hud.set_state("sleeping")
            return

        # JARVIS konuşurken gelen transkript büyük ihtimalle kendi yankısı: yok say.
        if self.speaking:
            return
        # Boş/gürültü/halüsinasyon turuna yanıt verme (kendi kendine konuşmayı önler).
        if not _meaningful(low):
            return

        # Gerçek bir kullanıcı turu: yanıtı biz tetikleriz.
        self.hud.add_message("SİZ", text, ui.GREEN)
        # Katılımcılara selam istendiyse küre 'yüz' olup el sallar (sesli yanıt da gelir).
        if is_greet(low):
            self.hud.wave()
        await self._send({"type": "response.create"})

    async def _on_tool_call(self, ev):
        self.hud.set_state("thinking")
        result = await asyncio.to_thread(
            self._run_tool, ev.get("name", ""), ev.get("arguments", "")
        )
        await self._send({
            "type": "conversation.item.create",
            "item": {"type": "function_call_output",
                     "call_id": ev.get("call_id"), "output": result},
        })
        await self._send({"type": "response.create"})

    def _run_tool(self, name, arguments_json):
        fn = core.TOOL_DISPATCH.get(name)
        if fn is None:
            return f"Bilinmeyen araç: {name}"
        try:
            args = json.loads(arguments_json) if arguments_json else {}
        except json.JSONDecodeError:
            args = {}
        try:
            return str(fn(**args))
        except Exception as e:
            return f"'{name}' çalışırken hata: {e}"

    async def _after_response(self):
        # Oynatma kuyruğu boşalana dek bekle, sonra hoparlör tamponu da boşalsın
        # diye biraz daha bekle; erken açılan mikrofon sesin kuyruğunu yankı
        # olarak yakalayıp yeni bir tur tetikleyebilir.
        while self.play_queue is not None and not self.play_queue.empty():
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.4)
        self.speaking = False
        self.hud.set_state("listening" if self.awake else "sleeping")
