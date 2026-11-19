from __future__ import annotations

import json
from collections.abc import Mapping

from .config import get_config


def load_state() -> dict[str, object]:
    """Load persisted import state from disk.

    Returns:
        Parsed JSON dict, or an empty dict if the file is absent or corrupt.
    """
    state_path = get_config().state_path
    if not state_path.exists():
        return {}
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except json.JSONDecodeError:
        return {}


def get_state_str(state: dict[str, object], key: str, default: str | None = None) -> str | None:
    """Return a string value from the state dict, or ``default`` if absent or wrong type.

    Args:
        state: loaded state dict.
        key: key to look up.
        default: fallback when the key is missing or not a string.
    """
    val = state.get(key)
    return val if isinstance(val, str) else default


def save_state(state: Mapping[str, object]) -> None:
    """Persist import state to disk as JSON.

    Args:
        state: key/value pairs to write (strings, booleans, or None).
    """
    state_path = get_config().state_path
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
