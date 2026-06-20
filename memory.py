"""Kalıcı hafıza — JARVIS'in kullanıcıyı zamanla öğrenmesini sağlar.

Kullanıcı hakkında öğrenilen kalıcı bilgiler (tercihler, alışkanlıklar,
isimler, projeler…) `config/memory.json` içinde saklanır. Beyin, kalıcı bir
bilgi öğrendiğinde `hatirla` aracını çağırarak buraya ekler; her oturum
başında bu bilgiler sistem istemine yüklenir. Dosya gizlidir (gitignore).
"""

import json
import time

from store import CONFIG_DIR

MEM_PATH = CONFIG_DIR / "memory.json"


def load():
    try:
        return json.loads(MEM_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save(items):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    MEM_PATH.write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def add(fact):
    fact = (fact or "").strip()
    if not fact:
        return "Boş bir şey hatırlayamam."
    items = load()
    if any(fact.lower() == i["fact"].lower() for i in items):
        return "Bunu zaten biliyorum."
    items.append({"fact": fact, "ts": time.strftime("%Y-%m-%d")})
    _save(items)
    return "Tamam, bunu aklımda tutacağım."


def remove(query):
    query = (query or "").strip().lower()
    items = load()
    kept = [i for i in items if query not in i["fact"].lower()]
    _save(kept)
    return "Unuttum." if len(kept) < len(items) else "Öyle bir kayıt bulamadım."


def as_prompt_text():
    items = load()
    if not items:
        return ""
    lines = "\n".join(f"- {i['fact']}" for i in items)
    return f"Kullanıcı hakkında zamanla öğrendiklerin:\n{lines}"
