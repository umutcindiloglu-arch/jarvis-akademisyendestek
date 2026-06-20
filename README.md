# JARVIS — Akademisyen Destek Sürümü

Herkesin kurup kişiselleştirebileceği, gerçek zamanlı sesli, sinematik bir
macOS masaüstü asistanı. İlk açılışta size birkaç soru sorar (size nasıl hitap
etsin, hangi kelimeyle uyansın, hangi şehrin havasını göstersin…), cevaplarınıza
göre kendini ayarlar ve masaüstünüzde işler yapar.

> Bu sürüm kişisel bilgi içermez. Tüm kişiselleştirme, ilk açılıştaki **kurulum
> sihirbazı** ile sizin girdiğiniz değerlerden oluşur ve yalnızca kendi
> bilgisayarınızdaki `config/` klasöründe saklanır.

## Özellikler

- 🎙️ **Gerçek zamanlı sesli konuşma** — OpenAI Realtime API ile konuşma-konuşmaya, anlık ve doğal yanıt.
- 🧙 **Kurulum sihirbazı** — ilk açılışta API anahtarı + kişiselleştirme sorar; sonradan `--setup` ile değiştirilebilir.
- 😴 **Uyandırma sözü** — açılışta sessiz bekler; sizin belirlediğiniz kelimeyle (ör. "jarvis uyan") uyanır, "uykuya geç" deyince susar.
- 🧠 **Araç çağırma** — çok adımlı işleri kendi planlar; adına yanıt verir, sizi zamanla öğrenir (hafıza).
- 🖥️ **Masaüstü kontrolü** — uygulama/dosya/web açma, ses & parlaklık, ekran görüntüsü, not alma.
- 📅 **Takvim planlama** — macOS Takvim'e etkinlik ekler, gününüzü okur.
- 📬 **Mail okuma** — Mail uygulamasındaki okunmamış e-postaları özetler (yalnızca okur, göndermez).
- 🎵 **Müzik** — Spotify'da istediğiniz parçayı çalar.
- 🎓 **Anlatım modu** — "bu konuyu katılımcılara anlat" dendiğinde kısalık kuralını bırakıp "Değerli katılımcılar, bu konu…" diye başlayan bir mini ders verir (sunum/eğitim modu).
- 👋 **Katılımcılara selam** — "katılımcılara selam ver" / "el salla" dendiğinde küre geçici olarak gülen bir yüze dönüşüp el sallar.
- 🔎 **Web araması** — internette arar ve özetler.
- 🕒 **Canlı HUD** — dijital saat, şehrinizin hava durumu ve CPU/RAM/GPU kullanım barları.

## Gereksinimler

- macOS (Apple Silicon veya Intel)
- Python 3.10+
- Bir OpenAI API anahtarı — [platform.openai.com/api-keys](https://platform.openai.com/api-keys)

## Kurulum

```bash
git clone https://github.com/umutcindiloglu-arch/jarvis-akademisyendestek.git
cd jarvis-akademisyendestek
python3 -m venv venv
./venv/bin/python -m pip install -r requirements.txt
```

## Çalıştırma

```bash
./venv/bin/python main.py
```

İlk açılışta **kurulum sihirbazı** çıkar. Şunları sorar:

| Soru | Örnek |
|------|-------|
| OpenAI API anahtarı | `sk-...` |
| Adınız | Ahmet |
| JARVIS size nasıl hitap etsin? | hocam / Ahmet Bey / kaptan |
| Mesleğiniz / alanınız | akademisyen |
| Asistanın adı | JARVIS |
| Uyandırma kelimesi | jarvis / athena |
| Şehir (hava durumu) | İstanbul |
| Ses tonu | marin / cedar / alloy … |

Cevaplar yalnızca yerelde `config/api_keys.json` ve `config/profile.json`
içinde saklanır; bu dosyalar `.gitignore` ile korunur, **asla** depoya gönderilmez.

Ayarları sonradan değiştirmek için:

```bash
./venv/bin/python main.py --setup
```

İlk açılışta macOS **Mikrofon** iznini ister — izin verin.

## Kullanım

- Uyandırmak için: **"<uyandırma kelimesi> uyan"** (ör. "jarvis uyan") ya da "wake up".
- Uyutmak için: "uykuya geç" / "uyu".
- Kapatmak için: "görüşürüz", HUD'daki **SHUTDOWN** ya da `Esc`.

## Dosya yapısı

| Dosya | Görevi |
|-------|--------|
| `main.py` | Kurulum sihirbazını ve HUD'u başlatır |
| `realtime.py` | Gerçek zamanlı sesli çekirdek (OpenAI Realtime, WebSocket) |
| `core.py` | Kişilik (sistem istemi) ve araç tanımları/yönlendirmesi |
| `actions.py` | Masaüstü eylemleri (uygulama, takvim, sistem, web) |
| `ui.py` | Sinematik HUD + kurulum sihirbazı |
| `store.py` | Ayar ve profil deposu |
| `weather.py` | Hava durumu + şehir → koordinat çözümü (Open-Meteo) |
| `sysinfo.py` | CPU/RAM/GPU ölçümleri |
| `memory.py` | Kalıcı hafıza |
| `config/` | API anahtarı ve kişisel profil (gizli, gitignore) |

## Güvenlik

`config/api_keys.json`, `config/profile.json` ve `config/memory.json` `.gitignore`
ile korunur ve depoya gönderilmez. Yalnızca `*.example.json` şablonları paylaşılır.
API anahtarınız ve kişisel bilgileriniz hiçbir zaman depoya çıkmaz.

## Testler

Ağ ve macOS izni gerektirmeyen çevrimdışı testler:

```bash
./venv/bin/python test_smoke.py
```

## Lisans

MIT
