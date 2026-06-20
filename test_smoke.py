#!/usr/bin/env python3
"""JARVIS offline smoke/birim testleri — ağ ve macOS izni gerektirmez.

Çalıştırma:
    ./venv/bin/python test_smoke.py

Saf/deterministik mantığı doğrular: modül importları, uyandırma/uyku
eşleşmesi, araç şemasının tutarlılığı, hafıza CRUD (gerçek dosya yedeklenip
geri yüklenir), store varsayılanları ve sysinfo ölçümleri. osascript,
mikrofon ve ağ çağrıları kapsam dışıdır.
"""

import sys
import traceback

_passed = 0
_failed = 0


def check(name, fn):
    global _passed, _failed
    try:
        fn()
        _passed += 1
        print(f"  ok   {name}")
    except Exception as e:  # noqa: BLE001 - test koşucusu tüm hataları raporlar
        _failed += 1
        print(f"  FAIL {name}: {e}")
        traceback.print_exc()


# --- 1) Importlar ----------------------------------------------------------

def test_imports():
    import actions  # noqa: F401
    import core  # noqa: F401
    import memory  # noqa: F401
    import realtime  # noqa: F401
    import store  # noqa: F401
    import sysinfo  # noqa: F401
    import ui  # noqa: F401
    import weather  # noqa: F401


# --- 2) Uyandırma / uyku eşleşmesi -----------------------------------------

def test_wake():
    import realtime as r
    for phrase in ["jarvis wake up", "JARVIS WAKE UP", "carvis uyan",
                   "jarvis kalk", "jarvıs uyandın mı", "wake up"]:
        assert r.is_wake(phrase.lower()), f"uyandırmalıydı: {phrase}"
    for phrase in ["jarvis", "merhaba", "uyku moduna geç"]:
        assert not r.is_wake(phrase.lower()), f"uyandırmamalıydı: {phrase}"


def test_sleep():
    import realtime as r
    for phrase in ["uyku moduna geç", "uykuya geç", "uyku modu",
                   "jarvis uyu", "uyu jarvis", "uyku moduna geçebilirsin",
                   "jarvis uyuyabilirsin", "uyuyabilirsin"]:
        assert r.is_sleep(phrase.lower()), f"uyutmalıydı: {phrase}"
    for phrase in ["merhaba", "jarvis wake up", "geç kaldım", "uyandım"]:
        assert not r.is_sleep(phrase.lower()), f"uyutmamalıydı: {phrase}"


def test_greet():
    import realtime as r
    for phrase in ["katılımcılarımıza bir şey söyle", "katılımcılara selam ver",
                   "el salla", "herkese merhaba de", "izleyicilere selam"]:
        assert r.is_greet(phrase.lower()), f"selam tetiklemeliydi: {phrase}"
    for phrase in ["bugün hava nasıl", "saat kaç", "müziğimizi aç"]:
        assert not r.is_greet(phrase.lower()), f"selam tetiklememeliydi: {phrase}"


def test_meaningful():
    import realtime as r
    for ok in ["bugün hava nasıl", "saat kaç", "ab"]:
        assert r._meaningful(ok.lower()), f"anlamlı olmalı: {ok}"
    for noise in ["", " ", ".", "?!", "a", "altyazı m.k.",
                  "abone olmayı unutmayın", "thanks for watching"]:
        assert not r._meaningful(noise.lower()), f"anlamsız olmalı: {noise}"


def test_now_str():
    import datetime
    import realtime as r
    s = r.now_str()
    assert str(datetime.datetime.now().year) in s, s
    assert any(g in s for g in ("Pazartesi", "Salı", "Çarşamba", "Perşembe",
                                "Cuma", "Cumartesi", "Pazar")), s


# --- 3) Araç şeması tutarlılığı --------------------------------------------

def test_tool_schema():
    import core
    names = [t["function"]["name"] for t in core.TOOLS]
    assert len(names) == len(set(names)), "araç adları tekil olmalı"
    assert set(names) == set(core.TOOL_DISPATCH), (
        f"TOOLS adları TOOL_DISPATCH ile eşleşmeli: "
        f"{set(names) ^ set(core.TOOL_DISPATCH)}"
    )
    for fn in core.TOOL_DISPATCH.values():
        assert callable(fn)


def test_flat_tools():
    import core
    import realtime as r
    flat = r._flat_tools()
    assert len(flat) == len(core.TOOLS)
    for t in flat:
        assert t["type"] == "function"
        assert t["name"] and isinstance(t["name"], str)
        assert "parameters" in t and t["parameters"].get("type") == "object"


def test_system_prompt():
    import core
    # Varsayılan profil: generic, kişisel veri içermez.
    p = core.build_system_prompt({}, "01.01.2026 10:00")
    assert "JARVIS" in p
    assert "Umut" not in p, "varsayılan istemde kişisel ad olmamalı"
    # Özelleştirilmiş profil değerleri isteme yansımalı.
    p2 = core.build_system_prompt(
        {"asistan_adi": "Athena", "hitap": "kaptan", "uyandirma_kelimesi": "athena"},
        "01.01.2026 10:00",
    )
    assert "Athena" in p2 and "kaptan" in p2


def test_wake_custom_word():
    import realtime as r
    names = r.wake_names_for("athena")
    assert names == ("athena",), names
    assert r.is_wake("athena uyan", names)
    assert not r.is_wake("jarvis uyan", names), "özel kelimede jarvis uyandırmamalı"
    # Varsayılan 'jarvis' için sık karışan biçimler korunur.
    assert r.wake_names_for("jarvis") == r._WAKE_NAMES


# --- 4) Hafıza CRUD (gerçek dosya yedeklenir) -------------------------------

def test_memory_roundtrip():
    import memory
    path = memory.MEM_PATH
    backup = path.read_text(encoding="utf-8") if path.exists() else None
    try:
        memory._save([])
        assert memory.load() == []
        assert memory.as_prompt_text() == ""
        memory.add("Test gerçeği: kahveyi sade içer.")
        assert any("kahveyi sade" in i["fact"] for i in memory.load())
        assert "kahveyi sade" in memory.as_prompt_text()
        # tekrar ekleme engellenmeli
        assert memory.add("Test gerçeği: kahveyi sade içer.") == "Bunu zaten biliyorum."
        out = memory.remove("kahveyi sade")
        assert out == "Unuttum." and memory.load() == []
    finally:
        if backup is not None:
            path.write_text(backup, encoding="utf-8")
        elif path.exists():
            path.unlink()


# --- 5) Store varsayılanları -----------------------------------------------

def test_store_defaults():
    import store
    keys = store.load_keys()
    for k in store.DEFAULT_KEYS:
        assert k in keys, f"eksik anahtar: {k}"
    prof = store.load_profile()
    assert prof.get("hitap")


# --- 6) Sistem ölçümleri ---------------------------------------------------

def test_sysinfo():
    import sysinfo
    assert 0.0 <= sysinfo.cpu_percent() <= 100.0
    assert 0.0 <= sysinfo.ram_percent() <= 100.0
    assert isinstance(sysinfo.ram_detail(), str)
    g = sysinfo.gpu_percent()
    assert g is None or 0.0 <= g <= 100.0
    b = sysinfo.battery()
    assert b is None or (isinstance(b, tuple) and len(b) == 2)


def main():
    tests = [
        ("imports", test_imports),
        ("wake matcher", test_wake),
        ("sleep matcher", test_sleep),
        ("greet matcher", test_greet),
        ("meaningful/noise filter", test_meaningful),
        ("now_str format", test_now_str),
        ("tool schema consistency", test_tool_schema),
        ("flat tools (realtime)", test_flat_tools),
        ("system prompt", test_system_prompt),
        ("wake custom word", test_wake_custom_word),
        ("memory roundtrip", test_memory_roundtrip),
        ("store defaults", test_store_defaults),
        ("sysinfo metrics", test_sysinfo),
    ]
    print(f"JARVIS smoke testleri — {len(tests)} test\n")
    for name, fn in tests:
        check(name, fn)
    print(f"\n{_passed} geçti, {_failed} başarısız")
    sys.exit(1 if _failed else 0)


if __name__ == "__main__":
    main()
