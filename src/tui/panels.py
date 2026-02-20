"""Panel drawing functions for DocForge TUI (curses-based)."""

from __future__ import annotations

import curses
from src.tui.state import AppState


# ═══════════════════════════════════════════════════════════════════════════ #
#  Low-level helpers
# ═══════════════════════════════════════════════════════════════════════════ #

def _safe_addstr(win, y: int, x: int, text: str, attr: int = 0) -> None:
    """addstr that silently ignores out-of-bounds writes."""
    try:
        h, w = win.getmaxyx()
        if y < 0 or y >= h or x < 0 or x >= w:
            return
        max_len = w - x - 1
        if max_len <= 0:
            return
        win.addstr(y, x, text[:max_len], attr)
    except curses.error:
        pass


def _draw_box(win, top: int, left: int, height: int, width: int,
              title: str = "", attr: int = 0) -> None:
    """Draw a rounded box with optional title."""
    if height < 2 or width < 4:
        return
    h, w = win.getmaxyx()

    # corners & edges (use ASCII fallback if Unicode fails)
    TL, TR, BL, BR = "╭", "╮", "╰", "╯"
    H, V = "─", "│"

    def put(y, x, ch, a=0):
        if 0 <= y < h and 0 <= x < w - 1:
            try:
                win.addstr(y, x, ch, a)
            except curses.error:
                pass

    # top border
    put(top, left, TL, attr)
    inner = width - 2
    if title:
        label = f" {title} "
        pad = inner - len(label)
        left_pad = pad // 2
        right_pad = pad - left_pad
        border_top = H * left_pad + label + H * right_pad
    else:
        border_top = H * inner
    for i, ch in enumerate(border_top[:inner]):
        put(top, left + 1 + i, ch, attr)
    put(top, left + width - 1, TR, attr)

    # sides
    for row in range(1, height - 1):
        put(top + row, left, V, attr)
        put(top + row, left + width - 1, V, attr)

    # bottom
    put(top + height - 1, left, BL, attr)
    for i in range(inner):
        put(top + height - 1, left + 1 + i, H, attr)
    put(top + height - 1, left + width - 1, BR, attr)


# ═══════════════════════════════════════════════════════════════════════════ #
#  Public panel drawers
# ═══════════════════════════════════════════════════════════════════════════ #

def draw_header(win, top: int, left: int, width: int) -> None:
    """Full-width title bar (2 rows)."""
    attr_bg  = curses.color_pair(1) | curses.A_BOLD
    attr_sub = curses.color_pair(2)

    title = " ⚡ DocForge"
    subtitle = "Document Creator"

    # Row 0 — coloured background bar
    try:
        win.addstr(top, left, " " * width, attr_bg)
        win.addstr(top, left + 1, title, attr_bg)
        # right-align subtitle
        sub_x = max(left + len(title) + 2, width - len(subtitle) - 2)
        win.addstr(top, sub_x, subtitle, attr_bg)
    except curses.error:
        pass

    # Row 1 — thin separator
    sep = "─" * (width - 1)
    _safe_addstr(win, top + 1, left, sep, curses.color_pair(2))


def draw_sources_panel(win, top: int, left: int, height: int, width: int,
                        state: AppState) -> None:
    """Left column: numbered list of detected markdown files."""
    border_attr = curses.color_pair(2)
    title_attr  = curses.color_pair(2) | curses.A_BOLD
    used_attr   = curses.color_pair(3)          # green ✓
    num_attr    = curses.color_pair(4)           # yellow index
    dim_attr    = curses.A_DIM

    _draw_box(win, top, left, height, width, title=" Sources ", attr=border_attr)

    inner_w = width - 4
    row = top + 1

    if not state.detected_files:
        _safe_addstr(win, row, left + 2, "(no .md files detected)", dim_attr)
        return

    for idx, filepath in enumerate(state.detected_files, start=1):
        if row >= top + height - 1:
            _safe_addstr(win, row, left + 2, "…", dim_attr)
            break

        is_intro   = filepath == state.intro_file
        is_chapter = any(c.file_path == filepath for c in state.chapters)
        used       = is_intro or is_chapter

        # index badge
        badge = f"[{idx:>2}]"
        _safe_addstr(win, row, left + 2, badge, num_attr)

        # filename (truncated)
        name_x   = left + 2 + len(badge) + 1
        max_name = inner_w - len(badge) - 3
        name     = filepath[:max_name]

        if used:
            _safe_addstr(win, row, name_x, name, used_attr)
            tag = " ✓I" if is_intro else " ✓C"
            _safe_addstr(win, row, name_x + len(name), tag, used_attr | curses.A_BOLD)
        else:
            _safe_addstr(win, row, name_x, name)

        row += 1


def draw_outline_panel(win, top: int, left: int, height: int, width: int,
                        state: AppState) -> None:
    """Right column: document outline — title, intro, chapters."""
    border_attr  = curses.color_pair(4)
    label_attr   = curses.color_pair(4) | curses.A_BOLD
    value_attr   = curses.color_pair(5) | curses.A_BOLD
    chapter_attr = curses.color_pair(3)
    dim_attr     = curses.A_DIM
    accent_attr  = curses.color_pair(2)

    _draw_box(win, top, left, height, width, title=" Outline ", attr=border_attr)

    inner_w = width - 4
    row     = top + 1

    def put_row(label: str, value: str, la=label_attr, va=value_attr):
        nonlocal row
        if row >= top + height - 1:
            return
        _safe_addstr(win, row, left + 2, label, la)
        vx = left + 2 + len(label)
        _safe_addstr(win, row, vx, value[:max(0, inner_w - len(label))], va)
        row += 1

    # ── Title ─────────────────────────────────────────────────────────
    put_row("Title  ", state.title or "(untitled)")

    # ── Intro ─────────────────────────────────────────────────────────
    if state.intro_file:
        put_row("Intro  ", state.intro_file, va=chapter_attr)
    else:
        put_row("Intro  ", "(not set)", va=dim_attr)

    # ── Separator ─────────────────────────────────────────────────────
    if row < top + height - 1:
        _safe_addstr(win, row, left + 2, "─" * (inner_w), accent_attr | curses.A_DIM)
        row += 1

    # ── Chapters ──────────────────────────────────────────────────────
    if not state.chapters:
        if row < top + height - 1:
            _safe_addstr(win, row, left + 2, "Chapters  (none)", dim_attr)
    else:
        if row < top + height - 1:
            _safe_addstr(win, row, left + 2, "Chapters", label_attr)
            row += 1

        for i, ch in enumerate(state.chapters, start=1):
            if row >= top + height - 1:
                _safe_addstr(win, row, left + 2, "  …", dim_attr)
                break
            title = ch.custom_title or ch.file_path
            line  = f"  {i}. {title}"
            _safe_addstr(win, row, left + 2,
                         line[:inner_w], chapter_attr)
            row += 1


def draw_log_panel(win, top: int, left: int, height: int, width: int,
                   state: AppState) -> None:
    """Full-width log panel at the bottom."""
    border_attr = curses.color_pair(7)
    dim_attr    = curses.A_DIM
    err_attr    = curses.color_pair(8)

    _draw_box(win, top, left, height, width, title=" Log ", attr=border_attr)

    inner_h = height - 2
    inner_w = width - 4
    visible = state.log_lines[-inner_h:]

    for i, line in enumerate(visible):
        row = top + 1 + i
        # simple heuristic: lines containing 'error'/'invalid'/'unknown' → red
        low = line.lower()
        if any(w in low for w in ("error", "invalid", "unknown", "fail")):
            attr = err_attr
        elif line.startswith("DocForge") or line.startswith("Starting"):
            attr = curses.color_pair(3)
        elif line.startswith("  "):          # help indented lines
            attr = dim_attr
        else:
            attr = curses.color_pair(5)

        _safe_addstr(win, row, left + 2, line[:inner_w], attr)


def draw_input_bar(win, top: int, left: int, height: int, width: int,
                   input_buf: list[str]) -> None:
    """
    Bottom input area:
      row 0 — thin divider + key hints
      row 1 — prompt line  ">  <cursor>"
      row 2 — blank padding
    """
    h, w = win.getmaxyx()

    # Row 0: status/hint bar
    hints = " /help · /generate · /quit "
    hint_x = max(left, width - len(hints) - 1)
    status = "─" * (hint_x - left)
    _safe_addstr(win, top, left, status, curses.color_pair(2) | curses.A_DIM)
    _safe_addstr(win, top, hint_x, hints, curses.color_pair(10))

    # Row 1: prompt
    prompt       = "❯ "
    prompt_attr  = curses.color_pair(7) | curses.A_BOLD
    text         = "".join(input_buf)
    text_attr    = curses.color_pair(5) | curses.A_BOLD

    if top + 1 < h:
        _safe_addstr(win, top + 1, left + 1, prompt, prompt_attr)
        px = left + 1 + len(prompt)
        _safe_addstr(win, top + 1, px, text, text_attr)

        # Block cursor  ▌
        cursor_x = px + len(text)
        if cursor_x < width - 1:
            try:
                win.addstr(top + 1, cursor_x, "▌",
                           curses.color_pair(7) | curses.A_BLINK)
            except curses.error:
                pass


def draw_command_popup(win, top: int, left: int,
                       matches: list[tuple[str, str]],
                       prefix: str) -> None:
    """
    Floating autocomplete popup above the input bar.

    matches = [("title", "Set document title"), ...]
    prefix  = currently typed portion after the /
    """
    if not matches:
        return

    h, w = win.getmaxyx()

    max_cmd  = max(len(m[0]) for m in matches)
    max_desc = max(len(m[1]) for m in matches)
    box_w    = max_cmd + max_desc + 7   # "  /cmd  desc  "
    box_h    = len(matches) + 2         # border top + border bottom

    # clamp position
    if top < 0:
        top = 0
    if left + box_w >= w:
        left = max(0, w - box_w - 1)

    bg_attr      = curses.color_pair(6)
    cmd_attr     = curses.color_pair(9) | curses.A_BOLD
    desc_attr    = curses.color_pair(6)
    prefix_attr  = curses.color_pair(9) | curses.A_BOLD | curses.A_UNDERLINE
    border_attr  = curses.color_pair(2)

    # draw background + border
    for r in range(box_h):
        _safe_addstr(win, top + r, left, " " * box_w, bg_attr)
    _draw_box(win, top, left, box_h, box_w, attr=border_attr)

    for i, (cmd, desc) in enumerate(matches):
        row = top + 1 + i
        # highlight the typed prefix portion inside the command
        x = left + 2
        slash_attr = desc_attr

        # "/"
        _safe_addstr(win, row, x, "/", slash_attr)
        x += 1

        # prefix part (underlined match)
        if prefix and cmd.startswith(prefix):
            _safe_addstr(win, row, x, prefix, prefix_attr)
            x += len(prefix)
            remainder = cmd[len(prefix):]
            _safe_addstr(win, row, x, remainder, cmd_attr)
            x += len(remainder)
        else:
            _safe_addstr(win, row, x, cmd, cmd_attr)
            x += len(cmd)

        # padding between cmd and desc
        pad = max_cmd - len(cmd) + 2
        x += pad

        # description (dim)
        _safe_addstr(win, row, x, desc[:max(0, box_w - (x - left) - 2)], desc_attr)