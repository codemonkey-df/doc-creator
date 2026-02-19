"""Main DocForge TUI application."""

from src.tui.state import AppState
from src.tui.panels import render_sources, render_outline, render_log
from src.tui.watcher import FileWatcher
from src.tui.commands import (
    parse_command,
    handle_title,
    handle_intro,
    handle_chapter,
    handle_remove,
    handle_reset,
    handle_help,
    handle_quit,
    handle_generate,
)


class DocForgeApp:
    """Main TUI application with live rendering."""

    def __init__(self, state: AppState, watcher: FileWatcher):
        self.state = state
        self.watcher = watcher
        self._input_buffer = ""
        self._running = True

    def _make_layout(self):
        """Create the layout structure (placeholder for future Rich Layout)."""
        return None

    def _clear_screen(self):
        """Clear the terminal screen."""
        print("\033[2J\033[H", end="")

    def _render(self) -> str:
        """Render all panels and return the string display."""
        from io import StringIO
        from rich.console import Console

        # Render each panel to a string with specific widths
        sources_io = StringIO()
        console_s = Console(file=sources_io, width=28, force_terminal=True)
        console_s.print(render_sources(self.state))
        sources_str = sources_io.getvalue().rstrip()

        outline_io = StringIO()
        console_o = Console(file=outline_io, width=28, force_terminal=True)
        console_o.print(render_outline(self.state))
        outline_str = outline_io.getvalue().rstrip()

        log_io = StringIO()
        console_l = Console(file=log_io, width=58, force_terminal=True)
        console_l.print(render_log(self.state))
        log_str = log_io.getvalue().rstrip()

        # Build the final display
        display = []
        display.append(
            "\033[1;37;44m" + " DocForge - Document Creator ".center(60) + "\033[0m"
        )
        display.append("")

        # Two column layout for sources and outline
        sources_lines = sources_str.split("\n")
        outline_lines = outline_str.split("\n")
        max_rows = max(len(sources_lines), len(outline_lines))

        for i in range(max_rows):
            s = sources_lines[i] if i < len(sources_lines) else ""
            o = outline_lines[i] if i < len(outline_lines) else ""
            display.append(f"{s:<28} {o}")

        display.append("")
        display.append("\033[90m" + "─" * 60 + "\033[0m")
        display.append("\033[1mLOG\033[0m")
        display.append("\033[90m" + "─" * 60 + "\033[0m")

        for line in log_str.split("\n"):
            display.append(line)

        display.append("")
        display.append(f"\033[1;36m> {self._input_buffer}\033[0m")

        return "\n".join(display)

    def _execute_command(self, raw: str) -> bool:
        """Parse and execute a command. Returns False if app should quit."""
        cmd = parse_command(raw)
        if cmd is None:
            self.state.log_lines.append(f"Unknown command: {raw}")
            return True

        if cmd.name == "title":
            handle_title(self.state, cmd.args)
        elif cmd.name == "intro":
            handle_intro(self.state, cmd.args)
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
            handle_quit(self.state, [self._running])
            return False

        return True

    def run(self):
        """Start the TUI application."""
        # Initial render
        self._clear_screen()
        print(self._render())
        print(
            "\n\033[1;33mType a command and press Enter. Try /help for available commands.\033[0m"
        )

        try:
            while self._running:
                # Use standard input() - user will see what they type
                try:
                    line = input("\n> ")
                except EOFError:
                    break

                if line.strip():
                    should_continue = self._execute_command(line)
                    if not should_continue:
                        break

                # Redraw screen after command execution
                if self._running:
                    self._clear_screen()
                    print(self._render())

        except KeyboardInterrupt:
            print("\n\033[1;32mGoodbye!\033[0m")
