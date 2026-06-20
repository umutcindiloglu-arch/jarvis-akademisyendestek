"""Ayar ve profil deposu — API anahtarı ve kişisel profili okur/yazar.

Tüm dosya yolları bu modüldeki BASE_DIR'e göre çözülür; böylece uygulama
nereden çalıştırılırsa çalıştırılsın doğru config/ klasörünü bulur.
"""

import json
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


def _write_json(path, data):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_keys():
    return _read_json(KEYS_PATH, DEFAULT_KEYS)


def save_keys(keys):
    _write_json(KEYS_PATH, keys)


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
