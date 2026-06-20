# JARVIS Kurulum ve Kullanım Rehberi (macOS)

Bu belge, projeyi **ilk kez kuran** birinin hiçbir adımı atlamadan, baştan sona
çalışan bir JARVIS elde etmesi için hazırlandı. Sırasıyla takip edin.

> 🪟 **Windows kullanıyorsanız** bu sürüm değil, Windows'a özel sürümü kurun:
> **[jarvis-akademisyendestek-for-Microsoft](https://github.com/umutcindiloglu-arch/jarvis-akademisyendestek-for-Microsoft)**

İçindekiler:

1. [JARVIS nedir?](#1-jarvis-nedir)
2. [Ön gereksinimler](#2-ön-gereksinimler)
3. [OpenAI API anahtarı alma](#3-openai-api-anahtarı-alma)
4. [Kurulum adımları](#4-kurulum-adımları)
5. [İlk açılış: kurulum sihirbazı](#5-i̇lk-açılış-kurulum-sihirbazı)
6. [macOS izinleri (önemli)](#6-macos-i̇zinleri-önemli)
7. [Kullanım](#7-kullanım)
8. [İsteğe bağlı ek özellikler](#8-i̇steğe-bağlı-ek-özellikler)
9. [Sorun giderme](#9-sorun-giderme)
10. [Gizlilik ve güvenlik](#10-gizlilik-ve-güvenlik)

---

## 1. JARVIS nedir?

JARVIS, macOS için gerçek zamanlı **sesli** bir masaüstü asistanıdır. Sinematik
bir tam ekran arayüz (HUD) açar; sizi adınızla tanır, belirlediğiniz uyandırma
kelimesiyle uyanır, OpenAI Realtime API üzerinden konuşma-konuşmaya sohbet eder
ve masaüstünüzde gerçek işler yapar: uygulama açma, takvim planlama, mail okuma,
müzik çalma, web araması, not alma ve daha fazlası.

Projede **hiçbir kişisel bilgi gömülü değildir.** Tüm kişiselleştirme, ilk
açılışta çıkan kurulum sihirbazına sizin girdiğiniz değerlerden oluşur ve
yalnızca kendi bilgisayarınızda saklanır.

**Nasıl çalışır (kısaca):** Mikrofonunuz sesi yakalar → OpenAI Realtime API sesi
hem yazıya döker hem de yanıtı yine sesli üretir → asistan gerekirse bir "araç"
(takvim, mail, uygulama açma…) çağırır → sonucu tek cümleyle onaylar.

---

## 2. Ön gereksinimler

| Gereksinim | Açıklama |
|------------|----------|
| **macOS** | Apple Silicon (M1/M2/M3…) veya Intel |
| **Python 3.10+** | `python3 --version` ile kontrol edin |
| **Homebrew** | Ses kütüphanesi için gerekli — [brew.sh](https://brew.sh) |
| **OpenAI API anahtarı** | Ücretli; Realtime API kredisi gerekir (bkz. Bölüm 3) |
| **Mikrofon** | Dahili veya harici |
| **İnternet** | Realtime API ve hava durumu için |

Homebrew kurulu değilse:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Ses girişi için **PortAudio** şarttır (Python'un `pyaudio` paketi buna bağlıdır):

```bash
brew install portaudio
```

> ⚠️ Bu adımı atlarsanız `pip install pyaudio` derleme hatasıyla başarısız olur.
> En sık karşılaşılan kurulum sorunu budur.

---

## 3. OpenAI API anahtarı alma

1. [platform.openai.com](https://platform.openai.com) hesabınıza girin.
2. **Settings → Billing** bölümünden bir ödeme yöntemi ekleyip kredi yükleyin.
   Realtime (sesli) API ücretlidir; kredi olmadan asistan bağlanamaz.
3. [platform.openai.com/api-keys](https://platform.openai.com/api-keys) →
   **Create new secret key** ile anahtarı oluşturun.
4. Anahtarı kopyalayın (`sk-...` ile başlar). **Yalnızca bir kez gösterilir**,
   güvenli bir yere not edin.

Bu anahtarı birazdan kurulum sihirbazına gireceksiniz. Anahtar yalnızca kendi
bilgisayarınızda `config/api_keys.json` içinde saklanır, depoya **asla** gitmez.

---

## 4. Kurulum adımları

```bash
# 1) Projeyi indirin
git clone https://github.com/umutcindiloglu-arch/jarvis-akademisyendestek-for-macOS.git
cd jarvis-akademisyendestek-for-macOS

# 2) PortAudio'yu kurun (ses girişi için, bir kez)
brew install portaudio

# 3) İzole bir Python ortamı oluşturun
python3 -m venv venv

# 4) Bağımlılıkları kurun
./venv/bin/python -m pip install --upgrade pip
./venv/bin/python -m pip install -r requirements.txt
```

Kurulumun sağlamlığını ağ/izin gerektirmeyen testlerle doğrulayın:

```bash
./venv/bin/python test_smoke.py
```

Hepsi `ok` görünüyorsa kuruluma hazırsınız.

---

## 5. İlk açılış: kurulum sihirbazı

```bash
./venv/bin/python main.py
```

İlk çalıştırmada bir **kurulum penceresi** açılır ve şunları sorar:

| Alan | Ne işe yarar | Örnek |
|------|--------------|-------|
| OpenAI API anahtarı | Asistanın beyni | `sk-...` |
| Adınız | Sizi tanıması için | Ahmet |
| Size nasıl hitap etsin? | Konuşurken kullanacağı hitap | hocam / Ahmet Bey / kaptan |
| Mesleğiniz / alanınız | Yanıtlarını bağlamlandırır | akademisyen |
| Asistanın adı | İsteğe bağlı yeniden adlandırma | JARVIS / Athena |
| Uyandırma kelimesi | Bu kelimeyle uyanır | jarvis / athena |
| Şehir | Hava durumu için | İstanbul |
| Ses tonu | Asistanın sesi | marin / cedar / alloy … |

**Kaydet ve Başla**'ya bastığınızda değerler `config/profile.json` ve
`config/api_keys.json`'a yazılır, HUD açılır.

Ayarları sonradan değiştirmek isterseniz:

```bash
./venv/bin/python main.py --setup
```

---

## 6. macOS izinleri (önemli)

JARVIS gerçek işler yaptığı için macOS birkaç izin ister. İzinleri
**Sistem Ayarları → Gizlilik ve Güvenlik** altından yönetebilirsiniz. İlk kez
bir özelliği kullandığınızda macOS otomatik olarak sorar — **İzin Ver** deyin.

| İzin | Hangi özellik için | Nerede |
|------|--------------------|--------|
| **Mikrofon** | Sesle konuşmak (zorunlu) | Gizlilik → Mikrofon |
| **Otomasyon (Automation)** | Takvim, Mail, Notlar, Spotify kontrolü | Gizlilik → Otomasyon |
| **Ekran Kaydı (Screen Recording)** | Ekran görüntüsü almak | Gizlilik → Ekran Kaydı |

> İzni ilk anda reddederseniz ilgili özellik sessizce çalışmaz. Sonradan
> Sistem Ayarları'ndan elle açabilir, ardından uygulamayı yeniden başlatabilirsiniz.

İzni uygulamayı çalıştıran sürece (Terminal ya da JARVIS.app) verdiğinizden emin
olun; izin **çalıştıran programa** bağlıdır.

---

## 7. Kullanım

- **Uyandırma:** "<uyandırma kelimesi> uyan" (ör. *"jarvis uyan"*) ya da *"wake up"*.
  Açılışta JARVIS sessiz bekler; yalnızca uyandırınca yanıt verir.
- **Konuşma:** Uyandıktan sonra doğal Türkçe konuşun. JARVIS konuşurken
  mikrofon kapanır (yankıyla kendini kesmesini önlemek için); o yüzden o sözünü
  bitirince konuşun.
- **Uyutma:** *"uykuya geç"* / *"uyu"* deyin; tekrar uyandırana dek susar.
- **Anlatım modu:** *"bu konuyu katılımcılara anlat"* derseniz kısa konuşma
  kuralını bırakıp "Değerli katılımcılar…" diye bir mini ders verir (sunum için).
- **Kapatma:** *"görüşürüz"*, HUD'daki **SHUTDOWN** düğmesi ya da `Esc`.

---

## 8. İsteğe bağlı ek özellikler

Bunlar olmadan da JARVIS çalışır; isterseniz ekleyin:

- **Ekran parlaklığı kontrolü** — `brightness` aracı gerekir:

  ```bash
  brew install brightness
  ```

- **Müzik** — Spotify uygulamasının kurulu olması gerekir. Belirli bir parçayı
  çalmak için parçanın Spotify bağlantısını/URI'sini söyleyin.

- **Masaüstü kısayolu (JARVIS.app)** — Terminal yerine çift tıklayarak açmak
  isterseniz, Otomatik İşlemler (Automator) ile şu komutu çalıştıran bir uygulama
  oluşturabilirsiniz:

  ```bash
  cd "<proje yolu>" && ./venv/bin/python main.py
  ```

---

## 9. Sorun giderme

**`pip install pyaudio` hata veriyor / "portaudio.h not found"**
PortAudio kurulu değil. `brew install portaudio` çalıştırıp pip kurulumunu
tekrarlayın.

**"Realtime bağlanamadı" / 401 / 403 hatası**
API anahtarı hatalı ya da hesapta kredi yok. Anahtarı `--setup` ile yeniden
girin ve OpenAI Billing'de bakiyenizi kontrol edin.

**JARVIS beni duymuyor**
Mikrofon izni verilmemiş olabilir. Sistem Ayarları → Gizlilik → Mikrofon'dan
Terminal/JARVIS.app'e izin verin ve uygulamayı yeniden başlatın.

**Takvim/Mail/Notlar komutları çalışmıyor**
Otomasyon izni reddedilmiş olabilir. Sistem Ayarları → Gizlilik → Otomasyon'dan
ilgili uygulamalara izin verin.

**Ekran görüntüsü boş/çalışmıyor**
Ekran Kaydı izni gerekir. Sistem Ayarları → Gizlilik → Ekran Kaydı'ndan izin verip
uygulamayı yeniden başlatın.

**Hava durumu "alınıyor…" takılı**
İnternet bağlantısını kontrol edin; ya da şehir adı çözülememiştir. `--setup` ile
şehri tekrar girin (büyük şehir adı daha güvenilir çözülür).

**Yanlış kelimelerde uyanıyor / uyanmıyor**
`--setup` ile uyandırma kelimesini değiştirin. Daha ayırt edici, günlük konuşmada
sık geçmeyen bir kelime seçmek yanlış tetiklenmeyi azaltır.

---

## 10. Gizlilik ve güvenlik

- API anahtarınız ve kişisel profiliniz yalnızca **kendi bilgisayarınızda**
  `config/api_keys.json` ve `config/profile.json` içinde saklanır.
- Bu dosyalar `.gitignore` ile korunur; depoya **asla** gönderilmez. Yalnızca
  `*.example.json` şablonları paylaşılır.
- Öğrenilen bilgiler (hafıza) `config/memory.json` içinde tutulur ve yine
  gitignore ile korunur. İsterseniz bu dosyayı silerek hafızayı sıfırlayabilirsiniz.
- Sesiniz ve metniniz yalnızca yanıt üretmek için OpenAI'a gönderilir; OpenAI'ın
  veri politikaları geçerlidir.

---

İyi kullanımlar! Takıldığınız bir yer olursa `README.md`'deki dosya yapısı tablosu
hangi modülün ne işe yaradığını gösterir.
