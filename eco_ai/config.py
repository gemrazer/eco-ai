"""Configuración persistente de eco-ai (~/.eco-ai.json)."""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path

_CONFIG_PATH = Path.home() / ".eco-ai.json"


class Lang(str, Enum):
    ES = "es"
    EN = "en"


def load() -> dict:
    if _CONFIG_PATH.exists():
        try:
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save(data: dict) -> None:
    _CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_lang() -> Lang:
    return Lang(load().get("lang", Lang.ES.value))


def set_lang(lang: Lang) -> None:
    cfg = load()
    cfg["lang"] = lang.value
    save(cfg)
