"""
Copartner CLI — Main Entry Point
==================================
The "God Mode Interface" for Asirive Copartner.
Runs a beautiful terminal chat with real-time streaming, token stats, and memory.

Usage:
    python -m copartner "Build a landing page for my coffee shop, Beanery"
    python -m copartner                          # Interactive REPL mode
    python -m copartner --status                 # Show token budget + memory stats

Features:
  - Real-time token streaming from ThoughtController
  - Rich terminal output with syntax highlighting
  - Token budget status in header
  - Memory recall preview before each answer
  - Skill recall notification when a known skill is reused
"""

import os
import sys
import argparse
import logging
from pathlib import Path

# Enforce UTF-8 encoding for Windows terminals
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# Load .env before anything else
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.live import Live
    from rich.spinner import Spinner
    from rich.table import Table
    from rich import print as rprint
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

logging.basicConfig(
    level=logging.WARNING,  # Keep logs quiet in CLI — use DEBUG for dev
    format="%(levelname)s | %(name)s | %(message)s",
)

BANNER = """
 ██████╗ ██████╗ ██████╗  █████╗ ██████╗ ████████╗███╗   ██╗███████╗██████╗ 
██╔════╝██╔═══██╗██╔══██╗██╔══██╗██╔══██╗╚══██╔══╝████╗  ██║██╔════╝██╔══██╗
██║     ██║   ██║██████╔╝███████║██████╔╝   ██║   ██╔██╗ ██║█████╗  ██████╔╝
██║     ██║   ██║██╔═══╝ ██╔══██║██╔══██╗   ██║   ██║╚██╗██║██╔══╝  ██╔══██╗
╚██████╗╚██████╔╝██║     ██║  ██║██║  ██║   ██║   ██║ ╚████║███████╗██║  ██║
 ╚═════╝ ╚═════╝ ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝
                          by Asirive — One Human. Infinite Studio.
"""


def _create_controller():
    """Initialize ThoughtController with all dependencies."""
    from core.thought_controller import ThoughtController
    return ThoughtController.create()


def _print_status(controller):
    """Print token budget and memory statistics."""
    if not RICH_AVAILABLE:
        print("Install rich for better output: pip install rich")
        return

    console = Console()

    # Token budget
    if controller.budget:
        status = controller.budget.status()
        t = Table(title="💰 Token Budget", show_header=True)
        t.add_column("Metric", style="cyan")
        t.add_column("Value", style="white")
        t.add_row("Date",         status["date"])
        t.add_row("Tokens Used",  f"{status['tokens_used']:,}")
        t.add_row("Daily Limit",  f"{status['daily_limit']:,}")
        t.add_row("% Used",       status["pct_used"])
        t.add_row("Cost Today",   status["cost_today"])
        t.add_row("Status",       status["status"])
        for model, count in status.get("by_model", {}).items():
            t.add_row(f"  {model}", f"{count:,} tokens")
        console.print(t)

    # Memory stats
    if controller.memory:
        stats = controller.memory.stats()
        m = Table(title="🧠 Memory System", show_header=True)
        m.add_column("Tier", style="cyan")
        m.add_column("Count", style="white")
        for name, data in stats.get("collections", {}).items():
            m.add_row(name, str(data["count"]))
        m.add_row("TOTAL", str(stats.get("total_memories", 0)))
        console.print(m)

    # Skills
    if controller.learner:
        skills = controller.learner.list_skills()
        console.print(f"\n📚 Learned Skills: {len(skills)}")
        for s in skills[:5]:
            console.print(f"   • {s}")


def run_interactive(controller):
    """Interactive REPL loop."""
    console = Console() if RICH_AVAILABLE else None

    if RICH_AVAILABLE:
        console.print(BANNER, style="bold cyan")
        console.print(
            Panel(
                "Type your request below. Type [bold]exit[/bold] to quit, "
                "[bold]/status[/bold] for stats.\n"
                "Copartner remembers everything across sessions.",
                title="[bold green]Copartner v0.2.0 — Interactive Mode[/bold green]",
                border_style="green",
            )
        )
        # Show budget status in header
        if controller.budget:
            console.print(f"  {controller.budget.status_line()}\n", style="dim")
    else:
        print(BANNER)
        print("Copartner — Interactive Mode (type 'exit' to quit)\n")

    while True:
        try:
            if RICH_AVAILABLE:
                query = console.input("[bold green]You ❯[/bold green] ").strip()
            else:
                query = input("You ❯ ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            break

        if not query:
            continue
        if query.lower() in ("exit", "quit", "q"):
            if RICH_AVAILABLE:
                console.print("[dim]Goodbye. Your memories have been saved.[/dim]")
            else:
                print("Goodbye.")
            break
        if query.lower() == "/status":
            _print_status(controller)
            continue

        # Run ThoughtController with streaming output
        if RICH_AVAILABLE:
            console.print("\n[bold yellow]Copartner ❯[/bold yellow]")
            accumulated = []

            with Live("", refresh_per_second=20, console=console) as live:
                def stream_cb(token: str):
                    accumulated.append(token)
                    live.update(Text("".join(accumulated)))

                answer = controller.run(query, stream_callback=stream_cb)

            # Print final answer cleanly
            console.print()
            console.print(Panel(
                answer,
                title="[bold]Final Answer[/bold]",
                border_style="blue",
                padding=(1, 2),
            ))

            # Show budget line after each response
            if controller.budget:
                console.print(f"\n[dim]{controller.budget.status_line()}[/dim]\n")
        else:
            print("\nCopartner ❯")
            answer = controller.run(query, stream_callback=lambda t: print(t, end="", flush=True))
            print(f"\n\n--- Final Answer ---\n{answer}\n")


def run_single(controller, query: str):
    """Run a single query and print the answer."""
    console = Console() if RICH_AVAILABLE else None

    if RICH_AVAILABLE:
        console.print(f"\n[bold green]Query:[/bold green] {query}\n")
        with console.status("[bold yellow]Thinking...[/bold yellow]", spinner="dots"):
            answer = controller.run(query)
        console.print(Panel(answer, title="[bold]Copartner[/bold]", border_style="blue"))
    else:
        print(f"\nQuery: {query}\nThinking...\n")
        answer = controller.run(query)
        print(f"Answer:\n{answer}")


def main():
    parser = argparse.ArgumentParser(
        prog="copartner",
        description="Asirive Copartner — Ambient AI Partner",
    )
    parser.add_argument("query", nargs="?", default=None,
                        help="One-shot query to run (omit for interactive mode)")
    parser.add_argument("--status", action="store_true",
                        help="Show token budget and memory statistics")
    parser.add_argument("--debug", action="store_true",
                        help="Enable debug logging")
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    # Check for API key
    if not os.environ.get("GEMINI_API_KEY"):
        print("ERROR: GEMINI_API_KEY not set. Add it to .env file.")
        sys.exit(1)

    controller = _create_controller()

    if args.status:
        _print_status(controller)
    elif args.query:
        run_single(controller, args.query)
    else:
        run_interactive(controller)


if __name__ == "__main__":
    main()
