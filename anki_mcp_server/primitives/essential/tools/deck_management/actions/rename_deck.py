"""Rename deck action implementation."""
from typing import Any
import logging
from ......handler_wrappers import HandlerError, get_col

logger = logging.getLogger(__name__)


def rename_deck_impl(deck: str, new_name: str) -> dict[str, Any]:
    col = get_col()

    if not deck or not deck.strip():
        raise HandlerError("Deck name cannot be empty", code="validation_error")
    if not new_name or not new_name.strip():
        raise HandlerError("New deck name cannot be empty", code="validation_error")

    deck = deck.strip()
    new_name = new_name.strip()

    parts = new_name.split("::")
    if any(part.strip() == "" for part in parts):
        raise HandlerError("Deck name parts cannot be empty", code="validation_error")

    if deck == new_name:
        raise HandlerError(
            f'New name "{new_name}" is the same as the current name',
            code="validation_error",
        )

    # Resolve deck
    deck_id = None
    old_name = deck

    if deck.isdigit():
        deck_id = int(deck)
        deck_dict = col.decks.get(deck_id)
        if deck_dict:
            old_name = deck_dict.get("name", deck)
        else:
            raise HandlerError(f'Deck ID "{deck_id}" not found', code="not_found", deck_id=deck_id)
    else:
        deck_id = col.decks.id_for_name(deck)
        if deck_id is None:
            all_decks = col.decks.all_names_and_ids()
            matches = [d for d in all_decks if d.name.lower() == deck.lower()]
            if matches:
                deck_id = matches[0].id
                old_name = matches[0].name
            else:
                substring_matches = [d for d in all_decks if deck.lower() in d.name.lower()]
                if len(substring_matches) == 1:
                    deck_id = substring_matches[0].id
                    old_name = substring_matches[0].name
                elif len(substring_matches) > 1:
                    raise HandlerError(
                        f'Multiple decks match "{deck}": ' + ", ".join(d.name for d in substring_matches),
                        code="validation_error", matches=[d.name for d in substring_matches],
                    )
                else:
                    available = [d.name for d in all_decks[:10]]
                    raise HandlerError(
                        f'Deck "{deck}" not found',
                        hint=f"Known: {', '.join(available)}", code="not_found", deck=deck,
                    )

    existing_id = col.decks.id_for_name(new_name)
    if existing_id is not None and existing_id != deck_id:
        raise HandlerError(
            f'A deck named "{new_name}" already exists',
            code="duplicate", existing_deck_id=existing_id,
        )

    card_count = col.decks.card_count(deck_id, include_subdecks=True)
    children = col.decks.children(deck_id)
    child_names = [name for name, _ in children] if children else []

    try:
        col.decks.rename(deck_id, new_name)
    except Exception as e:
        logger.error("Failed to rename deck %s -> %s: %s", old_name, new_name, e, exc_info=True)
        raise HandlerError(
            f"Failed to rename deck: {e}", code="rename_error",
            old_name=old_name, new_name=new_name,
        )

    result: dict[str, Any] = {
        "old_name": old_name, "new_name": new_name, "deck_id": deck_id,
        "card_count": card_count, "child_decks_updated": child_names,
        "message": f'Renamed deck "{old_name}" to "{new_name}" ({card_count} cards preserved)',
    }
    if child_names:
        result["message"] += f". {len(child_names)} child deck(s) updated: {', '.join(child_names)}"
    return result
