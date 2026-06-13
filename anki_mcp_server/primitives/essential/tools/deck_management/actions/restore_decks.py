"""Restore decks action implementation."""
import json
import logging
from pathlib import Path
from typing import Any
from ......handler_wrappers import HandlerError, get_col

logger = logging.getLogger(__name__)


def restore_decks_impl(file_path: str, confirm: bool = False) -> dict[str, Any]:
    if not confirm:
        raise HandlerError(
            "Confirm required to restore deck structure from file",
            hint="Read the backup file first, then tell the user how many decks "
                 "will be created. Set confirm=true only after the user approves.",
            code="confirmation_required",
        )

    path = Path(file_path).resolve()
    if not path.exists():
        raise HandlerError(
            f'Snapshot file not found: "{file_path}"',
            code="not_found",
        )
    if path.suffix.lower() != ".json":
        raise HandlerError(
            f'Expected a .json file, got "{path.suffix}"',
            code="validation_error",
        )

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise HandlerError(
            f"Invalid JSON in snapshot file: {e}",
            code="validation_error",
        ) from e

    snapshot_decks = data.get("decks", [])
    if not snapshot_decks:
        raise HandlerError(
            "Snapshot file contains no deck data",
            code="validation_error",
        )

    col = get_col()
    current_names: set[str] = {d.name for d in col.decks.all_names_and_ids()}

    top_level = [d for d in snapshot_decks if not d.get("parent")]
    child_decks = [d for d in snapshot_decks if d.get("parent")]
    top_level.sort(key=lambda d: d.get("name", ""))
    child_decks.sort(key=lambda d: d.get("name", "").count("::"))
    ordered = top_level + child_decks

    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    for entry in ordered:
        name = entry.get("name", "").strip()
        if not name:
            skipped.append({"deck_name": "(empty)", "reason": "Empty deck name in snapshot"})
            continue
        if name in current_names:
            skipped.append({
                "deck_name": name, "deck_id": col.decks.id_for_name(name),
                "reason": "Already exists",
            })
            continue
        try:
            deck_id = col.decks.id(name)
            created.append({
                "deck_name": name, "deck_id": deck_id,
                "parent": entry.get("parent"), "was_in_snapshot": True,
            })
            current_names.add(name)
        except Exception as e:
            logger.error("Failed to create deck %s: %s", name, e, exc_info=True)
            failed.append({"deck_name": name, "error": str(e)})

    total_snapshot = len(snapshot_decks)
    parts_parts = [f"Created {len(created)} deck(s)"]
    if skipped:
        parts_parts.append(f"{len(skipped)} already existed, skipped")
    if failed:
        parts_parts.append(f"{len(failed)} failed")

    result: dict[str, Any] = {
        "created": created, "created_count": len(created),
        "skipped": skipped, "skipped_count": len(skipped),
        "failed": failed, "failed_count": len(failed),
        "total_in_snapshot": total_snapshot,
        "message": ". ".join(parts_parts),
    }
    if created:
        created_names = [d["deck_name"] for d in created]
        result["hint"] = (
            f"Deck structure restored. New decks: {', '.join(created_names)}. "
            "These decks are empty — use add_notes or the Anki browser to add cards."
        )
    else:
        result["hint"] = "No new decks were needed. The deck structure already matches the backup."
    return result
