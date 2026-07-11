"""
suk — disposable inbox in your terminal.

Usage:
    suk                         open saved inbox, or create one if none exists
    suk --new                   create a fresh inbox (replaces slot 0)
    suk --list                  list all saved sessions
    suk --open <n>              open saved session in slot n (history shown first)
    suk --open all              open all saved sessions simultaneously
    suk --open <a> <b> …        open specific slots simultaneously
    suk --shred all             delete ALL local data (sessions + history)
    suk --shred history         delete local email history only
    suk --version               print version and exit
"""

import sys
from importlib.metadata import version as pkg_version, PackageNotFoundError
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

console = Console(highlight=False)

# Lazy imports from suk — so rich is available for error messages even if
# the rest of the package fails to import.
def _import_mail():
    from suk.mail import (
        create_mailbox, listen, load_saved_mailbox,
        list_sessions, open_session, open_sessions_multi,
        MAX_SESSIONS, _load_sessions,
    )
    return (create_mailbox, listen, load_saved_mailbox,
            list_sessions, open_session, open_sessions_multi,
            MAX_SESSIONS, _load_sessions)


def _get_version() -> str:
    try:
        return pkg_version("suk")
    except PackageNotFoundError:
        return "unknown"


def _print_banner():
    ver = _get_version()
    console.print(Panel(
        f"[bold cyan]suk[/bold cyan] [dim]v{ver} · disposable inbox in your terminal[/dim]",
        border_style="dim",
        expand=False,
        padding=(0, 1),
    ))


# ── shred ─────────────────────────────────────────────────────────────────────

def _cmd_shred(target: str):
    from suk.history import shred_history, shred_all as _shred_all_history

    SESSION_FILE = Path.home() / ".suk_sessions.json"
    DATA_FILE    = Path.home() / ".otp_mailbox.json"

    if target == "all":
        for f in (SESSION_FILE, DATA_FILE):
            if f.exists():
                f.unlink()
        _shred_all_history()
        console.print("[bold red]  ✓ All local data deleted.[/bold red]")

    elif target == "history":
        _shred_all_history()
        console.print("[bold yellow]  ✓ Email history deleted (sessions kept).[/bold yellow]")

    else:
        console.print(
            f"[red]Unknown shred target '[bold]{target}[/bold]'.[/red]\n"
            f"  Use [bold]suk --shred all[/bold] or [bold]suk --shred history[/bold]."
        )
        sys.exit(1)


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]

    try:
        _main(args)
    except KeyboardInterrupt:
        # Clean Ctrl+C — already printed "Done." inside listen(); just exit quietly.
        sys.exit(0)


def _main(args: list):
    (create_mailbox, listen, load_saved_mailbox,
     list_sessions, open_session, open_sessions_multi,
     MAX_SESSIONS, _load_sessions) = _import_mail()

    from suk.updater import check_for_updates

    # ── no args: open or create slot 0 ────────────────────────────────────────
    if not args:
        _print_banner()
        update_thread = check_for_updates()
        saved = load_saved_mailbox()
        if saved:
            token, mailbox = saved
        else:
            console.print("  [dim]No saved inbox found, creating one…[/dim]")
            token, mailbox = create_mailbox()
        update_thread.join(timeout=1.5)
        listen(token, mailbox, slot=0)
        return

    # ── --version ─────────────────────────────────────────────────────────────
    if args[0] == "--version":
        console.print(f"suk [bold]{_get_version()}[/bold]")
        return

    # ── --help / -h ───────────────────────────────────────────────────────────
    if args[0] in ("--help", "-h"):
        console.print(__doc__.strip())
        return

    # ── --new ─────────────────────────────────────────────────────────────────
    if args[0] == "--new":
        _print_banner()
        update_thread = check_for_updates()
        token, mailbox = create_mailbox()
        update_thread.join(timeout=1.5)
        listen(token, mailbox, slot=0)
        return

    # ── --list ────────────────────────────────────────────────────────────────
    if args[0] == "--list":
        list_sessions()
        return

    # ── --shred <all | history> ───────────────────────────────────────────────
    if args[0] == "--shred":
        if len(args) < 2:
            console.print(
                "[red]Usage:[/red] [bold]suk --shred all[/bold]  |  "
                "[bold]suk --shred history[/bold]"
            )
            sys.exit(1)
        _cmd_shred(args[1])
        return

    # ── --open <n | all | a b c> ──────────────────────────────────────────────
    if args[0] == "--open":
        rest = args[1:]
        if not rest:
            console.print(
                "[red]Usage:[/red] suk --open [bold]<slot>[/bold]  |  "
                "suk --open [bold]all[/bold]  |  suk --open [bold]<a> <b> …[/bold]"
            )
            sys.exit(1)

        _print_banner()
        update_thread = check_for_updates()

        if rest[0] == "all":
            sessions = _load_sessions()
            slots = [i for i, s in enumerate(sessions) if s]
            if not slots:
                console.print("[dim]No saved sessions. Run `suk` to create one.[/dim]")
                sys.exit(0)
            update_thread.join(timeout=1.5)
            open_sessions_multi(slots)
            return

        slots = []
        for tok in rest:
            if not tok.isdigit():
                console.print(
                    f"[red]Invalid slot '[bold]{tok}[/bold]'. "
                    f"Use integers 0–{MAX_SESSIONS - 1} or 'all'.[/red]"
                )
                sys.exit(1)
            slot = int(tok)
            if not (0 <= slot < MAX_SESSIONS):
                console.print(f"[red]Slot {slot} out of range (0–{MAX_SESSIONS - 1}).[/red]")
                sys.exit(1)
            slots.append(slot)

        update_thread.join(timeout=1.5)
        if len(slots) == 1:
            open_session(slots[0])
        else:
            open_sessions_multi(slots)
        return

    console.print(f"[red]Unknown command:[/red] [bold]{args[0]}[/bold]\n")
    console.print(__doc__.strip())
    sys.exit(1)


if __name__ == "__main__":
    main()