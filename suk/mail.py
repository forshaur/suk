"""
mail.py — core mailbox logic for suk.

Uses the Rich library for all terminal output.
"""

import json
import sys
import time
import threading
from datetime import datetime
from pathlib import Path

from curl_cffi import requests
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.text import Text
from rich.rule import Rule
from rich.columns import Columns
from rich.padding import Padding
from rich.style import Style

from suk.history import get_history, save_message

console = Console(highlight=False)

DATA_FILE    = Path.home() / ".otp_mailbox.json"
SESSION_FILE = Path.home() / ".suk_sessions.json"

MAX_SESSIONS = 4

# On 401/403, retry with exponential back-off before giving up.
RETRY_BASE = 2    # seconds for first pause
RETRY_MAX  = 300  # give up after 5 min total

# Slot accent colours (Rich style names)
SLOT_STYLES = ["cyan", "green", "yellow", "magenta"]


# ── Helpers ───────────────────────────────────────────────────────────────────

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
    if SESSION_FILE.exists():
        try:
            data = json.loads(SESSION_FILE.read_text())
            sessions = data if isinstance(data, list) else []
            sessions = (sessions + [None] * MAX_SESSIONS)[:MAX_SESSIONS]
            return sessions
        except Exception:
            pass
    return [None] * MAX_SESSIONS


def _save_sessions(sessions: list):
    SESSION_FILE.write_text(json.dumps(sessions, indent=2))


def _migrate_legacy():
    if not DATA_FILE.exists():
        return
    sessions = _load_sessions()
    if sessions[0] is not None:
        return
    try:
        data = json.loads(DATA_FILE.read_text())
        if data.get("token") and data.get("mailbox"):
            sessions[0] = {
                "token":      data["token"],
                "mailbox":    data["mailbox"],
                "created_at": data.get("created_at", time.time()),
            }
            _save_sessions(sessions)
            console.print("[dim]  (Imported legacy session into slot 0)[/dim]")
    except Exception:
        pass


# ── API helpers ───────────────────────────────────────────────────────────────

HEADERS_BASE = {
    "User-Agent":      "Mozilla/5.0 (X11; Linux x86_64; rv:149.0) Gecko/20100101 Firefox/149.0",
    "Accept":          "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Referer":         "https://temp-mail.org/",
    "Origin":          "https://temp-mail.org",
    "Connection":      "keep-alive",
    "Sec-Fetch-Dest":  "empty",
    "Sec-Fetch-Mode":  "cors",
    "Sec-Fetch-Site":  "same-site",
    "Priority":        "u=4",
    "TE":              "trailers",
}


def _post_headers():
    return {**HEADERS_BASE, "Content-Type": "application/json", "Content-Length": "0"}


def _auth_headers(token):
    return {**HEADERS_BASE, "Authorization": f"Bearer {token}"}


def _api_create() -> dict:
    r = requests.post(
        "https://web2.temp-mail.org/mailbox",
        headers=_post_headers(),
        impersonate="firefox",
    )
    r.raise_for_status()
    return r.json()


# ── Public API ────────────────────────────────────────────────────────────────

def create_mailbox():
    """Create a single mailbox, save to slot 0, return (token, mailbox)."""
    _migrate_legacy()
    console.print("[dim]  Spinning up a new inbox…[/dim]")
    try:
        data = _api_create()
    except Exception as e:
        console.print(f"[bold red]  ✗ Couldn't reach temp-mail:[/bold red] {e}")
        sys.exit(1)

    now = time.time()
    sessions = _load_sessions()
    sessions[0] = {"token": data["token"], "mailbox": data["mailbox"], "created_at": now}
    _save_sessions(sessions)
    DATA_FILE.write_text(json.dumps({**data, "created_at": now}, indent=2))
    return data["token"], data["mailbox"]


def load_saved_mailbox():
    """Return (token, mailbox) from slot 0, or None."""
    _migrate_legacy()
    sessions = _load_sessions()
    s = sessions[0]
    if s and s.get("token") and s.get("mailbox"):
        return s["token"], s["mailbox"]
    return None


# ── Multi-session creation ─────────────────────────────────────────────────────

def create_multi_sessions(n: int):
    if not (1 <= n <= MAX_SESSIONS):
        console.print(f"[red]n must be between 1 and {MAX_SESSIONS}.[/red]")
        sys.exit(1)

    _migrate_legacy()
    sessions = _load_sessions()
    new_sessions = []
    now = time.time()
    for i in range(n):
        console.print(f"  [dim][[{i}] Spinning up inbox {i + 1}/{n}…[/dim]")
        try:
            data = _api_create()
            new_sessions.append({"token": data["token"], "mailbox": data["mailbox"], "created_at": now})
        except Exception as e:
            console.print(f"  [red][{i}] Failed:[/red] {e}")
            sys.exit(1)
        time.sleep(0.3)

    for i, s in enumerate(new_sessions):
        sessions[i] = s
    _save_sessions(sessions)
    DATA_FILE.write_text(json.dumps(
        {"token": sessions[0]["token"], "mailbox": sessions[0]["mailbox"], "created_at": now}, indent=2
    ))
    _listen_multi(new_sessions)


# ── Session listing ────────────────────────────────────────────────────────────

def list_sessions():
    _migrate_legacy()
    sessions = _load_sessions()

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
    table.add_column("Address",  min_width=30)
    table.add_column("Created",  style="dim", justify="right")

    any_found = False
    for i, s in enumerate(sessions):
        color = _slot_style(i)
        if s:
            any_found = True
            age = _format_age(s.get("created_at"))
            table.add_row(
                f"[{color}][{i}][/{color}]",
                f"[{color}]{s['mailbox']}[/{color}]",
                age,
            )
        else:
            table.add_row(f"[dim][{i}][/dim]", "[dim](empty)[/dim]", "")

    console.print()
    console.print(table)
    if not any_found:
        console.print("  [dim]No sessions saved. Run `suk` to create one.[/dim]")
    console.print()


def open_session(slot: int):
    _migrate_legacy()
    sessions = _load_sessions()
    if not (0 <= slot < MAX_SESSIONS):
        console.print(f"[red]Slot must be 0–{MAX_SESSIONS - 1}.[/red]")
        sys.exit(1)
    s = sessions[slot]
    if not s:
        console.print(f"[red]Slot {slot} is empty.[/red] Create sessions with `suk` or `suk --new`.")
        sys.exit(1)
    listen(s["token"], s["mailbox"], slot=slot)


# ── Rich display helpers ───────────────────────────────────────────────────────

def _print_inbox_header(mailbox: str, slot: int, multi: bool = False):
    color = _slot_style(slot)
    slot_label = f"[{color}][{slot}][/{color}]  " if multi else ""
    console.print(Panel(
        f"{slot_label}[bold {color}]{mailbox}[/bold {color}]  [dim]·  Waiting for messages… (Ctrl+C to quit)[/dim]",
        title="[bold white]📬 Inbox[/bold white]",
        border_style=color,
        expand=False,
        padding=(0, 1),
    ))


def _print_history_header(mailbox: str, slot: int):
    color = _slot_style(slot)
    console.print(Rule(
        f"[bold {color}]History — {mailbox}[/bold {color}]",
        style=color,
    ))


def _render_message(msg_data: dict, slot: int, multi: bool = False,
                    from_history: bool = False) -> Panel:
    """
    Build a compact Rich Panel for one email.
    msg_data keys: from, subject, body, received_at (optional)
    """
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

    return Panel(
        Group(header, "", Text(body_text, overflow="fold")),
        title=f"{slot_prefix}[bold {color}]✉ New message[/bold {color}]" if not from_history
              else f"{slot_prefix}[dim]✉ {_fmt_time(msg_data.get('received_at', 0)) if 'received_at' in msg_data else 'Saved message'}[/dim]",
        border_style=color if not from_history else "dim",
        expand=False,
        padding=(0, 1),
    )


def _display_history(mailbox: str, slot: int):
    """Print locally stored past messages for this mailbox."""
    msgs = get_history(mailbox)
    if not msgs:
        return
    _print_history_header(mailbox, slot)
    for m in msgs:
        console.print(_render_message(m, slot=slot, from_history=True))
    color = _slot_style(slot)
    console.print(Rule(
        f"[dim]─── {len(msgs)} saved message{'s' if len(msgs) != 1 else ''} above · live below ───[/dim]",
        style="dim",
    ))
    console.print()


# ── Polling ───────────────────────────────────────────────────────────────────

def _poll_with_retry(token: str, slot: int, stop: threading.Event):
    """
    Generator: yields successful GET /messages response objects.
    On 401/403 uses exponential back-off for up to RETRY_MAX seconds.
    Stops when the session is confirmed dead or stop is set.
    """
    color   = _slot_style(slot)
    retry_wait    = RETRY_BASE
    retry_elapsed = 0
    attempt       = 0

    while not stop.is_set():
        try:
            r = requests.get(
                "https://web2.temp-mail.org/messages",
                headers=_auth_headers(token),
                impersonate="firefox",
            )
        except Exception:
            stop.wait(3)
            continue

        if r.status_code == 200:
            if retry_elapsed > 0:
                console.print(f"  [{color}]✓ Connection recovered[/{color}]\n")
            retry_wait    = RETRY_BASE
            retry_elapsed = 0
            attempt       = 0
            yield r
            stop.wait(2)
            continue

        if r.status_code in (401, 403):
            if retry_elapsed == 0:
                console.print(
                    f"\n  [yellow]Got {r.status_code} — retrying for up to "
                    f"{RETRY_MAX // 60} min…[/yellow]"
                )
            if retry_elapsed >= RETRY_MAX:
                console.print(
                    f"\n  [bold red]Session confirmed gone after "
                    f"{RETRY_MAX // 60} min of retries.[/bold red]\n"
                    f"  Run [bold]suk --new[/bold] to get a fresh inbox.\n"
                )
                return

            attempt += 1
            console.print(
                f"  [dim]attempt #{attempt} — waiting {retry_wait}s "
                f"({retry_elapsed}/{RETRY_MAX}s elapsed)…[/dim]",
                end="\r",
            )
            stop.wait(retry_wait)
            retry_elapsed += retry_wait
            retry_wait = min(retry_wait * 2, 60)
            continue

        stop.wait(2)


# ── Full message body fetch ───────────────────────────────────────────────────

def _fetch_full_body(token: str, message_id: str) -> str:
    try:
        r = requests.get(
            f"https://web2.temp-mail.org/messages/{message_id}",
            headers=_auth_headers(token),
            impersonate="firefox",
            timeout=8,
        )
        if r.status_code != 200:
            return ""
        data = r.json()
        body = data.get("bodyText", "").strip()
        if not body:
            body = _strip_html(data.get("bodyHtml", "")).strip()
        return body
    except Exception:
        return ""


def _strip_html(html: str) -> str:
    import re
    html = re.sub(r"<(style|script)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<(br|p|div|tr|li|h[1-6])\b[^>]*>", "\n", html, flags=re.I)
    html = re.sub(r"<[^>]+>", "", html)
    for ent, ch in [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                    ("&nbsp;", " "), ("&quot;", '"'), ("&#39;", "'")]:
        html = html.replace(ent, ch)
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html


# ── Listen (single inbox) ─────────────────────────────────────────────────────

def listen(token: str, mailbox: str, slot: int = 0):
    _display_history(mailbox, slot)
    _print_inbox_header(mailbox, slot)

    seen  = set()
    stop  = threading.Event()

    # Pre-populate seen set with already-stored history ids so we don't
    # re-display history messages as "new" when they come back from the API.
    for h in get_history(mailbox):
        seen.add(h["id"])

    try:
        for r in _poll_with_retry(token, slot, stop):
            for msg in r.json().get("messages", []):
                mid = msg.get("_id")
                if mid not in seen:
                    seen.add(mid)
                    body = _fetch_full_body(token, mid)
                    # Persist to history
                    save_message(
                        mailbox,
                        msg_id  = mid,
                        sender  = msg.get("from", ""),
                        subject = msg.get("subject", "(no subject)"),
                        body    = body or msg.get("bodyPreview", ""),
                    )
                    display_msg = {
                        "from":    msg.get("from", "—"),
                        "subject": msg.get("subject", "(no subject)"),
                        "body":    body or msg.get("bodyPreview", ""),
                    }
                    console.print(_render_message(display_msg, slot=slot))
    except KeyboardInterrupt:
        stop.set()
        console.print("\n[dim]  Done.[/dim]")
        raise   # let main() catch it for a clean exit


# ── Listen (multiple inboxes) ─────────────────────────────────────────────────

def _listen_multi(sessions: list):
    n = len(sessions)

    table = Table(box=box.SIMPLE, show_header=False, border_style="dim")
    table.add_column(width=5)
    table.add_column()
    for i, s in enumerate(sessions):
        c = _slot_style(i)
        table.add_row(f"[{c}][{i}][/{c}]", f"[{c}]{s['mailbox']}[/{c}]")

    console.print(Panel(
        Group(table, "", Text("·  Waiting for messages on all inboxes… (Ctrl+C to quit)", style="dim")),
        title=f"[bold white]📬 Opening {n} inbox{'es' if n > 1 else ''}[/bold white]",
        border_style="white",
        expand=False,
        padding=(0, 1),
    ))

    stop = threading.Event()

    def _worker(slot: int, token: str, mailbox: str):
        seen = set()
        for h in get_history(mailbox):
            seen.add(h["id"])
        try:
            for r in _poll_with_retry(token, slot, stop):
                for msg in r.json().get("messages", []):
                    mid = msg.get("_id")
                    if mid not in seen:
                        seen.add(mid)
                        body = _fetch_full_body(token, mid)
                        save_message(
                            mailbox,
                            msg_id  = mid,
                            sender  = msg.get("from", ""),
                            subject = msg.get("subject", "(no subject)"),
                            body    = body or msg.get("bodyPreview", ""),
                        )
                        display_msg = {
                            "from":    msg.get("from", "—"),
                            "subject": msg.get("subject", "(no subject)"),
                            "body":    body or msg.get("bodyPreview", ""),
                        }
                        console.print(_render_message(display_msg, slot=slot, multi=True))
        except Exception:
            pass

    threads = [
        threading.Thread(target=_worker, args=(i, s["token"], s["mailbox"]), daemon=True)
        for i, s in enumerate(sessions)
    ]
    for t in threads:
        t.start()

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        stop.set()
        console.print("\n[dim]  Done.[/dim]")
        raise


def open_sessions_multi(slots: list):
    _migrate_legacy()
    sessions_all = _load_sessions()
    to_open = [(slot, sessions_all[slot]) for slot in slots if sessions_all[slot]]

    if not to_open:
        console.print("[red]No valid sessions to open.[/red]")
        sys.exit(1)

    if len(to_open) == 1:
        slot, s = to_open[0]
        listen(s["token"], s["mailbox"], slot=slot)
        return

    # Show history for each slot before starting live listen
    for slot, s in sorted(to_open):
        _display_history(s["mailbox"], slot)

    # Build ordered lists for _listen_multi, keeping original slot colours
    session_list = [s for _, s in sorted(to_open)]
    slot_map     = [slot for slot, _ in sorted(to_open)]
    _listen_multi_slots(session_list, slot_map)


def _listen_multi_slots(sessions: list, slot_map: list):
    n = len(sessions)
    table = Table(box=box.SIMPLE, show_header=False, border_style="dim")
    table.add_column(width=5)
    table.add_column()
    for i, s in enumerate(sessions):
        slot = slot_map[i]
        c = _slot_style(slot)
        table.add_row(f"[{c}][{slot}][/{c}]", f"[{c}]{s['mailbox']}[/{c}]")

    console.print(Panel(
        Group(table, "", Text("·  Waiting for messages… (Ctrl+C to quit)", style="dim")),
        title=f"[bold white]📬 Opening {n} inbox{'es' if n > 1 else ''}[/bold white]",
        border_style="white",
        expand=False,
        padding=(0, 1),
    ))

    stop = threading.Event()

    def _worker(slot: int, token: str, mailbox: str):
        seen = set()
        for h in get_history(mailbox):
            seen.add(h["id"])
        try:
            for r in _poll_with_retry(token, slot, stop):
                for msg in r.json().get("messages", []):
                    mid = msg.get("_id")
                    if mid not in seen:
                        seen.add(mid)
                        body = _fetch_full_body(token, mid)
                        save_message(
                            mailbox,
                            msg_id  = mid,
                            sender  = msg.get("from", ""),
                            subject = msg.get("subject", "(no subject)"),
                            body    = body or msg.get("bodyPreview", ""),
                        )
                        display_msg = {
                            "from":    msg.get("from", "—"),
                            "subject": msg.get("subject", "(no subject)"),
                            "body":    body or msg.get("bodyPreview", ""),
                        }
                        console.print(_render_message(display_msg, slot=slot, multi=True))
        except Exception:
            pass

    threads = [
        threading.Thread(
            target=_worker,
            args=(slot_map[i], s["token"], s["mailbox"]),
            daemon=True,
        )
        for i, s in enumerate(sessions)
    ]
    for t in threads:
        t.start()

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        stop.set()
        console.print("\n[dim]  Done.[/dim]")
        raise