"""Multi-action tool for deck management operations."""
from typing import Annotated, Any, ClassVar, Literal, Union

from pydantic import BaseModel, Field

from .....tool_decorator import Tool
from .....handler_wrappers import HandlerError

from .actions.rename_deck import rename_deck_impl
from .actions.delete_decks import delete_decks_impl
from .actions.export_decks import export_decks_impl
from .actions.restore_decks import restore_decks_impl
from .actions.list_backups import list_backups_impl
from .actions.create_deck import create_deck_impl

_BASE_DESCRIPTION = "Manage deck organization and backups"


class RenameDeckParams(BaseModel):
    """Parameters for rename action."""
    _tool_description: ClassVar[str] = (
        "rename: Rename a single Anki deck (atomic, preserves all cards and scheduling). "
        "Child decks are automatically updated. One deck per call."
    )
    _destructive: ClassVar[bool] = True
    action: Literal["rename"]
    deck: str = Field(description="Current deck name or ID to rename")
    new_name: str = Field(description="New name for the deck (use '::' for hierarchy)")


class DeleteDecksParams(BaseModel):
    """Parameters for delete action."""
    _tool_description: ClassVar[str] = (
        "delete: Delete one or more Anki decks. With cards_too=true, cards are "
        "moved to the Default deck before deletion (preserved, not lost). "
        "SAFE WORKFLOW: call export action first to create a backup, then delete. "
        "By default only empty decks can be deleted."
    )
    _destructive: ClassVar[bool] = True
    action: Literal["delete"]
    decks: list[str] = Field(description="Deck names or IDs to delete")
    cards_too: bool = Field(default=False, description="Also delete decks containing cards (cards will be permanently deleted)")
    confirm: bool = Field(default=False, description="Set true after user explicitly approves the deletion")


class ExportDecksParams(BaseModel):
    """Parameters for export action."""
    _tool_description: ClassVar[str] = (
        "export: Export the complete deck tree structure (names, hierarchy, card counts) "
        "to a timestamped JSON file. Cards and scheduling data are NOT exported."
    )
    action: Literal["export"]


class RestoreDecksParams(BaseModel):
    """Parameters for restore action."""
    _tool_description: ClassVar[str] = (
        "restore: Recreate deck structure from a JSON backup. Only creates decks that "
        "are missing — never deletes or modifies existing decks. "
        "Parent decks are created before children."
    )
    _destructive: ClassVar[bool] = True
    action: Literal["restore"]
    file_path: str = Field(description="Path to a JSON backup file created by export action")
    confirm: bool = Field(default=False, description="Set true after user approves the restore")


class ListBackupsParams(BaseModel):
    """Parameters for list_backups action."""
    _tool_description: ClassVar[str] = (
        "list_backups: List available deck structure snapshots (timestamped JSON files). "
        "Sorted newest first."
    )
    action: Literal["list_backups"]


class CreateDeckParams(BaseModel):
    """Parameters for create action."""
    _tool_description: ClassVar[str] = (
        "create: Create a new empty Anki deck. Supports parent::child nesting up to "
        "configured max_deck_depth (default 7). Returns deckId and created flag."
    )
    action: Literal["create"]
    deck_name: str = Field(description="Deck name (use '::' for nested decks, e.g., 'Spanish::Verbs')")


DeckManagementParams = Annotated[
    Union[
        RenameDeckParams, DeleteDecksParams, ExportDecksParams,
        RestoreDecksParams, ListBackupsParams, CreateDeckParams,
    ],
    Field(discriminator="action"),
]


@Tool(
    "deck_management",
    _BASE_DESCRIPTION,  # Rebuilt dynamically at MCP registration
    write=True,
)
def deck_management(params: DeckManagementParams) -> dict[str, Any]:
    """Dispatcher for deck management operations."""
    match params.action:
        case "rename":
            return rename_deck_impl(deck=params.deck, new_name=params.new_name)
        case "delete":
            return delete_decks_impl(
                decks=params.decks,
                cards_too=params.cards_too,
                confirm=params.confirm,
            )
        case "export":
            return export_decks_impl()
        case "restore":
            return restore_decks_impl(
                file_path=params.file_path,
                confirm=params.confirm,
            )
        case "list_backups":
            return list_backups_impl()
        case "create":
            return create_deck_impl(deck_name=params.deck_name)
        case _:
            raise HandlerError(f"Unknown action: {params.action}")
