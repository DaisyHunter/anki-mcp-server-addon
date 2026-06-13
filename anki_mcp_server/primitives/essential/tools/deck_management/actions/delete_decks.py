"""Delete decks action implementation."""
from typing import Any
import logging
from ......handler_wrappers import HandlerError, get_col

logger = logging.getLogger(__name__)
_DEFAULT_DECK_ID = 1


def _resolve_deck_ids(col: Any, names: list[str]) -> list[tuple[str, int, str]]:
    all_decks = col.decks.all_names_and_ids()
    name_to_id: dict[str, int] = {}
    id_to_name: dict[int, str] = {}
    for d in all_decks:
        name_to_id[d.name.lower()] = d.id
        id_to_name[d.id] = d.name

    results: list[tuple[str, int, str]] = []
    for raw in names:
        raw = raw.strip()
        if not raw:
            raise HandlerError(
                f"Empty deck name in list: {names}",
                hint="Remove empty entries from the decks list.",
                code="validation_error",
            )
        if raw.isdigit():
            deck_id = int(raw)
            actual_name = id_to_name.get(deck_id)
            if actual_name is None:
                raise HandlerError(
                    f'Deck ID "{deck_id}" not found',
                    code="not_found", deck_id=deck_id,
                )
            results.append((raw, deck_id, actual_name))
        else:
            deck_id = name_to_id.get(raw.lower())
            if deck_id is None:
                substring_matches = [d for d in all_decks if raw.lower() in d.name.lower()]
                if len(substring_matches) == 1:
                    deck_id = substring_matches[0].id
                elif len(substring_matches) > 1:
                    raise HandlerError(
                        f'Multiple decks match "{raw}": ' + ", ".join(d.name for d in substring_matches),
                        code="validation_error", matches=[d.name for d in substring_matches],
                    )
                else:
                    available = [d.name for d in all_decks[:10]]
                    raise HandlerError(
                        f'Deck "{raw}" not found',
                        hint=f"Known: {', '.join(available)}", code="not_found", deck=raw,
                    )
            results.append((raw, deck_id, id_to_name[deck_id]))
    return results


def delete_decks_impl(
    decks: list[str], cards_too: bool = False, confirm: bool = False
) -> dict[str, Any]:
    if not confirm:
        raise HandlerError(
            "Confirm required to delete decks",
            hint="Ask the user for explicit confirmation before deleting decks. "
                 "Set confirm=true only after the user approves.",
            code="confirmation_required",
        )

    if not decks:
        raise HandlerError("No decks specified", code="validation_error")

    col = get_col()

    for raw in decks:
        if not isinstance(raw, str):
            raise HandlerError(
                f"Each deck must be a name string, got: {type(raw).__name__}",
                hint="Provide deck names as strings, e.g., ['My Deck', 'Spanish::Verbs'].",
                code="validation_error",
            )

    # Resolve deck IDs first (validate before any mutation)
    resolved = _resolve_deck_ids(col, decks)
    seen_ids: set[int] = set()
    unique: list[tuple[str, int, str]] = []
    for raw, did, name in resolved:
        if did not in seen_ids:
            seen_ids.add(did)
            unique.append((raw, did, name))

    # Phase 1: validate
    blocked: list[dict[str, Any]] = []
    allowed: list[dict[str, Any]] = []

    for raw, did, name in unique:
        if did == _DEFAULT_DECK_ID:
            blocked.append({
                "deck": raw, "deck_name": name, "deck_id": did,
                "reason": "Cannot delete the Default deck",
            })
            continue

        deck_dict = col.decks.get(did)
        if deck_dict and deck_dict.get("dyn"):
            blocked.append({
                "deck": raw, "deck_name": name, "deck_id": did,
                "reason": "Use the filtered_deck management tool to delete filtered decks",
            })
            continue

        card_count = col.decks.card_count(did, include_subdecks=False)
        child_count = col.decks.card_count(did, include_subdecks=True) - card_count

        if card_count > 0 and not cards_too:
            blocked.append({
                "deck": raw, "deck_name": name, "deck_id": did,
                "card_count": card_count, "child_card_count": child_count,
                "reason": (
                    f"Deck contains {card_count} cards. Set cards_too=true to "
                    "delete anyway (cards and orphaned notes will be permanently deleted)"
                ),
            })
            continue

        allowed.append({
            "deck": raw, "deck_name": name, "deck_id": did,
            "card_count": card_count, "child_card_count": child_count,
        })

    # Human confirmation (Qt dialog — AI cannot bypass)
    if allowed:
        total_cards = sum(e["card_count"] + e["child_card_count"] for e in allowed)
        deck_list = "\n".join(f"  • {e['deck_name']} ({e['card_count']} cards)" for e in allowed)
        from ......handler_wrappers import require_human_confirm
        require_human_confirm(
            "Delete Decks",
            f"Delete {len(allowed)} deck(s)?\n\n"
            f"{deck_list}\n\n"
            f"Total: {total_cards} cards will be permanently deleted.\n\n"
            f"This cannot be undone."
        )

    # Phase 1.5: move cards to .Trash deck before deleting (cards_too mode)
    cards_moved_total = 0
    trash_deck_id = col.decks.id(".Trash")  # Creates if missing
    for entry in allowed:
        if entry["card_count"] > 0 and cards_too:
            try:
                card_ids = col.decks.cids(entry["deck_id"], children=False)
                if card_ids:
                    col.set_deck(card_ids, trash_deck_id)
                    cards_moved_total += len(card_ids)
            except Exception as e:
                logger.error("Failed to move cards from deck %d: %s", entry["deck_id"], e, exc_info=True)

    # Phase 2: delete allowed decks
    deleted: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    for entry in allowed:
        try:
            col.decks.remove([entry["deck_id"]])
            deleted.append({
                "deck": entry["deck"], "deck_name": entry["deck_name"],
                "deck_id": entry["deck_id"],
                "cards_moved": entry["card_count"] if entry["card_count"] > 0 else 0,
            })
        except Exception as e:
            logger.error("Failed to delete deck %d: %s", entry["deck_id"], e, exc_info=True)
            failed.append({
                "deck": entry["deck"], "deck_name": entry["deck_name"],
                "deck_id": entry["deck_id"], "error": str(e),
            })

    cards_moved = cards_moved_total
    parts = [f"Deleted {len(deleted)} deck(s)"]
    if cards_moved > 0:
        parts.append(f"{cards_moved} cards moved to .Trash")
    if blocked:
        parts.append(f"{len(blocked)} deck(s) blocked — see blocked list for reasons")
    if failed:
        parts.append(f"{len(failed)} deck(s) failed — see failed list")

    return {
        "deleted": deleted, "deleted_count": len(deleted),
        "blocked": blocked, "blocked_count": len(blocked),
        "failed": failed, "failed_count": len(failed),
        "cards_too_mode": cards_too,
        "cards_moved": cards_moved,
        "message": ". ".join(parts),
        "hint": (
            "Cards from deleted decks were moved to the .Trash deck — "
            "they are NOT permanently deleted. Check .Trash in the Anki browser "
            "to recover them."
        ),
    }
