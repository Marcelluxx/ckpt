"""Interactive terminal selection menu for checkpoint restoration.

Provides a lightweight, terminal-native selection list that operates inline
without requiring a full-screen TUI. Uses ANSI escape codes for clean,
flicker-free updates and supports cross-platform raw keyboard input.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ckpt.models import Checkpoint

# ---------------------------------------------------------------------------
# Cross-Platform Keyboard Input Handlers
# ---------------------------------------------------------------------------

if sys.platform == "win32":
    import msvcrt

    def _get_keypress() -> str:
        """Read a single keypress on Windows systems.

        Returns:
            A string identifier: "up", "down", "enter", "escape", "ctrl-c", or "".
        """
        if not msvcrt.kbhit():
            # Wait for a key to be pressed
            pass
        ch = msvcrt.getch()
        # Handle special/arrow keys which start with 0x00 or 0xE0
        if ch in (b"\x00", b"\xe0"):
            ch2 = msvcrt.getch()
            if ch2 == b"H":  # Arrow Up
                return "up"
            elif ch2 == b"P":  # Arrow Down
                return "down"
            return ""
        if ch in (b"\r", b"\n"):
            return "enter"
        if ch == b"\x1b":
            return "escape"
        if ch == b"\x03":  # Ctrl+C
            return "ctrl-c"
        try:
            char = ch.decode("utf-8", errors="ignore").lower()
            if char == "k":
                return "up"
            elif char == "j":
                return "down"
        except Exception:
            pass
        return ""
else:
    import select
    import termios
    import tty

    def _get_keypress() -> str:
        """Read a single keypress on Unix/macOS systems using raw mode termios.

        Returns:
            A string identifier: "up", "down", "enter", "escape", "ctrl-c", or "".
        """
        fd = sys.stdin.fileno()
        if not sys.stdin.isatty():
            return ""

        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                # Check if this is the start of an escape sequence (e.g. arrow keys)
                r, _, _ = select.select([sys.stdin], [], [], 0.05)
                if r:
                    ch2 = sys.stdin.read(1)
                    if ch2 == "[":
                        ch3 = sys.stdin.read(1)
                        if ch3 == "A":  # Arrow Up
                            return "up"
                        elif ch3 == "B":  # Arrow Down
                            return "down"
                return "escape"
            elif ch in ("\r", "\n"):
                return "enter"
            elif ch == "\x03":  # Ctrl+C
                return "ctrl-c"
            elif ch.lower() == "k":
                return "up"
            elif ch.lower() == "j":
                return "down"
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ""


# ---------------------------------------------------------------------------
# Utility Helpers
# ---------------------------------------------------------------------------


def format_relative_time(timestamp: datetime) -> str:
    """Format a timezone-aware timestamp into a human-readable relative time string.

    Args:
        timestamp: The timezone-aware datetime of the checkpoint creation.

    Returns:
        A human-readable relative time string, e.g. "just now", "2 hours ago", etc.
    """
    now = datetime.now(timezone.utc)
    delta = now - timestamp
    seconds = int(delta.total_seconds())

    if seconds < 60:
        return "just now"

    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minutes ago" if minutes > 1 else "1 minute ago"

    hours = minutes // 60
    if hours < 24:
        return f"{hours} hours ago" if hours > 1 else "1 hour ago"

    days = hours // 24
    return f"{days} days ago" if days > 1 else "1 day ago"


def _hide_cursor() -> None:
    """Send ANSI escape sequence to hide the terminal cursor."""
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()


def _show_cursor() -> None:
    """Send ANSI escape sequence to show the terminal cursor."""
    sys.stdout.write("\033[?25h")
    sys.stdout.flush()


def _clear_lines(n: int) -> None:
    """Clear n lines up from the current cursor position.

    Args:
        n: Number of lines to clear.
    """
    if n <= 0:
        return
    sys.stdout.write("\r" + "\033[A\033[K" * n)
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Interactive Selection Menu
# ---------------------------------------------------------------------------


def select_checkpoint_interactive(checkpoints: list[Checkpoint]) -> str | None:
    """Display an interactive terminal menu for choosing a checkpoint.

    Renders a clean inline selection list in stdout, listens to real-time arrow
    keys, and allows selecting or canceling gracefully.

    Args:
        checkpoints: Sorted list of checkpoints.

    Returns:
        The 8-character ID of the selected checkpoint, or None if cancelled.
    """
    if not checkpoints:
        return None

    # Limit display list size to avoid overflow on standard terminal screens
    max_display = 15
    truncated = len(checkpoints) > max_display
    menu_items = checkpoints[:max_display]

    selected_idx = 0
    num_lines = len(menu_items)
    if truncated:
        num_lines += 1  # Add one line for the truncated footer notice

    _hide_cursor()
    try:
        import shutil

        while True:
            # Query terminal size to dynamically prevent wrapping
            cols, _ = shutil.get_terminal_size()

            # Render menu
            lines = []
            for idx, cp in enumerate(menu_items):
                rel_time = format_relative_time(cp.timestamp)
                branch_part = f"(branch: {cp.branch})"

                # Calculate visible width limit
                # We need at least 15 chars for message, the prefix of 33, and the branch part (plus 2 margin)
                min_width_for_branch = 33 + 15 + 1 + len(branch_part) + 2

                if cols >= min_width_for_branch:
                    # Show branch
                    max_msg_len = cols - 2 - 33 - 1 - len(branch_part)
                    msg = cp.message
                    if len(msg) > max_msg_len:
                        msg = (
                            msg[: max_msg_len - 3] + "..."
                            if max_msg_len > 3
                            else msg[:max_msg_len]
                        )

                    if idx == selected_idx:
                        # Highlighted/selected style
                        indicator = "\033[1;35m❯\033[0m"  # Bold Magenta
                        cp_id = f"\033[1;36m[{cp.id}]\033[0m"  # Bold Cyan
                        time_str = f"\033[1;33m{rel_time:<14}\033[0m"  # Bold Yellow
                        msg_str = f"\033[1;37m{msg}\033[0m"  # Bold White
                        branch_str = f"\033[1;34m{branch_part}\033[0m"  # Bold Blue
                    else:
                        # Dimmed/unselected style
                        indicator = " "
                        cp_id = f"\033[2;37m[{cp.id}]\033[0m"  # Dim Gray
                        time_str = f"\033[2;37m{rel_time:<14}\033[0m"  # Dim Gray
                        msg_str = f"\033[2;37m{msg}\033[0m"  # Dim Gray
                        branch_str = f"\033[2;37m{branch_part}\033[0m"  # Dim Gray

                    lines.append(
                        f"{indicator} {cp_id}  {time_str}  -  {msg_str} {branch_str}"
                    )
                else:
                    # Hide branch to save space
                    max_msg_len = cols - 2 - 33
                    msg = cp.message
                    if len(msg) > max_msg_len:
                        msg = (
                            msg[: max_msg_len - 3] + "..."
                            if max_msg_len > 3
                            else msg[:max_msg_len]
                        )

                    if idx == selected_idx:
                        # Highlighted/selected style
                        indicator = "\033[1;35m❯\033[0m"  # Bold Magenta
                        cp_id = f"\033[1;36m[{cp.id}]\033[0m"  # Bold Cyan
                        time_str = f"\033[1;33m{rel_time:<14}\033[0m"  # Bold Yellow
                        msg_str = f"\033[1;37m{msg}\033[0m"  # Bold White
                    else:
                        # Dimmed/unselected style
                        indicator = " "
                        cp_id = f"\033[2;37m[{cp.id}]\033[0m"  # Dim Gray
                        time_str = f"\033[2;37m{rel_time:<14}\033[0m"  # Dim Gray
                        msg_str = f"\033[2;37m{msg}\033[0m"  # Dim Gray

                    lines.append(f"{indicator} {cp_id}  {time_str}  -  {msg_str}")

            if truncated:
                extra_count = len(checkpoints) - max_display
                footer_text = f"... and {extra_count} more checkpoints (specify ID directly to restore)"
                max_footer_len = cols - 5
                if len(footer_text) > max_footer_len:
                    footer_text = (
                        footer_text[: max_footer_len - 3] + "..."
                        if max_footer_len > 3
                        else footer_text[:max_footer_len]
                    )
                lines.append(f"  \033[2;37m{footer_text}\033[0m")

            # Draw lines
            sys.stdout.write("\n".join(lines) + "\n")
            sys.stdout.flush()

            # Read key
            try:
                key = _get_keypress()
            except KeyboardInterrupt:
                _clear_lines(num_lines)
                return None

            if key == "up":
                selected_idx = (selected_idx - 1) % len(menu_items)
            elif key == "down":
                selected_idx = (selected_idx + 1) % len(menu_items)
            elif key == "enter":
                _clear_lines(num_lines)
                return menu_items[selected_idx].id
            elif key in ("escape", "ctrl-c"):
                _clear_lines(num_lines)
                return None

            # Clear drawn lines before drawing the next state
            _clear_lines(num_lines)

    finally:
        _show_cursor()


def select_option_interactive(options: list[tuple[str, str]], title: str) -> str | None:
    """Display an interactive terminal menu for choosing from a list of options.

    Renders a title and a list of options, listens to real-time arrow keys,
    and returns the selected option value.

    Args:
        options: A list of (value, display_label) tuples.
        title: Title/header message shown above the choices.

    Returns:
        The selected option value (string), or None if cancelled.
    """
    if not options:
        return None

    selected_idx = 0
    num_lines = len(options) + 1  # Options + Title line

    _hide_cursor()
    try:
        import shutil

        while True:
            cols, _ = shutil.get_terminal_size()

            lines = []
            # Title with Cyan color
            title_text = f"\033[1;36m{title}\033[0m"
            if len(title_text) > cols:
                title_text = title_text[: cols - 3] + "..."
            lines.append(title_text)

            for idx, (val, label) in enumerate(options):
                # Ensure each line fits the terminal width
                max_label_len = cols - 4
                disp_label = label
                if len(disp_label) > max_label_len:
                    disp_label = (
                        disp_label[: max_label_len - 3] + "..."
                        if max_label_len > 3
                        else disp_label[:max_label_len]
                    )

                if idx == selected_idx:
                    indicator = "\033[1;35m❯\033[0m"  # Bold Magenta
                    label_str = f"\033[1;37m{disp_label}\033[0m"  # Bold White
                else:
                    indicator = " "
                    label_str = f"\033[2;37m{disp_label}\033[0m"  # Dim Gray

                lines.append(f"{indicator}  {label_str}")

            # Draw lines
            sys.stdout.write("\n".join(lines) + "\n")
            sys.stdout.flush()

            # Read key
            try:
                key = _get_keypress()
            except KeyboardInterrupt:
                _clear_lines(num_lines)
                return None

            if key == "up":
                selected_idx = (selected_idx - 1) % len(options)
            elif key == "down":
                selected_idx = (selected_idx + 1) % len(options)
            elif key == "enter":
                _clear_lines(num_lines)
                return options[selected_idx][0]
            elif key in ("escape", "ctrl-c"):
                _clear_lines(num_lines)
                return None

            _clear_lines(num_lines)

    finally:
        _show_cursor()
