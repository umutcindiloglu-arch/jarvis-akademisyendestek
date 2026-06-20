"""Ayar ve profil deposu — API anahtarı ve kişisel profili okur/yazar.

Tüm dosya yolları bu modüldeki BASE_DIR'e göre çözülür; böylece uygulama
nereden çalıştırılırsa çalıştırılsın doğru config/ klasörünü bulur.
"""

import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
KEYS_PATH = CONFIG_DIR / "api_keys.json"
PROFILE_PATH = CONFIG_DIR / "profile.json"

DEFAULT_KEYS = {
    "openai_api_key": "",
    "model": "gpt-4o",
    "tts_voice": "marin",
    "stt_model": "whisper-1",
}

DEFAULT_PROFILE = {
    "asistan_adi": "JARVIS",
    "uyandirma_kelimesi": "jarvis",
    "hitap": "hocam",
    "kullanici_adi": "",
    "meslek": "akademisyen",
    "dil": "tr",
    "sehir": "İstanbul",
    "enlem": 41.0082,
    "boylam": 28.9784,
    "notlar": [],
    "tercihler": {"acilis_selami": "Buyurun, ne yapmamı istersiniz?"},
}


def _read_json(path, fallback):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(fallback)
        merged.update(data)
        return merged
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(fallback)


def _write_json(path, data, secret=False):
    """JSON yazar. `secret=True` ise dosyayı yalnızca sahibe okunur (0600)
    olacak şekilde oluşturur; API anahtarı gibi gizli veriler için kullanılır."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # config/ klasörünü de sahibe özel yap (varsa kısıtla, yoksa zaten kuruldu).
    try:
        os.chmod(CONFIG_DIR, 0o700)
    except OSError:
        pass
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    if secret:
        # 0600 ile aç: başka kullanıcılar/işlemler anahtarı okuyamasın.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        # Dosya zaten 0600 izinleriyle vardıysa da garantiye al.
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write(payload)


def load_keys():
    return _read_json(KEYS_PATH, DEFAULT_KEYS)


def save_keys(keys):
    _write_json(KEYS_PATH, keys, secret=True)


def has_api_key():
    return bool(load_keys().get("openai_api_key", "").strip())


def set_api_key(key):
    keys = load_keys()
    keys["openai_api_key"] = key.strip()
    save_keys(keys)


def load_profile():
    return _read_json(PROFILE_PATH, DEFAULT_PROFILE)


def save_profile(profile):
    _write_json(PROFILE_PATH, profile)


def profile_exists():
    """Kullanıcı kurulum sihirbazını tamamlayıp profili kaydetti mi?"""
    return PROFILE_PATH.exists()
