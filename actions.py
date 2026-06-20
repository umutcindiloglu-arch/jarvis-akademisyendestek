"""Eller — JARVIS'in masaüstünde yaptığı somut işler.

Her fonksiyon tek bir işi yapar ve modelin geri besleme olarak okuyabileceği
kısa Türkçe bir sonuç metni döndürür. Hatalar yakalanır; uygulama çökmez.

macOS entegrasyonları `osascript` (AppleScript) ve birkaç sistem komutu
üzerinden yapılır. Web araması harici servis gerektirmeden DuckDuckGo'nun
HTML uç noktasından okunur.
"""

import html
import re
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path


def _ensure_running(app_name, wait=1.5):
    """Bir uygulamayı arka planda başlatır (osascript -600 hatasını önler)."""
    already = subprocess.run(["pgrep", "-x", app_name], capture_output=True).returncode == 0
    subprocess.run(["open", "-a", app_name])
    if not already:
        time.sleep(wait)


def _osascript(script):
    """Bir AppleScript'i çalıştırır, stdout'u döndürür (hata olursa Exception)."""
    proc = subprocess.run(
        ["osascript", "-"],
        input=script,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "AppleScript hatası")
    return proc.stdout.strip()


def _q(s):
    """AppleScript metin sabiti için güvenli kaçış (önce ters bölü, sonra tırnak).

    Enjeksiyonu engeller: kaçışsız bir tırnak/ters bölü, modele iletilen metinle
    AppleScript'ten çıkıp 'do shell script' gibi komutlar çalıştırabilirdi.
    """
    return str(s).replace("\\", "\\\\").replace('"', '\\"')


# --- Uygulama / dosya / web açma --------------------------------------------

def open_app(name):
    name = (name or "").strip()
    # Uygulama adları kısadır; aşırı uzun/satır içeren girdileri reddet.
    if not name or len(name) > 80 or any(c in name for c in "\n\r\t"):
        return "Geçersiz uygulama adı."
    try:
        subprocess.run(["open", "-a", name], check=True, capture_output=True, text=True)
        return f"{name} açıldı."
    except subprocess.CalledProcessError:
        return f"'{name}' adlı uygulamayı bulamadım. Adı tam yazdığından emin ol."


# Yalnızca bu klasörlerin altındaki dosyalar açılabilir (ev dizinine göre).
_ALLOWED_OPEN_DIRS = ("Desktop", "Documents", "Downloads")
# Açılınca kod çalıştırabilecek tehlikeli uzantı/paketler — engellenir.
_BLOCKED_OPEN_SUFFIXES = {
    ".app", ".command", ".sh", ".bash", ".zsh", ".scpt", ".applescript",
    ".command", ".tool", ".terminal", ".workflow", ".action", ".pkg", ".mpkg",
    ".dmg", ".jar", ".py", ".rb", ".pl", ".php", ".js", ".osascript",
    ".scptd", ".prefpane", ".plugin", ".kext",
}


def open_path(path):
    """Yalnızca ev dizinindeki Desktop/Documents/Downloads içindeki dosyaları açar.

    Model tarafından (ör. okunan bir mailden gelen metinle) çağrılabildiği için
    yol, gerçek konumuna çözülüp bu güvenli klasörlerle sınırlanır; açılınca kod
    çalıştırabilecek uzantılar (.app, .sh, .command…) reddedilir.
    """
    home = Path.home().resolve()
    try:
        p = Path(path).expanduser().resolve()
    except (OSError, RuntimeError):
        return f"'{path}' yolunu çözemedim."

    allowed_roots = [home / d for d in _ALLOWED_OPEN_DIRS]
    if not any(p == root or root in p.parents for root in allowed_roots):
        return ("Güvenlik nedeniyle yalnızca Masaüstü, Belgeler ve İndirilenler "
                "klasörlerindeki dosyaları açabilirim.")
    if p.suffix.lower() in _BLOCKED_OPEN_SUFFIXES:
        return f"Güvenlik nedeniyle '{p.name}' türündeki dosyaları açmıyorum."
    if not p.exists():
        return f"'{path}' bulunamadı."
    if p.is_symlink():
        return f"Güvenlik nedeniyle sembolik bağlantıları açmıyorum: '{p.name}'."
    subprocess.run(["open", str(p)])
    return f"{p.name} açıldı."


def open_url(url):
    """Yalnızca http/https adreslerini tarayıcıda açar.

    Şema beyaz listesi 'file:', 'javascript:', özel uygulama şemaları gibi
    istismar edilebilir bağlantıları engeller (model/komut enjeksiyonu savunması).
    """
    url = (url or "").strip()
    if not re.match(r"^https?://", url, re.IGNORECASE):
        # Şema yoksa güvenli varsayılan olarak https ekle; başka şema varsa reddet.
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:", url):
            return "Güvenlik nedeniyle yalnızca http ve https bağlantılarını açabilirim."
        url = "https://" + url
    subprocess.run(["open", url])
    return f"{url} tarayıcıda açıldı."


# --- Sistem kontrolü --------------------------------------------------------

def set_volume(level):
    level = max(0, min(100, int(level)))
    _osascript(f"set volume output volume {level}")
    return f"Ses %{level} yapıldı."


def get_volume():
    out = _osascript("output volume of (get volume settings)")
    return f"Ses seviyesi %{out}."


def set_brightness(level):
    """0-100 arası parlaklık. 'brightness' CLI aracı kuruluysa kullanır."""
    level = max(0, min(100, int(level)))
    if subprocess.run(["which", "brightness"], capture_output=True).returncode == 0:
        subprocess.run(["brightness", str(level / 100.0)])
        return f"Ekran parlaklığı %{level} yapıldı."
    return ("Parlaklık ayarı için 'brightness' aracı kurulu değil. "
            "İstersen 'brew install brightness' ile kurabilirim.")


def take_screenshot(path=None):
    if path is None:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = str(Path.home() / "Desktop" / f"ekran-{ts}.png")
    subprocess.run(["screencapture", "-x", path])
    return f"Ekran görüntüsü masaüstüne kaydedildi: {Path(path).name}"


def take_note(text):
    text = (text or "")[:5000]  # aşırı uzun girdileri kırp
    _osascript(f'''
tell application "Notes"
    tell account "iCloud"
        make new note at folder "Notes" with properties {{body:"{_q(text)}"}}
    end tell
end tell''')
    return "Not, Notlar uygulamasına kaydedildi."


# --- Müzik (Spotify) --------------------------------------------------------

def play_spotify_track(uri, label=""):
    """Spotify'da belirli bir parçayı çalar.

    `uri` tam bir 'spotify:track:<ID>' olmalı; macOS Spotify AppleScript'i ada
    göre arayıp çalamaz, yalnızca kesin URI ile parça oynatır.
    """
    if not re.match(r"^spotify:track:[A-Za-z0-9]+$", uri or ""):
        return f"Geçersiz Spotify parça kimliği: '{uri}'."
    _ensure_running("Spotify", wait=3.0)
    try:
        _osascript(f'tell application "Spotify" to play track "{_q(uri)}"')
    except RuntimeError as e:
        return f"Spotify'da çalamadım: {e}"
    return f"{label or 'Parça'} Spotify'da çalıyor."


# --- Takvim -----------------------------------------------------------------

def _applescript_date(dt):
    """Python datetime'ı AppleScript date değişkenine çeviren kod parçası."""
    return f'''
    set d to current date
    set year of d to {dt.year}
    set month of d to {dt.month}
    set day of d to {dt.day}
    set hours of d to {dt.hour}
    set minutes of d to {dt.minute}
    set seconds of d to 0'''


def add_calendar_event(title, start, end=None, notes=""):
    """Takvime etkinlik ekler. start/end ISO formatında: '2026-06-20T15:00'."""
    try:
        start_dt = datetime.fromisoformat(start)
    except ValueError:
        return f"Başlangıç zamanını anlayamadım: '{start}'. Örn: 2026-06-20T15:00"
    end_dt = datetime.fromisoformat(end) if end else start_dt + timedelta(hours=1)

    _ensure_running("Calendar")
    script = f'''
tell application "Calendar"
    {_applescript_date(start_dt)}
    set startDate to d
    {_applescript_date(end_dt)}
    set endDate to d
    tell calendar 1
        make new event with properties {{summary:"{_q(title)}", start date:startDate, end date:endDate, description:"{_q(notes)}"}}
    end tell
end tell'''
    try:
        _osascript(script)
    except RuntimeError as e:
        return f"Takvime ekleyemedim: {e}"
    when = start_dt.strftime("%d.%m.%Y %H:%M")
    return f"'{title}' etkinliği {when} için takvime eklendi."


def list_calendar_events(date=None):
    """Belirtilen günün (varsayılan bugün) etkinliklerini listeler."""
    day = datetime.fromisoformat(date) if date else datetime.now()
    _ensure_running("Calendar")
    script = f'''
tell application "Calendar"
    {_applescript_date(day.replace(hour=0, minute=0))}
    set dayStart to d
    set dayEnd to dayStart + (1 * days)
    set outText to ""
    repeat with c in calendars
        set theEvents to (every event of c whose start date is greater than or equal to dayStart and start date is less than dayEnd)
        repeat with e in theEvents
            set ev to contents of e
            set sd to start date of ev
            set outText to outText & (summary of ev) & " @ " & (time string of sd) & linefeed
        end repeat
    end repeat
    return outText
end tell'''
    try:
        out = _osascript(script)
    except RuntimeError as e:
        return f"Takvimi okuyamadım: {e}"
    out = out.strip()
    if not out:
        return f"{day.strftime('%d.%m.%Y')} için takvimde etkinlik yok."
    return f"{day.strftime('%d.%m.%Y')} etkinlikleri:\n{out}"


# --- Mail (yalnızca okuma) --------------------------------------------------

def list_unread_mail(limit=10):
    """Mail.app gelen kutusundaki okunmamış e-postaları (gönderen + konu) verir.

    Yalnızca okur; mail göndermez. Çok sayıda okunmamış mailde yavaşlamamak için
    liste baştan `limit` adetle kırpılır.
    """
    limit = max(1, min(50, int(limit)))
    _ensure_running("Mail")
    # 'whose read status is false' tüm kutuyu tarayıp zaman aşımına (-1712) yol
    # açıyor. Hızlı 'unread count' ile sayıyı al; sadece en yeni mailleri tarayıp
    # okunmamışları topla (okunmamış mail genelde en üsttedir).
    script = f'''
with timeout of 90 seconds
    tell application "Mail"
        set total to unread count of inbox
        if total is 0 then return "0|"
        set msgCount to count of messages of inbox
        set scanMax to 60
        if msgCount < scanMax then set scanMax to msgCount
        set outText to ""
        set shown to 0
        repeat with i from 1 to scanMax
            set m to message i of inbox
            if read status of m is false then
                set outText to outText & (sender of m) & " — " & (subject of m) & linefeed
                set shown to shown + 1
                if shown is greater than or equal to {limit} then exit repeat
            end if
        end repeat
        return (total as text) & "|" & outText
    end tell
end timeout'''
    try:
        out = _osascript(script)
    except RuntimeError as e:
        return f"Mail'i okuyamadım: {e}"
    total_str, _, body = out.partition("|")
    body = body.strip()
    try:
        total = int(total_str)
    except ValueError:
        total = 0
    if total == 0 or not body:
        return "Okunmamış mail yok."
    shown = min(total, limit)
    return f"{total} okunmamış mail var. İlk {shown}:\n{body}"


# --- Web araması ------------------------------------------------------------

def web_search(query, max_results=5):
    """DuckDuckGo HTML uç noktasından kısa sonuç parçaları çeker."""
    import requests

    query = (query or "").strip()[:500]  # aşırı uzun sorguları kırp
    if not query:
        return "Arama için bir ifade ver."
    max_results = max(1, min(10, int(max_results)))

    url = "https://html.duckduckgo.com/html/"
    try:
        resp = requests.post(
            url,
            data={"q": query},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        return f"Web aramasında sorun oldu: {e}"

    snippets = re.findall(
        r'class="result__snippet"[^>]*>(.*?)</a>', resp.text, re.S
    )
    results = []
    for s in snippets[:max_results]:
        clean = html.unescape(re.sub(r"<[^>]+>", "", s)).strip()
        if clean:
            results.append("• " + clean)
    if not results:
        return f"'{query}' için sonuç bulamadım."
    return f"'{query}' için bulduklarım:\n" + "\n".join(results)
