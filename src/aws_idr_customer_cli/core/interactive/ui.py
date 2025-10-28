from contextlib import contextmanager
from typing import Any, Dict, Generic, Iterator, List, Optional, Tuple, TypeVar, cast

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, TaskID
from rich.prompt import Confirm

T = TypeVar("T")


class InteractiveUI(Generic[T]):
    """Enhanced UI components for interactive workflows."""

    def __init__(self) -> None:
        self.console = Console()
        self._silent_mode = False

    def set_silent_mode(self, silent: bool) -> None:
        """Enable/disable silent mode."""
        self._silent_mode = silent

    def display_header(self, title: str, description: Optional[str] = None) -> None:
        """Display a consistent header."""
        if self._silent_mode:
            return
        self.console.print(f"\n[bold]{title}[/bold]")
        if description:
            self.console.print(description)
        self.console.print("─" * (len(description or title)))

    def display_info(self, message: str, style: str = "green") -> None:
        if self._silent_mode:
            return
        self.console.print(f"\n[{style}]{message}[/{style}]")

    def display_warning(self, message: str) -> None:
        if self._silent_mode:
            return
        self.console.print(f"\n[bold yellow]⚠️  {message}[/bold yellow]")

    def display_error(self, message: str) -> None:
        if self._silent_mode:
            return
        self.console.print(f"\n[bold red]❌ {message}[/bold red]")

    def ask_select(
        self, message: str, choices: List[str], default: Optional[str] = None
    ) -> str:
        return cast(
            str,
            questionary.select(
                f"{message}", choices=choices, default=default, qmark="→"
            ).unsafe_ask(),
        )

    def ask_text(self, message: str, qmark: str = "→") -> str:
        return cast(str, questionary.text(f"{message}:", qmark=qmark).unsafe_ask())

    def prompt_input(
        self,
        message: str,
        default: Optional[str] = None,
        choices: Optional[List[str]] = None,
    ) -> str:
        if choices:
            return self.ask_select(message, choices, default)
        else:
            if default:
                self.console.print(f"→ {message} [cyan]({default})[/cyan]", end="")
                result = self.ask_text("", qmark="")
            else:
                result = self.ask_text(message)

            return result or default or ""

    @staticmethod
    def prompt_confirm(message: str, default: bool = True) -> bool:
        """Prompt confirmation."""
        return Confirm.ask(f"→ {message}", default=default)

    def select_option(
        self,
        options: List[str],
        message: str = "Select an option",
        explicit_index: bool = False,
        max_choice_number: Optional[int] = None,
    ) -> int:
        """
        Select from numbered options.
        explicit_index: if index is coming as part of option itself
        """
        self.console.print(f"\n{message}:")

        for i, option in enumerate(options, 1):
            if explicit_index:
                self.console.print(f"  {option}")
            else:
                self.console.print(f"  {i}. {option}")

        max_choice = max_choice_number if max_choice_number else len(options)

        while True:
            try:
                choice_range = f"1-{max_choice}"
                choice = int(self.prompt_input("Enter your choice", choice_range))
                if 1 <= choice <= max_choice:
                    return choice - 1
            except ValueError:
                pass

            self.console.print("[red]Invalid selection. Try again.[/red]")

    def display_resource_summary(self, resources: List[Dict[str, Any]]) -> None:
        """Display resource summary by service."""
        if not resources:
            self.console.print("\nNo resources found.")
            return

        # Group by service
        by_service: Dict[str, List[Dict[str, Any]]] = {}
        for r in resources:
            service = r["service"]
            if service not in by_service:
                by_service[service] = []
            by_service[service].append(r)

        # Display summary
        self.console.print(f"\nFound {len(resources)} resources:")

        for service, items in by_service.items():
            self.console.print(f"\n[bold]{service}[/bold] ({len(items)})")

            for item in items[:5]:  # Show first 5 per service
                self.console.print(
                    f"  • {item['name']} • {item['type']} • {item['status']}"
                )

            if len(items) > 5:
                self.console.print(f"  • ... and {len(items) - 5} more")

    @staticmethod
    def progress_bar(message: str, total: int = 100) -> Tuple[Progress, TaskID]:
        """Create a progress bar."""
        progress = Progress()
        task = progress.add_task(message, total=total)
        return progress, task

    def display_result(self, title: str, data: Dict[str, Any]) -> None:
        """Display operation result."""
        if self._silent_mode:
            return
        panel = Panel(
            "\n".join(f"{k}: {v}" for k, v in data.items()),
            title=title,
            border_style="green",
        )
        self.console.print(panel)

    @contextmanager
    def unsilenced_output(self) -> Iterator[None]:
        """Temporarily disable silent mode for output."""
        self.set_silent_mode(False)
        try:
            yield
        finally:
            self.set_silent_mode(True)
