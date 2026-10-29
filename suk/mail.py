"""
mail.py — core mailbox logic and terminal rendering for suk.

HTTP lives in :mod:`suk.client`; this module owns session persistence, polling,
and Rich output.
"""

import json
import random
import threading
import time
from datetime import datetime

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from suk import paths
from suk.client import Mailbox
from suk.exceptions import (
    APIError,
    MailboxExpiredError,
    NotFoundError,
    UsageError,
)
from suk.history import get_history, save_message, shred_history

console = Console(highlight=False)
err_console = Console(stderr=True, highlight=False)
_print_lock = threading.Lock()

MAX_SESSIONS = 4

# Retry transient network and rate-limit errors with exponential back-off.
RETRY_BASE = 2    # seconds for first pause
RETRY_MAX  = 300  # give up after 5 min total

# Slot accent colours (Rich style names)
SLOT_STYLES = ["cyan", "green", "yellow", "magenta"]


# ── Output helpers ────────────────────────────────────────────────────────────

def _cprint(*args, **kwargs):
    with _print_lock:
        console.print(*args, **kwargs)


def _eprint(*args, **kwargs):
    with _print_lock:
        err_console.print(*args, **kwargs)


def _slot_style(slot: int) -> str:
    return SLOT_STYLES[slot % len(SLOT_STYLES)]


def _format_age(created_at) -> str:
    if not created_at:
        return ""
    delta = int(time.time() - created_at)
    if delta < 60:
        return f"{delta}s ago"
    if delta < 3600:
        return f"{delta // 60}m ago"
    if delta < 86400:
        return f"{delta // 3600}h ago"
    return f"{delta // 86400}d ago"


def _fmt_time(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


# ── Session persistence ────────────────────────────────────────────────────────

def _load_sessions() -> list:
    paths.ensure_state_dir()
    path = paths.sessions_file()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            sessions = data if isinstance(data, list) else []
            sessions = [
                entry
                if isinstance(entry, dict) and entry.get("token") and entry.get("mailbox")
                else None
                for entry in sessions
            ]
            return (sessions + [None] * MAX_SESSIONS)[:MAX_SESSIONS]
        except Exception as exc:
            _eprint(f"[yellow]Warning: could not read {path}: {exc}[/yellow]")
    return [None] * MAX_SESSIONS


def _save_sessions(sessions: list):
    paths.ensure_state_dir()
    paths.atomic_write(paths.sessions_file(), json.dumps(sessions, indent=2))


def _migrate_legacy():
    legacy = paths.legacy_file()
    if not legacy.exists():
        return
    sessions = _load_sessions()
    if sessions[0] is not None:
        return
    try:
        data = json.loads(legacy.read_text(encoding="utf-8"))
        if data.get("token") and data.get("mailbox"):
            sessions[0] = {
                "token":      data["token"],
                "mailbox":    data["mailbox"],
                "created_at": data.get("created_at", time.time()),
            }
            _save_sessions(sessions)
            _eprint("[dim]  (Imported legacy session into slot 0)[/dim]")
    except Exception:
        pass


def save_session(slot: int, token: str, address: str) -> dict:
    sessions = _load_sessions()
    entry = {
        "token":      token,
        "mailbox":    address,
        "created_at": time.time(),
    }
    sessions[slot] = entry
    _save_sessions(sessions)
    return entry


def get_session(slot: int) -> dict:
    sessions = _load_sessions()
    if not (0 <= slot < MAX_SESSIONS):
        raise UsageError(f"Slot must be 0-{MAX_SESSIONS - 1}.")
    entry = sessions[slot]
    if not entry:
        raise NotFoundError(f"Slot {slot} is empty.")
    return entry


def delete_session(slot: int) -> str:
    sessions = _load_sessions()
    if not (0 <= slot < MAX_SESSIONS):
        raise UsageError(f"Slot must be 0-{MAX_SESSIONS - 1}.")
    entry = sessions[slot]
    if not entry:
        raise NotFoundError(f"Slot {slot} is empty.")
    address = entry["mailbox"]
    sessions[slot] = None
    _save_sessions(sessions)
    shred_history(address)
    return address


def mailbox_for_slot(slot: int) -> Mailbox:
    entry = get_session(slot)
    return Mailbox(token=entry["token"], address=entry["mailbox"])


# ── Public API ────────────────────────────────────────────────────────────────

def create_mailbox(quiet: bool = False):
    """Create a single mailbox, save to slot 0, return (token, mailbox)."""
    _migrate_legacy()
    sessions = _load_sessions()
    old = sessions[0]
    if not quiet:
        _eprint("[dim]  Spinning up a new inbox…[/dim]")
    inbox = Mailbox.create()
    save_session(0, inbox.token, inbox.address)
    if old and old.get("mailbox") and old["mailbox"] != inbox.address:
        shred_history(old["mailbox"])
    return inbox.token, inbox.address


def load_saved_mailbox():
    """Return (token, mailbox) from slot 0, or None."""
    _migrate_legacy()
    sessions = _load_sessions()
    entry = sessions[0]
    if entry and entry.get("token") and entry.get("mailbox"):
        return entry["token"], entry["mailbox"]
    return None


def add_mailbox(quiet: bool = False):
    """Create a mailbox in the next empty slot. Returns (slot, token, mailbox)."""
    _migrate_legacy()
    sessions = _load_sessions()

    slot = None
    for i, entry in enumerate(sessions):
        if entry is None:
            slot = i
            break

    if slot is None:
        raise UsageError(
            f"All {MAX_SESSIONS} slots are full. "
            "Use `suk --shred all --yes` to clear, or `suk --new` to replace slot 0."
        )

    if not quiet:
        _eprint(f"[dim]  Spinning up inbox in slot {slot}…[/dim]")
    inbox = Mailbox.create()
    save_session(slot, inbox.token, inbox.address)
    return slot, inbox.token, inbox.address


# ── Session listing ────────────────────────────────────────────────────────────

def list_sessions_data() -> list:
    sessions = _load_sessions()
    return [
        {
            "slot":       i,
            "address":    entry["mailbox"],
            "created_at": entry.get("created_at"),
        }
        for i, entry in enumerate(sessions)
        if entry
    ]


def list_sessions():
    data = list_sessions_data()
    if not data:
        console.print("No inboxes yet.")
        console.print("Create one:  [bold]suk --new[/bold]")
        return

    table = Table(
        box=box.ROUNDED,
        show_header=True,
        header_style="bold white",
        border_style="dim white",
        title="[bold white]Saved Sessions[/bold white]",
        title_justify="left",
        padding=(0, 1),
    )
    table.add_column("Slot", style="bold", justify="center", width=6)
    table.add_column("Address", min_width=30)
    table.add_column("Created", style="dim", justify="right")

    for item in data:
        slot = item["slot"]
        color = _slot_style(slot)
        table.add_row(
            f"[{color}][{slot}][/{color}]",
            f"[{color}]{item['address']}[/{color}]",
            _format_age(item.get("created_at")),
        )

    console.print()
    console.print(table)
    free = MAX_SESSIONS - len(data)
    if free:
        console.print(f"  [dim]{free} free slot{'s' if free != 1 else ''}.[/dim]")
    console.print()


def open_session(slot: int, raw_html: bool = False):
    entry = get_session(slot)
    listen(entry["token"], entry["mailbox"], slot=slot, raw_html=raw_html)


# ── Rich display helpers ───────────────────────────────────────────────────────

def _print_inbox_header(mailbox: str, slot: int, multi: bool = False):
    color = _slot_style(slot)
    slot_label = f"[{color}][{slot}][/{color}]  " if multi else ""
    console.print(Rule(
        f"[bold]Inbox[/bold]  {slot_label}[{color}]{mailbox}[/{color}]  "
        f"[dim]·  waiting… (Ctrl+C to quit)[/dim]",
        style="dim",
    ))


def _print_history_header(mailbox: str, slot: int):
    color = _slot_style(slot)
    console.print(Rule(
        f"[bold {color}]History — {mailbox}[/bold {color}]",
        style=color,
    ))


def _render_message(msg_data: dict, slot: int, multi: bool = False,
                    from_history: bool = False) -> Panel:
    """Build one compact Rich Panel for an email."""
    color = _slot_style(slot)
    slot_prefix = f"[{color}][{slot}][/{color}]  " if multi else ""

    ts = ""
    if "received_at" in msg_data:
        ts = f"  [dim]{_fmt_time(msg_data['received_at'])}[/dim]"
    elif from_history:
        ts = "  [dim](from history)[/dim]"

    header = Table.grid(padding=(0, 1))
    header.add_column(style="dim", min_width=7)
    header.add_column()
    header.add_row("From:",    f"[white]{msg_data.get('from', '—')}[/white]")
    header.add_row("Subject:", f"[bold white]{msg_data.get('subject', '(no subject)')}[/bold white]")
    if ts:
        header.add_row("Time:", ts)

    body_text = msg_data.get("body", "").strip() or "(no body)"

    title = (
        f"{slot_prefix}[bold {color}]✉ New message[/bold {color}]"
        if not from_history
        else f"{slot_prefix}[dim]✉ Saved message[/dim]"
    )
    return Panel(
        Group(header, "", Text(body_text, overflow="fold")),
        title=title,
        border_style="dim",
        expand=False,
        padding=(0, 1),
    )


def _display_history(mailbox: str, slot: int, raw_html: bool = False):
    """Print locally stored past messages for this mailbox."""
    msgs = get_history(mailbox)
    if not msgs:
        return
    _print_history_header(mailbox, slot)
    for message in msgs:
        display_message = dict(message)
        if raw_html and message.get("html"):
            display_message["body"] = message["html"]
        console.print(_render_message(display_message, slot=slot, from_history=True))
    console.print(Rule(
        f"[dim]─── {len(msgs)} saved message{'s' if len(msgs) != 1 else ''} above · live below ───[/dim]",
        style="dim",
    ))
    console.print()


# ── Polling ───────────────────────────────────────────────────────────────────

def _poll_messages(inbox: Mailbox, slot: int, stop: threading.Event):
    """Yield message lists. Retry auth/network errors with jittered backoff."""
    color = _slot_style(slot)
    retry_wait = RETRY_BASE
    retry_elapsed = 0
    attempt = 0

    while not stop.is_set():
        try:
            messages = inbox.get_messages()
        except (MailboxExpiredError, APIError) as exc:
            status = getattr(exc, "status_code", 0)
            # Auth and client errors will not recover; fail fast.
            if isinstance(exc, MailboxExpiredError):
                raise
            if 400 <= status < 500 and status != 429:
                raise
            if retry_elapsed == 0:
                _eprint(
                    f"  [yellow]Got {status or 'network error'} — retrying for up to "
                    f"{RETRY_MAX // 60} min…[/yellow]"
                )
            if retry_elapsed >= RETRY_MAX:
                raise

            attempt += 1
            wait = retry_wait * random.uniform(0.5, 1.0)
            _eprint(
                f"  [dim]attempt #{attempt} — waiting {wait:.0f}s "
                f"({retry_elapsed}/{RETRY_MAX}s elapsed)…[/dim]"
            )
            stop.wait(wait)
            retry_elapsed += int(wait)
            retry_wait = min(retry_wait * 2, 60)
            continue

        if retry_elapsed > 0:
            _eprint(f"  [{color}]✓ Connection recovered[/{color}]")
        retry_wait = RETRY_BASE
        retry_elapsed = 0
        attempt = 0
        yield messages
        stop.wait(2)


# ── Listen (single inbox) ─────────────────────────────────────────────────────

def listen(token: str, mailbox: str, slot: int = 0, raw_html: bool = False):
    _display_history(mailbox, slot, raw_html=raw_html)
    _print_inbox_header(mailbox, slot)

    inbox = Mailbox(token=token, address=mailbox)
    seen = set()
    stop = threading.Event()

    for entry in get_history(mailbox):
        seen.add(entry["id"])

    try:
        for messages in _poll_messages(inbox, slot, stop):
            for message in messages:
                if message.id in seen:
                    continue
                seen.add(message.id)
                try:
                    detail = inbox.get_message_detail(message.id)
                except APIError as exc:
                    _eprint(f"[yellow]Could not fetch message {message.id}: {exc}[/yellow]")
                    detail = message

                body_text = detail.body_text or message.body_text
                body_html = detail.body_html
                save_message(
                    mailbox,
                    msg_id=message.id,
                    sender=message.sender,
                    subject=message.subject or "(no subject)",
                    body=body_text,
                    html=body_html or None,
                )
                display_body = (body_html if raw_html and body_html else body_text) or "(no body)"
                display_message = {
                    "from":    message.sender or "—",
                    "subject": message.subject or "(no subject)",
                    "body":    display_body,
                }
                _cprint(_render_message(display_message, slot=slot))
    except KeyboardInterrupt:
        stop.set()
        _cprint("\n[dim]  Done.[/dim]")
        raise


# ── Listen (multiple inboxes) ─────────────────────────────────────────────────

def _listen_multi_slots(sessions: list, slot_map: list, raw_html: bool = False):
    n = len(sessions)

    console.print(Rule(f"[bold]Inbox[/bold] · {n} session{'s' if n != 1 else ''}", style="dim"))
    for i, entry in enumerate(sessions):
        slot = slot_map[i]
        color = _slot_style(slot)
        console.print(f"  [{color}][{slot}][/{color}]  [{color}]{entry['mailbox']}[/{color}]")
    console.print("[dim]  Waiting for messages… (Ctrl+C to quit)[/dim]")
    console.print()

    stop = threading.Event()

    def _worker(slot: int, token: str, mailbox: str):
        inbox = Mailbox(token=token, address=mailbox)
        seen = set()
        for entry in get_history(mailbox):
            seen.add(entry["id"])
        try:
            for messages in _poll_messages(inbox, slot, stop):
                for message in messages:
                    if message.id in seen:
                        continue
                    seen.add(message.id)
                    try:
                        detail = inbox.get_message_detail(message.id)
                    except APIError as exc:
                        _eprint(f"[yellow]Could not fetch message {message.id}: {exc}[/yellow]")
                        detail = message

                    body_text = detail.body_text or message.body_text
                    body_html = detail.body_html
                    save_message(
                        mailbox,
                        msg_id=message.id,
                        sender=message.sender,
                        subject=message.subject or "(no subject)",
                        body=body_text,
                        html=body_html or None,
                    )
                    display_body = (body_html if raw_html and body_html else body_text) or "(no body)"
                    display_message = {
                        "from":    message.sender or "—",
                        "subject": message.subject or "(no subject)",
                        "body":    display_body,
                    }
                    _cprint(_render_message(display_message, slot=slot, multi=True))
        except (MailboxExpiredError, APIError) as exc:
            _eprint(f"[red]Inbox {slot} stopped: {exc}[/red]")

    threads = [
        threading.Thread(
            target=_worker,
            args=(slot_map[i], entry["token"], entry["mailbox"]),
            daemon=True,
        )
        for i, entry in enumerate(sessions)
    ]
    for thread in threads:
        thread.start()

    try:
        while any(thread.is_alive() for thread in threads):
            time.sleep(0.5)
        if not stop.is_set():
            _cprint("[dim]  All inboxes stopped.[/dim]")
    except KeyboardInterrupt:
        stop.set()
        _cprint("\n[dim]  Done.[/dim]")
        raise


def open_sessions_multi(slots: list, raw_html: bool = False):
    _migrate_legacy()
    sessions_all = _load_sessions()
    to_open = [(slot, sessions_all[slot]) for slot in slots if sessions_all[slot]]

    if not to_open:
        raise NotFoundError("No valid sessions to open.")

    if len(to_open) == 1:
        slot, entry = to_open[0]
        listen(entry["token"], entry["mailbox"], slot=slot, raw_html=raw_html)
        return

    for slot, entry in sorted(to_open):
        _display_history(entry["mailbox"], slot, raw_html=raw_html)

    session_list = [entry for _, entry in sorted(to_open)]
    slot_map = [slot for slot, _ in sorted(to_open)]
    _listen_multi_slots(session_list, slot_map, raw_html=raw_html)
