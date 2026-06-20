#!/usr/bin/env python3
"""JARVIS — gerçek zamanlı sesli masaüstü asistanı (akademisyen destek sürümü).

Akış: ilk açılışta kurulum sihirbazı (API anahtarı + kişiselleştirme) → HUD tam
ekran açılır (sessiz) → uyandırma kelimesiyle ("jarvis uyan") ya da metin
kutusuyla uyanır → OpenAI Realtime API üzerinden konuşma-konuşmaya sohbet eder
ve gerekirse masaüstünde işlem yapar.

Çalıştırma:
    ./venv/bin/python main.py            # normal başlat
    ./venv/bin/python main.py --setup    # ayarları yeniden yapılandır
"""

import sys
import threading

import realtime
import store
import ui


def _run_setup(force=False):
    """Gerekiyorsa kurulum sihirbazını aç, sonucu kaydet.

    İlk açılışta (anahtar veya profil yok) ya da --setup verildiğinde çalışır.
    """
    if not force and store.has_api_key() and store.profile_exists():
        return
    out = ui.run_setup(store.load_keys(), store.load_profile())
    if out is None:
        sys.exit(0)  # kullanıcı vazgeçti
    keys, profile = out
    store.save_keys(keys)
    store.save_profile(profile)


def main():
    _run_setup(force="--setup" in sys.argv)

    keys = store.load_keys()
    profile = store.load_profile()

    hud = ui.HUD(title=profile.get("asistan_adi", "JARVIS"), profile=profile)
    client = realtime.RealtimeClient(hud, keys, profile)
    hud.on_ready = lambda: threading.Thread(target=client.run, daemon=True).start()
    hud.on_quit = client.stop  # kapanınca çalan sesi anında kes
    hud.run()


if __name__ == "__main__":
    main()
