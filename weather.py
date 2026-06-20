"""Hava durumu — anahtarsız, ücretsiz Open-Meteo servisi.

`fetch(lat, lon, city)` anlık sıcaklık ve hava kodunu çeker, Türkçe açıklamayla
birlikte küçük bir sözlük döndürür. Ağ hatasında None döner; arayüz buna göre
'Hava durumu alınamadı' gösterir. Şehir/koordinat kullanıcı profilinden gelir
(kurulum sihirbazında `geocode()` ile çözülür).
"""

import requests

# Varsayılan konum (profil yoksa) — İstanbul.
DEFAULT_LAT, DEFAULT_LON = 41.0082, 28.9784
DEFAULT_CITY = "İSTANBUL"

# WMO hava kodları -> kısa Türkçe açıklama.
WMO = {
    0: "Açık", 1: "Az bulutlu", 2: "Parçalı bulutlu", 3: "Bulutlu",
    45: "Sisli", 48: "Kırağılı sis",
    51: "Çisenti", 53: "Çisenti", 55: "Yoğun çisenti",
    61: "Hafif yağmur", 63: "Yağmur", 65: "Şiddetli yağmur",
    71: "Hafif kar", 73: "Kar", 75: "Yoğun kar",
    80: "Sağanak", 81: "Sağanak", 82: "Şiddetli sağanak",
    95: "Gök gürültülü", 96: "Dolu fırtınası", 99: "Dolu fırtınası",
}


def fetch(lat=DEFAULT_LAT, lon=DEFAULT_LON, city=DEFAULT_CITY):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,weather_code",
        "timezone": "auto",
    }
    try:
        resp = requests.get(url, params=params, timeout=8)
        resp.raise_for_status()
        cur = resp.json()["current"]
    except (requests.RequestException, KeyError, ValueError):
        return None
    return {
        "city": (city or DEFAULT_CITY).upper(),
        "temp": round(cur["temperature_2m"]),
        "desc": WMO.get(cur["weather_code"], "—"),
    }


def geocode(city_name):
    """Şehir adını enlem/boylam'a çevirir (Open-Meteo geocoding, anahtarsız).

    Kurulum sihirbazında kullanılır. Bulamazsa None döner.
    Dönüş: {"sehir": <düzgün ad>, "enlem": float, "boylam": float}
    """
    if not (city_name or "").strip():
        return None
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {"name": city_name.strip(), "count": 1, "language": "tr"}
    try:
        resp = requests.get(url, params=params, timeout=8)
        resp.raise_for_status()
        results = resp.json().get("results") or []
    except (requests.RequestException, KeyError, ValueError):
        return None
    if not results:
        return None
    r = results[0]
    return {"sehir": r.get("name", city_name), "enlem": r["latitude"], "boylam": r["longitude"]}
