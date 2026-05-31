"""Interactive Terminal User Interface for checkpoint selection.

Provides a Textual-based TUI that displays all saved checkpoints in a
scrollable list with a live detail panel showing the Mental Map of the
currently highlighted item.  The user confirms a selection with Enter,
and the chosen ``snapshot_id`` is returned to the calling script.
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.widgets import Footer, Header, ListItem, ListView, Markdown, Static

from ckpt.models import Checkpoint
from ckpt.store import list_checkpoints

# ---------------------------------------------------------------------------
# Custom widgets
# ---------------------------------------------------------------------------


class SnapshotCard(Static):
    """A compact summary card rendered inside a ListItem.

    Displays the checkpoint ID, timestamp, branch, and message on two
    lines using Rich console markup.

    Attributes:
        checkpoint: The :class:`Checkpoint` this card represents.
    """

    def __init__(self, checkpoint: Checkpoint) -> None:
        self.checkpoint = checkpoint
        ts = checkpoint.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        label = (
            f"[bold cyan]{checkpoint.id}[/]  "
            f"[dim]{ts}[/]  "
            f"[italic]{checkpoint.branch}[/]\n"
            f"  {checkpoint.message}"
        )
        super().__init__(label, markup=True)


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------


class CheckpointSelector(App):
    """Textual TUI for browsing and selecting checkpoints.

    The app loads all stored checkpoints, presents them in a list, and
    shows the mental map of the highlighted checkpoint in a detail panel.
    Pressing Enter confirms the selection and exits the app, making the
    chosen ID available to the caller via :attr:`selected_id`.
    """

    TITLE = "ckpt - Checkpoint Selector"

    CSS = """
    Screen {
        background: $surface;
    }

    #main {
        height: 1fr;
    }

    #sidebar {
        width: 2fr;
        min-width: 30;
        border-right: solid $primary-lighten-2;
    }

    #sidebar-title {
        dock: top;
        height: 3;
        content-align: center middle;
        text-style: bold;
        color: $text;
        background: $primary-darken-2;
        padding: 0 1;
    }

    #snapshot-list {
        height: 1fr;
    }

    #snapshot-list > ListItem {
        padding: 1 1;
        height: auto;
    }

    #detail {
        width: 3fr;
        min-width: 40;
    }

    #detail-title {
        dock: top;
        height: 3;
        content-align: center middle;
        text-style: bold;
        color: $text;
        background: $primary-darken-2;
        padding: 0 1;
    }

    #mental-map {
        height: 1fr;
        padding: 1 2;
    }

    #empty-state {
        width: 1fr;
        height: 1fr;
        content-align: center middle;
        text-style: italic;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("escape", "quit", "Quit", show=True),
        Binding("enter", "select_checkpoint", "Confirm", show=True, priority=True),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
    ]

    selected_id: str | None = None
    """The ID of the checkpoint confirmed by the user, or ``None``."""

    def __init__(self) -> None:
        super().__init__()
        self._checkpoints: list[Checkpoint] = []

    def compose(self) -> ComposeResult:
        """Build the widget tree."""
        yield Header()

        self._checkpoints = list_checkpoints()

        if not self._checkpoints:
            yield Static(
                "No checkpoints found.\n\n"
                "Use [bold]ckpt save -m \"message\"[/] to create one.",
                id="empty-state",
                markup=True,
            )
        else:
            with Horizontal(id="main"):
                with Vertical(id="sidebar"):
                    yield Static(" Checkpoints", id="sidebar-title")
                    yield ListView(
                        *[
                            ListItem(SnapshotCard(cp))
                            for cp in self._checkpoints
                        ],
                        id="snapshot-list",
                    )
                with Vertical(id="detail"):
                    yield Static(" Mental Map", id="detail-title")
                    with VerticalScroll(id="mental-map"):
                        yield Markdown("", id="detail-content")

        yield Footer()

    def on_mount(self) -> None:
        """Set initial focus and load first checkpoint detail."""
        if self._checkpoints:
            self._show_detail(self._checkpoints[0])

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Update the detail panel when the highlight moves."""
        if event.item is None:
            return
        card = event.item.query_one(SnapshotCard)
        self._show_detail(card.checkpoint)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle Enter key via ListView's native Selected message."""
        if event.item is None:
            return
        card = event.item.query_one(SnapshotCard)
        self.selected_id = card.checkpoint.id
        self.exit(self.selected_id)

    def action_select_checkpoint(self) -> None:
        """Confirm the currently highlighted checkpoint and exit.

        Fallback action bound to Enter at app level with ``priority=True``
        so it fires even when a child widget would otherwise consume it.
        """
        try:
            lv = self.query_one("#snapshot-list", ListView)
        except NoMatches:
            return
        if lv.highlighted_child is None:
            return
        card = lv.highlighted_child.query_one(SnapshotCard)
        self.selected_id = card.checkpoint.id
        self.exit(self.selected_id)

    def action_cursor_up(self) -> None:
        """Move the list cursor up."""
        self.query_one("#snapshot-list", ListView).action_cursor_up()

    def action_cursor_down(self) -> None:
        """Move the list cursor down."""
        self.query_one("#snapshot-list", ListView).action_cursor_down()

    def _show_detail(self, checkpoint: Checkpoint) -> None:
        """Render the checkpoint's mental map in the detail panel.

        Args:
            checkpoint: The checkpoint whose details to display.
        """
        md_widget = self.query_one("#detail-content", Markdown)

        lines: list[str] = []
        lines.append(f"**ID:** `{checkpoint.id}`  ")
        lines.append(
            f"**Time:** {checkpoint.timestamp:%Y-%m-%d %H:%M:%S UTC}  "
        )
        lines.append(f"**Branch:** `{checkpoint.branch}`  ")
        lines.append(
            f"**Commit:** `{checkpoint.commit_hash[:12]}`  "
        )
        lines.append(f"**Message:** {checkpoint.message}")
        lines.append("")

        if checkpoint.files_locked:
            lines.append("### Modified Files")
            for f in checkpoint.files_locked:
                lines.append(f"- `{f}`")
            lines.append("")

        if checkpoint.mental_map:
            lines.append("### Mental Map")
            lines.append(checkpoint.mental_map)
        else:
            lines.append(
                "*No mental map attached. "
                "Configure an LLM via `ckpt setup` to enable.*"
            )

        md_widget.update("\n".join(lines))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def select_checkpoint() -> str | None:
    """Launch the TUI and return the selected checkpoint ID.

    Returns:
        The 8-character ID chosen by the user, or ``None`` if the user
        quit without selecting.
    """
    app = CheckpointSelector()
    result = app.run()
    return result
