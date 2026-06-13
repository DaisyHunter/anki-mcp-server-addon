"""List deck backups action implementation."""
import json
from pathlib import Path
from typing import Any

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


def list_backups_impl() -> dict[str, Any]:
    backup_dir = _get_deck_backup_dir()

    if not backup_dir.exists():
        return {
            "backups": [],
            "backup_dir": str(backup_dir),
            "count": 0,
            "message": "No deck backups found.",
            "hint": "Use the export action to create the first snapshot.",
        }

    try:
        from aqt import mw
        raw = mw.addonManager.getConfig("anki_mcp_server") or {}
        cfg = Config.from_dict(raw)
        max_count = cfg.deck_backup_max_count
    except Exception:
        max_count = 10

    snapshots = sorted(backup_dir.glob("deck-snapshot-*.json"), reverse=True)
    backups = []
    for f in snapshots:
        stat = f.stat()
        deck_count = "?"
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                deck_count = data.get("total_decks", "?")
        except Exception:
            pass
        backups.append({
            "filename": f.name,
            "file_path": str(f),
            "size": stat.st_size,
            "timestamp": f.stem.replace("deck-snapshot-", ""),
            "deck_count": deck_count,
        })

    return {
        "backups": backups,
        "backup_dir": str(backup_dir),
        "count": len(backups),
        "max_backups": max_count,
        "message": f"Found {len(backups)} deck backup(s)",
        "hint": "Use the restore action with file_path and confirm=true to restore.",
    }
