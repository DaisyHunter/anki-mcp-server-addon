"""Create deck action implementation."""
from typing import Any

from ......handler_wrappers import HandlerError, get_col
from ......config import Config

_DEFAULT_MAX_DEPTH = 7


def _get_max_depth() -> int:
    try:
        from aqt import mw
        raw = mw.addonManager.getConfig("anki_mcp_server") or {}
        return Config.from_dict(raw).max_deck_depth
    except Exception:
        return _DEFAULT_MAX_DEPTH


def create_deck_impl(deck_name: str) -> dict[str, Any]:
    col = get_col()

    parts = deck_name.split("::")
    max_depth = _get_max_depth()
    if len(parts) > max_depth:
        raise HandlerError(
            f"Deck name can have maximum {max_depth} levels. "
            f"Provided: {len(parts)} levels ({deck_name})",
            hint=f"Use at most {max_depth} '::' separators. "
                 f"The limit can be changed in the addon config (max_deck_depth).",
        )

    if any(part.strip() == "" for part in parts):
        raise HandlerError("Deck name parts cannot be empty")

    all_deck_names = col.decks.all_names_and_ids()
    deck_exists = any(d.name == deck_name for d in all_deck_names)

    deck_id = col.decks.id(deck_name)

    response: dict[str, Any] = {
        "deckId": deck_id,
        "deckName": deck_name,
        "created": not deck_exists,
        "depth": len(parts),
        "max_depth": max_depth,
    }

    if deck_exists:
        response["exists"] = True
        response["message"] = f'Deck "{deck_name}" already exists'
    else:
        if len(parts) > 1:
            response["parent_path"] = "::".join(parts[:-1])
            response["leaf_name"] = parts[-1]
        response["message"] = f'Successfully created deck "{deck_name}"'

    return response
