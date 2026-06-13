"""Export decks action implementation."""
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from ......handler_wrappers import get_col
from ......config import Config


def _get_deck_backup_dir() -> Path:
    try:
        from aqt import mw
        raw = mw.addonManager.getConfig("anki_mcp_server") or {}
        cfg = Config.from_dict(raw)
        if cfg.deck_backup_dir:
            return Path(cfg.deck_backup_dir)
    except Exception:
        pass
    return Path(__file__).resolve().parents[5] / "user_files" / "deck_backups"


def _get_deck_max_count() -> int:
    try:
        from aqt import mw
        raw = mw.addonManager.getConfig("anki_mcp_server") or {}
        return Config.from_dict(raw).deck_backup_max_count
    except Exception:
        return 10


def _rotate_deck_backups(backup_dir: Path, max_count: int) -> list[str]:
    snapshots = sorted(backup_dir.glob("deck-snapshot-*.json"))
    removed = []
    while len(snapshots) >= max_count:
        oldest = snapshots.pop(0)
        oldest.unlink(missing_ok=True)
        removed.append(oldest.name)
    return removed


def _build_deck_tree(col: Any) -> list[dict[str, Any]]:
    all_decks = col.decks.all_names_and_ids()
    if not all_decks:
        return []

    filtered_ids: set[int] = {d["id"] for d in col.decks.all() if d.get("dyn")}

    deck_tree = col.sched.deck_due_tree()

    def build_node_map(node, node_map):
        node_map[node.deck_id] = node
        for child in node.children:
            build_node_map(child, node_map)

    node_map: dict[int, Any] = {}
    for child in deck_tree.children:
        build_node_map(child, node_map)

    decks = []
    for deck_pair in all_decks:
        name = deck_pair.name
        did = deck_pair.id
        parent = name.rsplit("::", 1)[0] if "::" in name else None

        entry: dict[str, Any] = {
            "name": name, "deck_id": did, "parent": parent,
            "is_filtered": did in filtered_ids,
        }

        tree_node = node_map.get(did)
        if tree_node:
            entry["stats"] = {
                "new_count": tree_node.new_count,
                "learn_count": tree_node.learn_count,
                "review_count": tree_node.review_count,
                "total_in_deck": tree_node.total_in_deck,
            }
        else:
            entry["stats"] = {"new_count": 0, "learn_count": 0, "review_count": 0, "total_in_deck": 0}

        deck_dict = col.decks.get(did)
        if deck_dict:
            desc = deck_dict.get("desc", "")
            if desc:
                entry["description"] = str(desc)
            config_id = deck_dict.get("conf")
            if config_id:
                entry["config_id"] = config_id

        decks.append(entry)

    top = [d for d in decks if d["parent"] is None]
    children = [d for d in decks if d["parent"] is not None]
    top.sort(key=lambda d: d["name"])
    children.sort(key=lambda d: (d["parent"] or "", d["name"]))
    return top + children


def export_decks_impl() -> dict[str, Any]:
    col = get_col()
    decks = _build_deck_tree(col)

    if not decks:
        return {
            "exported": True, "file_path": "",
            "message": "No decks to export.",
            "hint": "Use the create action to create your first deck.",
        }

    backup_dir = _get_deck_backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)
    max_count = _get_deck_max_count()
    removed = _rotate_deck_backups(backup_dir, max_count)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"deck-snapshot-{timestamp}.json"
    filepath = backup_dir / filename

    top_level = [d for d in decks if d["parent"] is None]
    total_cards = sum(d["stats"]["total_in_deck"] for d in decks)

    payload = {
        "exported_at": datetime.now().isoformat(),
        "decks": decks,
        "total_decks": len(decks),
        "top_level_decks": len(top_level),
        "filtered_decks": sum(1 for d in decks if d["is_filtered"]),
        "total_cards_in_decks": total_cards,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    existing = sorted(backup_dir.glob("deck-snapshot-*.json"))
    parts = [f"Saved to {filepath.name}"]
    if removed:
        parts.append(f"removed {len(removed)} old backup(s)")

    return {
        "exported": True,
        "file_path": str(filepath),
        "filename": filename,
        "backup_dir": str(backup_dir),
        "deck_count": len(decks),
        "top_level_decks": len(top_level),
        "filtered_decks": sum(1 for d in decks if d["is_filtered"]),
        "total_cards_in_decks": total_cards,
        "backup_count": len(existing),
        "max_backups": max_count,
        "removed_old": removed,
        "message": f"Exported {len(decks)} decks ({total_cards} cards total). {'; '.join(parts)}.",
        "hint": f"Use the restore action with file_path={str(filepath)!r} to recreate this structure later.",
    }
