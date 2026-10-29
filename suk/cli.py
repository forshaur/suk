"""
suk — disposable inbox in your terminal.

Usage:
    suk                         open saved inbox, or create one if none exists
    suk --new                   create a fresh inbox (replaces slot 0)
    suk --add                   add a new inbox in the next empty slot
    suk --list                  list all saved sessions
    suk --open <n>              open saved session in slot n
    suk --open all              open all saved sessions
    suk --open <a> <b> …        open specific slots
    suk --html                  display emails as raw HTML
    suk --json                  machine-readable JSON output
    suk --once                  print a snapshot and exit (no TUI)
    suk messages --slot 0       list messages in a slot
    suk wait --slot 0 --timeout 60
    suk delete --slot 2 --yes
    suk --shred all --yes       delete ALL local data
    suk --shred history --yes   delete local email history only
    suk schema                  print the machine-readable command schema
    suk --check-update          check GitHub for a newer release
    suk --version               print version and exit
"""

import argparse
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from suk import __version__, paths
from suk.exceptions import (
    APIError,
    MailboxExpiredError,
    NetworkError,
    NotFoundError,
    SukError,
    UsageError,
    WaitTimeoutError,
)
from suk.mail import (
    MAX_SESSIONS,
    _render_message,
    add_mailbox,
    create_mailbox,
    delete_session,
    get_session,
    list_sessions,
    list_sessions_data,
    load_saved_mailbox,
    mailbox_for_slot,
    open_session,
    open_sessions_multi,
)
from suk.output import emit, envelope, error_obj

console = Console(highlight=False)
err_console = Console(stderr=True, highlight=False)


class _Parser(argparse.ArgumentParser):
    """Argument parser that can emit a JSON error envelope."""

    json_mode = False

    def error(self, message):
        if self.json_mode:
            emit(envelope(error=error_obj("USAGE", message, hint="Run `suk --help`.")))
            raise SystemExit(2)
        super().error(message)


# ── helpers ───────────────────────────────────────────────────────────────────

def _interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _print_banner():
    console.print(Panel(
        f"[bold cyan]suk[/bold cyan] [dim]v{__version__} · disposable inbox in your terminal[/dim]",
        border_style="dim",
        expand=False,
        padding=(0, 1),
    ))


def _parse_slots(raw) -> list:
    if raw == ["all"]:
        return ["all"]
    slots = []
    for token in raw:
        if not str(token).isdigit():
            raise UsageError(
                f"Invalid slot '{token}'. Use integers 0-{MAX_SESSIONS - 1} or 'all'."
            )
        slot = int(token)
        if not (0 <= slot < MAX_SESSIONS):
            raise UsageError(f"Slot {slot} out of range (0-{MAX_SESSIONS - 1}).")
        slots.append(slot)
    return slots


def _error_code(exc: SukError) -> str:
    if isinstance(exc, UsageError):
        return "USAGE"
    if isinstance(exc, NotFoundError):
        return "NOT_FOUND"
    if isinstance(exc, MailboxExpiredError):
        return "AUTH"
    if isinstance(exc, WaitTimeoutError):
        return "TIMEOUT"
    if isinstance(exc, NetworkError):
        return "NETWORK"
    if isinstance(exc, APIError):
        return "RATE_LIMIT" if exc.status_code == 429 else "API"
    return "ERROR"


def _error_hint(exc: SukError) -> str:
    if isinstance(exc, UsageError):
        return "Run `suk --help`."
    if isinstance(exc, NotFoundError):
        return "Run `suk --list`."
    if isinstance(exc, MailboxExpiredError):
        return "Run `suk --new` to create a fresh inbox."
    if isinstance(exc, WaitTimeoutError):
        return "Increase `--timeout` or check the inbox with `suk messages`."
    if isinstance(exc, NetworkError):
        return "Check your connection and retry."
    if isinstance(exc, APIError) and exc.status_code == 429:
        return "Wait before retrying."
    return "Run `suk --help`."


def _report_error(exc: SukError, json_mode: bool):
    if json_mode:
        emit(envelope(error=error_obj(
            _error_code(exc),
            str(exc),
            hint=_error_hint(exc),
            retryable=isinstance(exc, (NetworkError, WaitTimeoutError))
            or (isinstance(exc, APIError) and exc.status_code == 429),
        )))
    else:
        err_console.print(f"[red]{exc}[/red]")
        hint = _error_hint(exc)
        if hint:
            err_console.print(f"  [dim]{hint}[/dim]")


def _emit_inboxes(data: list):
    emit(envelope({"items": data, "total": len(data)}))


def _messages_payload(slot: int, address: str, messages: list, limit: int = 20) -> dict:
    items = [message.to_dict() for message in messages[:limit]]
    return {
        "slot": slot,
        "address": address,
        "items": items,
        "total": len(messages),
    }


def _print_message_table(messages: list):
    if not messages:
        console.print("[dim]No messages yet.[/dim]")
        return
    table = Table(box=None, show_header=True, header_style="bold white", padding=(0, 1))
    table.add_column("From", style="cyan", no_wrap=True)
    table.add_column("Subject", style="bold")
    table.add_column("Preview", style="dim")
    for message in messages:
        preview = (message.body_text or "").strip().replace("\n", " ")
        if len(preview) > 60:
            preview = preview[:57] + "..."
        table.add_row(message.sender or "—", message.subject or "(no subject)", preview)
    console.print(table)


def _one_shot(token: str, address: str, slot: int, json_mode: bool):
    from suk.client import Mailbox

    inbox = Mailbox(token=token, address=address)
    messages = inbox.get_messages()
    if json_mode:
        emit(envelope(_messages_payload(slot, address, messages)))
        return
    console.print(f"[bold]{address}[/bold]")
    _print_message_table(messages)
    if not messages:
        console.print("[dim]Run `suk --open 0` in a terminal to watch for mail.[/dim]")


# ── commands ──────────────────────────────────────────────────────────────────

def _cmd_list(json_mode: bool):
    data = list_sessions_data()
    if json_mode:
        _emit_inboxes(data)
    else:
        list_sessions()


def _cmd_new(args, json_mode: bool):
    token, address = create_mailbox(quiet=json_mode)
    entry = get_session(0)
    if json_mode:
        emit(envelope({
            "slot": 0,
            "address": address,
            "created_at": entry.get("created_at"),
        }))
        return
    _print_banner()
    if _interactive() and not getattr(args, "once", False):
        open_session(0, raw_html=getattr(args, "html", False))
    else:
        _one_shot(token, address, 0, json_mode)


def _cmd_add(args, json_mode: bool):
    slot, token, address = add_mailbox(quiet=json_mode)
    entry = get_session(slot)
    if json_mode:
        emit(envelope({
            "slot": slot,
            "address": address,
            "created_at": entry.get("created_at"),
        }))
        return
    _print_banner()
    if _interactive() and not getattr(args, "once", False):
        open_session(slot, raw_html=getattr(args, "html", False))
    else:
        _one_shot(token, address, slot, json_mode)


def _cmd_messages(slot: int, limit: int, json_mode: bool):
    if limit < 1:
        raise UsageError("`--limit` must be at least 1.")
    inbox = mailbox_for_slot(slot)
    messages = inbox.get_messages()
    if json_mode:
        emit(envelope(_messages_payload(slot, inbox.address, messages, limit=limit)))
        return
    console.print(f"[bold]{inbox.address}[/bold]")
    _print_message_table(messages[:limit])


def _cmd_wait(slot: int, timeout: int, json_mode: bool):
    if timeout < 0:
        raise UsageError("`--timeout` must be zero or greater.")
    inbox = mailbox_for_slot(slot)
    message = inbox.wait_for_message(timeout=timeout)
    if json_mode:
        emit(envelope({
            "slot": slot,
            "address": inbox.address,
            "message": message.to_dict(),
        }))
        return
    console.print(_render_message({
        "from": message.sender or "—",
        "subject": message.subject or "(no subject)",
        "body": message.body_text or "(no body)",
    }, slot=slot))


def _cmd_delete(slot: int, yes: bool, json_mode: bool):
    if not yes:
        raise UsageError("`suk delete` requires `--yes`.")
    address = delete_session(slot)
    if json_mode:
        emit(envelope({"slot": slot, "address": address, "deleted": True}))
    else:
        console.print(f"[bold red]✓ Deleted slot {slot} ({address}).[/bold red]")


def _cmd_shred(target: str, yes: bool, json_mode: bool):
    if not yes:
        raise UsageError("`suk --shred` requires `--yes`.")
    if target == "all":
        for path in (paths.sessions_file(), paths.legacy_file(), paths.history_file()):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        message = "All local data deleted."
    elif target == "history":
        from suk.history import shred_history

        shred_history()
        message = "Email history deleted (sessions kept)."
    else:
        raise UsageError("Use `suk --shred all` or `suk --shred history`.")

    if json_mode:
        emit(envelope({"target": target, "deleted": True}))
    else:
        console.print(f"[bold red]✓ {message}[/bold red]")


def _cmd_open(raw_slots, args, json_mode: bool):
    slots = _parse_slots(raw_slots)
    once = getattr(args, "once", False)
    raw_html = getattr(args, "html", False)

    if slots == ["all"]:
        sessions = list_sessions_data()
        if not sessions:
            raise NotFoundError("No saved sessions. Run `suk` to create one.")
        if json_mode:
            from suk.client import Mailbox

            items = []
            for item in sessions:
                entry = get_session(item["slot"])
                inbox = Mailbox(token=entry["token"], address=entry["mailbox"])
                items.append(_messages_payload(item["slot"], item["address"], inbox.get_messages()))
            emit(envelope({"items": items, "total": len(items)}))
            return
        if not _interactive() or once:
            raise UsageError("Non-interactive `--open all` needs `--json`.")
        open_sessions_multi([item["slot"] for item in sessions], raw_html=raw_html)
        return

    if json_mode:
        if len(slots) == 1:
            _cmd_messages(slots[0], limit=20, json_mode=True)
        else:
            items = []
            for slot in slots:
                inbox = mailbox_for_slot(slot)
                items.append(_messages_payload(slot, inbox.address, inbox.get_messages()))
            emit(envelope({"items": items, "total": len(items)}))
        return

    if not _interactive() or once:
        if len(slots) != 1:
            raise UsageError("Non-interactive open supports one slot. Use `--json` for multiple.")
        _cmd_messages(slots[0], limit=20, json_mode=False)
        return

    if len(slots) == 1:
        open_session(slots[0], raw_html=raw_html)
    else:
        open_sessions_multi(slots, raw_html=raw_html)


def _cmd_default(args, json_mode: bool):
    saved = load_saved_mailbox()
    if saved:
        token, address = saved
    else:
        token, address = create_mailbox(quiet=json_mode)

    if _interactive() and not getattr(args, "once", False) and not json_mode:
        from suk.updater import check_for_updates

        _print_banner()
        update_thread = check_for_updates()
        update_thread.join(timeout=1.5)
        open_session(0, raw_html=getattr(args, "html", False))
    else:
        _one_shot(token, address, 0, json_mode)


def _cmd_check_update(json_mode: bool):
    from suk.updater import check_now

    result = check_now()
    if json_mode:
        emit(envelope(result))
    else:
        current = result["current"] or "unknown"
        remote = result["remote"]
        if remote is None:
            console.print("Could not check for updates.")
        elif result["newer"]:
            console.print(f"Update available: {current} → {remote}")
            console.print("Upgrade with: [bold]pip install --upgrade suk[/bold]")
        else:
            console.print(f"suk {current} is up to date.")


def _schema() -> dict:
    return {
        "schema_version": "1",
        "commands": [
            {"name": "list", "args": [], "effects": "read-only", "output": "inbox list"},
            {"name": "new", "args": [], "effects": "creates inbox", "output": "slot, address"},
            {"name": "add", "args": [], "effects": "creates inbox", "output": "slot, address"},
            {"name": "open", "args": ["slots"], "effects": "interactive or read-only", "output": "messages"},
            {"name": "messages", "args": ["--slot", "--limit"], "effects": "read-only", "output": "message list"},
            {"name": "wait", "args": ["--slot", "--timeout"], "effects": "read-only", "output": "message"},
            {"name": "delete", "args": ["--slot", "--yes"], "effects": "destructive", "output": "deleted"},
            {"name": "shred", "args": ["target", "--yes"], "effects": "destructive", "output": "deleted"},
            {"name": "schema", "args": [], "effects": "read-only", "output": "schema"},
            {"name": "version", "args": [], "effects": "read-only", "output": "version"},
            {"name": "check-update", "args": [], "effects": "read-only", "output": "version check"},
            {"name": "default", "args": [], "effects": "read-only or creates inbox", "output": "messages"},
        ],
        "global_args": ["--json", "--once", "--html", "--yes"],
        "exit_codes": {
            "0": "success",
            "2": "usage",
            "3": "auth/expired",
            "4": "not found",
            "5": "rate limit",
            "6": "network",
            "7": "API",
            "130": "interrupted",
        },
    }


# ── parser ────────────────────────────────────────────────────────────────────

def _common_options() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="emit one JSON document on stdout")
    parser.add_argument("--html", action="store_true", default=argparse.SUPPRESS,
                        help="display raw HTML bodies")
    parser.add_argument("--once", action="store_true", default=argparse.SUPPRESS,
                        help="print a snapshot and exit")
    parser.add_argument("--yes", action="store_true", default=argparse.SUPPRESS,
                        help="confirm destructive actions")
    return parser


def _build_parser(json_mode: bool = False) -> argparse.ArgumentParser:
    common = _common_options()
    parser = _Parser(
        prog="suk",
        description="Disposable temp-mail inbox — Python SDK and CLI.",
        parents=[common],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.json_mode = json_mode
    parser.add_argument("--version", action="store_true", help="print version and exit")
    parser.add_argument("--check-update", action="store_true", help="check for a newer release")
    parser.add_argument("--new", action="store_true", help="create a fresh inbox in slot 0")
    parser.add_argument("--add", action="store_true", help="create an inbox in the next free slot")
    parser.add_argument("--list", action="store_true", help="list saved inboxes")
    parser.add_argument("--open", nargs="+", metavar="SLOT", help="open slot(s), or 'all'")
    parser.add_argument("--shred", choices=["all", "history"], help="delete local data")

    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("list", parents=[common], help="list saved inboxes")
    sub.add_parser("new", parents=[common], help="create a fresh inbox in slot 0")
    sub.add_parser("add", parents=[common], help="create an inbox in the next free slot")

    open_parser = sub.add_parser("open", parents=[common], help="open slot(s)")
    open_parser.add_argument("slots", nargs="+", metavar="SLOT")

    messages_parser = sub.add_parser("messages", parents=[common], help="list messages in a slot")
    messages_parser.add_argument("--slot", type=int, default=0)
    messages_parser.add_argument("--limit", type=int, default=20)

    wait_parser = sub.add_parser("wait", parents=[common], help="wait for one message")
    wait_parser.add_argument("--slot", type=int, default=0)
    wait_parser.add_argument("--timeout", type=int, default=60)

    delete_parser = sub.add_parser("delete", parents=[common], help="delete one slot")
    delete_parser.add_argument("--slot", type=int, required=True)

    shred_parser = sub.add_parser("shred", parents=[common], help="delete local data")
    shred_parser.add_argument("target", choices=["all", "history"])

    sub.add_parser("schema", parents=[common], help="print the command schema")
    sub.add_parser("version", parents=[common], help="print version")
    sub.add_parser("check-update", parents=[common], help="check for a newer release")

    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for subparser in action.choices.values():
                subparser.json_mode = json_mode

    return parser


def _main(argv: list) -> int:
    json_mode = "--json" in argv
    parser = _build_parser(json_mode=json_mode)
    args = parser.parse_args(argv)
    json_mode = getattr(args, "json", False) or json_mode

    if getattr(args, "version", False) or args.cmd == "version":
        if json_mode:
            emit(envelope({"version": __version__}))
        else:
            console.print(f"suk [bold]{__version__}[/bold]")
        return 0

    if getattr(args, "check_update", False) or args.cmd == "check-update":
        _cmd_check_update(json_mode)
        return 0

    if args.cmd == "schema":
        emit(envelope(_schema()))
        return 0

    command = args.cmd
    if command is None:
        if args.new:
            command = "new"
        elif args.add:
            command = "add"
        elif args.list:
            command = "list"
        elif args.open is not None:
            command = "open"
        elif args.shred:
            command = "shred"
        else:
            command = "default"

    if command == "list":
        _cmd_list(json_mode)
    elif command == "new":
        _cmd_new(args, json_mode)
    elif command == "add":
        _cmd_add(args, json_mode)
    elif command == "open":
        raw_slots = args.open if args.cmd is None else args.slots
        _cmd_open(raw_slots, args, json_mode)
    elif command == "messages":
        _cmd_messages(args.slot, args.limit, json_mode)
    elif command == "wait":
        _cmd_wait(args.slot, args.timeout, json_mode)
    elif command == "delete":
        _cmd_delete(args.slot, getattr(args, "yes", False), json_mode)
    elif command == "shred":
        target = args.shred if args.cmd is None else args.target
        _cmd_shred(target, getattr(args, "yes", False), json_mode)
    elif command == "default":
        _cmd_default(args, json_mode)
    else:
        raise UsageError(f"Unknown command: {command}")

    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    json_mode = "--json" in argv
    try:
        return _main(argv)
    except KeyboardInterrupt:
        return 130
    except SystemExit as exc:
        return int(exc.code or 0)
    except SukError as exc:
        _report_error(exc, json_mode)
        return exc.exit_code
    except OSError as exc:
        err = SukError(f"State error: {exc}")
        _report_error(err, json_mode)
        return err.exit_code


if __name__ == "__main__":
    sys.exit(main())
