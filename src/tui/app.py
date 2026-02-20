"""Main DocForge TUI application — Claude Code-style layout using curses."""

import curses
import curses.textpad

from src.tui.state import AppState
from src.tui.panels import (
    draw_header,
    draw_sources_panel,
    draw_outline_panel,
    draw_log_panel,
    draw_input_bar,
    draw_command_popup,
)
from src.tui.watcher import FileWatcher
from src.tui.commands import (
    parse_command,
    handle_title,
    handle_intro,
    handle_import,
    handle_chapter,
    handle_remove,
    handle_reset,
    handle_help,
    handle_quit,
    handle_generate,
    COMMAND_DESCRIPTIONS,
)


SLASH_COMMANDS = list(COMMAND_DESCRIPTIONS.keys())


class DocForgeApp:
    """Main TUI application — full-terminal, Claude Code-style."""

    def __init__(self, state: AppState, watcher: FileWatcher):
        self.state = state
        self.watcher = watcher
        self._running = True

    # ------------------------------------------------------------------ #
    #  Input helpers
    # ------------------------------------------------------------------ #

    def _handle_input(self, stdscr, input_buf: list[str]) -> tuple[str | None, bool]:
        """
        Read one character and mutate the input buffer.

        Returns (submitted_line_or_None, should_quit).
        """
        key = stdscr.get_wch()

        if key in (curses.KEY_ENTER, "\n", "\r"):
            line = "".join(input_buf)
            input_buf.clear()
            return line, False

        elif key in (curses.KEY_BACKSPACE, "\x7f", "\b"):
            if input_buf:
                input_buf.pop()

        elif key == "\x1b":          # ESC → clear buffer
            input_buf.clear()

        elif isinstance(key, str) and key.isprintable():
            input_buf.append(key)

        return None, False

    # ------------------------------------------------------------------ #
    #  Command execution
    # ------------------------------------------------------------------ #

    def _execute_command(self, raw: str) -> bool:
        """Execute a command string. Returns False when app should quit."""
        cmd = parse_command(raw)
        if cmd is None:
            self.state.log_lines.append(f"Unknown command: {raw}  (try /help)")
            return True

        if cmd.name == "title":
            handle_title(self.state, cmd.args)
        elif cmd.name == "intro":
            handle_intro(self.state, cmd.args)
        elif cmd.name == "import":
            handle_import(self.state, cmd.args)
        elif cmd.name == "chapter":
            handle_chapter(self.state, cmd.args)
        elif cmd.name == "remove":
            handle_remove(self.state, cmd.args)
        elif cmd.name == "reset":
            handle_reset(self.state)
        elif cmd.name == "help":
            handle_help(self.state)
        elif cmd.name == "generate":
            handle_generate(self.state)
        elif cmd.name == "quit":
            running_ref = [True]
            handle_quit(self.state, running_ref)
            return False

        return True

    # ------------------------------------------------------------------ #
    #  Main curses loop
    # ------------------------------------------------------------------ #

    def _main(self, stdscr):
        curses.curs_set(0)
        stdscr.nodelay(True)          # non-blocking getch
        stdscr.keypad(True)

        # ── Colour pairs ──────────────────────────────────────────────
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1,  curses.COLOR_WHITE,   curses.COLOR_BLUE)    # header bg
        curses.init_pair(2,  curses.COLOR_CYAN,    -1)                   # border / accent
        curses.init_pair(3,  curses.COLOR_GREEN,   -1)                   # success / found
        curses.init_pair(4,  curses.COLOR_YELLOW,  -1)                   # warn / outline
        curses.init_pair(5,  curses.COLOR_WHITE,   -1)                   # normal text
        curses.init_pair(6,  curses.COLOR_BLACK,   curses.COLOR_WHITE)   # popup bg
        curses.init_pair(7,  curses.COLOR_MAGENTA, -1)                   # prompt >
        curses.init_pair(8,  curses.COLOR_RED,     -1)                   # error
        curses.init_pair(9,  curses.COLOR_WHITE,   curses.COLOR_CYAN)    # popup selected
        curses.init_pair(10, curses.COLOR_BLACK,   curses.COLOR_YELLOW)  # status bar

        input_buf: list[str] = []

        self.state.log_lines.append("DocForge ready — type /help for commands")

        while self._running:
            # ── Check terminal size ────────────────────────────────────
            h, w = stdscr.getmaxyx()
            if h < 20 or w < 60:
                stdscr.clear()
                msg = "Terminal too small — please resize"
                stdscr.addstr(h // 2, max(0, (w - len(msg)) // 2), msg)
                stdscr.refresh()
                curses.napms(200)
                try:
                    self._handle_input(stdscr, input_buf)
                except Exception:
                    pass
                continue

            # ── Pipeline completion check ──────────────────────────────
            if self.state.pipeline_complete.is_set():
                self.state.pipeline_complete.clear()

            # ── Layout maths ──────────────────────────────────────────
            #
            #  ┌─ header (1 row) ────────────────────────────────────────┐
            #  │ Sources (left, 30%)  │ Outline (right, 70%)             │
            #  ├──────────────────────┤                                   │
            #  │ Log (full width, ~8 rows)                                │
            #  ├─────────────────────────────────────────────────────────┤
            #  │ status bar (1 row)                                       │
            #  │ input bar  (1 row)                                       │
            #  └─────────────────────────────────────────────────────────┘

            HEADER_H    = 2
            INPUT_H     = 3          # status + prompt
            LOG_H       = min(12, max(6, h // 5))
            BODY_H      = h - HEADER_H - LOG_H - INPUT_H
            SRC_W       = max(24, w * 30 // 100)
            OUT_W       = w - SRC_W

            src_top     = HEADER_H
            src_left    = 0
            out_top     = HEADER_H
            out_left    = SRC_W
            log_top     = HEADER_H + BODY_H
            log_left    = 0
            bar_top     = h - INPUT_H
            bar_left    = 0

            stdscr.erase()

            # ── Draw panels ───────────────────────────────────────────
            draw_header(stdscr, 0, 0, w)
            draw_sources_panel(stdscr, src_top, src_left, BODY_H, SRC_W, self.state)
            draw_outline_panel(stdscr, out_top, out_left, BODY_H, OUT_W, self.state)
            draw_log_panel(stdscr, log_top, log_left, LOG_H, w, self.state)
            draw_input_bar(stdscr, bar_top, bar_left, INPUT_H, w, input_buf)

            # ── Command popup ─────────────────────────────────────────
            current = "".join(input_buf)
            if current.startswith("/") and len(current) >= 1:
                prefix = current[1:]
                matches = [
                    (cmd, COMMAND_DESCRIPTIONS[cmd])
                    for cmd in SLASH_COMMANDS
                    if cmd.startswith(prefix)
                ]
                if matches:
                    draw_command_popup(
                        stdscr,
                        bar_top - len(matches) - 2,
                        2,
                        matches,
                        prefix,
                    )

            stdscr.refresh()

            # ── Input ─────────────────────────────────────────────────
            curses.napms(16)          # ~60 fps cap
            try:
                line, quit_now = self._handle_input(stdscr, input_buf)
            except curses.error:
                continue

            if quit_now:
                break

            if line is not None and line.strip():
                should_continue = self._execute_command(line.strip())
                if not should_continue:
                    break

    def run(self):
        """Start the TUI application."""
        try:
            curses.wrapper(self._main)
        except KeyboardInterrupt:
            pass
        print("\033[1;32mGoodbye!\033[0m")