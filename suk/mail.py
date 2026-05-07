import json
import sys
import time
import threading
from pathlib import Path

from curl_cffi import requests

DATA_FILE    = Path.home() / ".otp_mailbox.json"   # legacy single-session
SESSION_FILE = Path.home() / ".suk_sessions.json"  # new multi-session store

MAX_SESSIONS = 4   # slots 0-3

# ── ANSI ──────────────────────────────────────────────────────────────────────
CYAN    = "\033[96m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
MAGENTA = "\033[95m"
BLUE    = "\033[94m"
RED     = "\033[91m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
RESET   = "\033[0m"

SLOT_COLORS = [CYAN, GREEN, YELLOW, MAGENTA]


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
            sessions[0] = {"token": data["token"], "mailbox": data["mailbox"]}
            _save_sessions(sessions)
            print(f"{DIM}  (Imported legacy session into slot 0){RESET}")
    except Exception:
        pass


# ── API helpers ───────────────────────────────────────────────────────────────

HEADERS_BASE = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:149.0) Gecko/20100101 Firefox/149.0",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Referer": "https://temp-mail.org/",
    "Origin": "https://temp-mail.org",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "Priority": "u=4",
    "TE": "trailers",
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
    """Create a single mailbox, save to slot 0 (legacy behaviour), return (token, mailbox)."""
    _migrate_legacy()
    print("Spinning up a new inbox...")
    try:
        data = _api_create()
    except Exception as e:
        print(f"Couldn't reach temp-mail: {e}")
        sys.exit(1)

    sessions = _load_sessions()
    sessions[0] = {"token": data["token"], "mailbox": data["mailbox"]}
    _save_sessions(sessions)
    DATA_FILE.write_text(json.dumps(data, indent=2))
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
    """Create n new inboxes, fill the first n slots, then open all simultaneously."""
    if not (1 <= n <= MAX_SESSIONS):
        print(f"n must be between 1 and {MAX_SESSIONS}.")
        sys.exit(1)

    _migrate_legacy()
    sessions = _load_sessions()

    new_sessions = []
    for i in range(n):
        print(f"  [{i}] Spinning up inbox {i + 1}/{n}...")
        try:
            data = _api_create()
            new_sessions.append({"token": data["token"], "mailbox": data["mailbox"]})
        except Exception as e:
            print(f"  [{i}] Failed: {e}")
            sys.exit(1)
        time.sleep(0.3)

    for i, s in enumerate(new_sessions):
        sessions[i] = s
    _save_sessions(sessions)

    DATA_FILE.write_text(json.dumps(
        {"token": sessions[0]["token"], "mailbox": sessions[0]["mailbox"]}, indent=2
    ))

    _listen_multi(new_sessions)


# ── Session listing & selection ───────────────────────────────────────────────

def list_sessions():
    _migrate_legacy()
    sessions = _load_sessions()
    any_found = False
    print(f"\n  {BOLD}Saved sessions:{RESET}\n")
    for i, s in enumerate(sessions):
        color = SLOT_COLORS[i]
        if s:
            any_found = True
            print(f"  {BOLD}{color}[{i}]{RESET}  {s['mailbox']}")
        else:
            print(f"  {DIM}[{i}]  (empty){RESET}")
    if not any_found:
        print(f"  {DIM}No sessions saved. Run `suk` to create one.{RESET}")
    print()


def open_session(slot: int):
    """Open an existing session by slot number."""
    _migrate_legacy()
    sessions = _load_sessions()
    if not (0 <= slot < MAX_SESSIONS):
        print(f"Slot must be 0-{MAX_SESSIONS - 1}.")
        sys.exit(1)
    s = sessions[slot]
    if not s:
        print(f"Slot {slot} is empty. Create sessions with `suk` or `suk --sessions <n>`.")
        sys.exit(1)
    listen(s["token"], s["mailbox"], slot=slot)


def pick_session():
    """Interactive session picker."""
    _migrate_legacy()
    sessions = _load_sessions()
    occupied = [(i, s) for i, s in enumerate(sessions) if s]
    if not occupied:
        print("No saved sessions. Run `suk` to create one.")
        sys.exit(0)

    print(f"\n  {BOLD}Choose a session:{RESET}\n")
    for i, s in occupied:
        color = SLOT_COLORS[i]
        print(f"    {BOLD}{color}[{i}]{RESET}  {s['mailbox']}")
    print()

    while True:
        try:
            raw = input(f"  Enter slot number ({', '.join(str(i) for i, _ in occupied)}): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            sys.exit(0)
        if raw.isdigit():
            slot = int(raw)
            match = [s for i, s in occupied if i == slot]
            if match:
                listen(match[0]["token"], match[0]["mailbox"], slot=slot)
                return
        print(f"  Invalid. Choose from: {', '.join(str(i) for i, _ in occupied)}")


# ── Listening ─────────────────────────────────────────────────────────────────

def listen(token, mailbox, slot=0):
    color = SLOT_COLORS[slot % len(SLOT_COLORS)]
    label = f"{BOLD}{color}[{slot}]{RESET}"
    print(f"\n  {label}  Email  \u2192  {BOLD}{color}{mailbox}{RESET}")
    print(f"  Waiting for messages... (Ctrl+C to quit)\n")

    seen = set()
    try:
        while True:
            try:
                r = requests.get(
                    "https://web2.temp-mail.org/messages",
                    headers=_auth_headers(token),
                    impersonate="firefox",
                )
            except Exception:
                time.sleep(3)
                continue

            if r.status_code in (401, 403):
                print(f"  {label} Session expired. Run `suk --new` to get a fresh address.")
                break

            if r.status_code == 200:
                for msg in r.json().get("messages", []):
                    mid = msg.get("_id")
                    if mid not in seen:
                        seen.add(mid)
                        _print_message(msg, slot=slot, token=token, multi=False)

            time.sleep(2)

    except KeyboardInterrupt:
        print("\nDone.")


def _listen_multi(sessions: list):
    n = len(sessions)
    print(f"\n  {BOLD}Opening {n} inbox(es) simultaneously:{RESET}")
    for i, s in enumerate(sessions):
        color = SLOT_COLORS[i % len(SLOT_COLORS)]
        print(f"  {BOLD}{color}[{i}]{RESET}  {s['mailbox']}")
    print(f"\n  Waiting for messages on all inboxes... (Ctrl+C to quit)\n")

    stop = threading.Event()

    def _worker(slot, token):
        color = SLOT_COLORS[slot % len(SLOT_COLORS)]
        label = f"{BOLD}{color}[{slot}]{RESET}"
        seen = set()
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

            if r.status_code in (401, 403):
                print(f"  {label} Session expired.")
                return

            if r.status_code == 200:
                for msg in r.json().get("messages", []):
                    mid = msg.get("_id")
                    if mid not in seen:
                        seen.add(mid)
                        _print_message(msg, slot=slot, token=token, multi=True)

            stop.wait(2)

    threads = []
    for i, s in enumerate(sessions):
        t = threading.Thread(target=_worker, args=(i, s["token"]), daemon=True)
        t.start()
        threads.append(t)

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        stop.set()
        print("\nDone.")


def _print_message(msg, slot=0, token="", multi=False):
    color = SLOT_COLORS[slot % len(SLOT_COLORS)]
    sep = f"{color}{chr(9472) * 60}{RESET}"

    # Slot tag only shown in multi-session mode
    slot_tag = f" {BOLD}{color}[{slot}]{RESET}" if multi else ""

    print(sep)
    print(f"{slot_tag}  {BOLD}From{RESET}    : {msg.get('from', chr(8212))}")
    print(f"{slot_tag}  {BOLD}Subject{RESET} : {BOLD}{GREEN}{msg.get('subject', '(no subject)')}{RESET}")
    print(sep)

    mid = msg.get("_id", "")
    body = _fetch_full_body(token, mid) if (token and mid) else None
    if body:
        for line in body.splitlines():
            if line.strip():   # skip blank lines from HTML stripping
                print(f"{slot_tag}  {line}")
    else:
        print(f"{slot_tag}  {msg.get('bodyPreview', '').strip()}")

    print(sep + "\n")



def open_sessions_multi(slots: list):
    """Re-open existing saved sessions by slot list and listen simultaneously."""
    _migrate_legacy()
    sessions = _load_sessions()
    to_open = []
    for slot in slots:
        s = sessions[slot]
        if not s:
            print(f"Slot {slot} is empty — skipping.")
            continue
        to_open.append((slot, s))

    if not to_open:
        print("No valid sessions to open.")
        import sys; sys.exit(1)

    if len(to_open) == 1:
        slot, s = to_open[0]
        listen(s["token"], s["mailbox"], slot=slot)
    else:
        # Repack into list ordered by slot
        session_list = [s for _, s in sorted(to_open)]
        slot_map = [slot for slot, _ in sorted(to_open)]
        _listen_multi_slots(session_list, slot_map)


def _listen_multi_slots(sessions: list, slot_map: list):
    """Like _listen_multi but uses original slot numbers for colour/label."""
    print(f"\n  {BOLD}Opening {len(sessions)} inbox(es):{RESET}")
    for i, s in enumerate(sessions):
        slot = slot_map[i]
        color = SLOT_COLORS[slot % len(SLOT_COLORS)]
        print(f"  {BOLD}{color}[{slot}]{RESET}  {s['mailbox']}")
    print(f"\n  Waiting for messages... (Ctrl+C to quit)\n")

    stop = threading.Event()

    def _worker(slot, token):
        color = SLOT_COLORS[slot % len(SLOT_COLORS)]
        seen = set()
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
            if r.status_code in (401, 403):
                print(f"  {BOLD}{color}[{slot}]{RESET} Session expired.")
                return
            if r.status_code == 200:
                for msg in r.json().get("messages", []):
                    mid = msg.get("_id")
                    if mid not in seen:
                        seen.add(mid)
                        _print_message(msg, slot=slot, token=token, multi=True)
            stop.wait(2)

    threads = []
    for i, s in enumerate(sessions):
        slot = slot_map[i]
        t = threading.Thread(target=_worker, args=(slot, s["token"]), daemon=True)
        t.start()
        threads.append(t)

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        stop.set()
        print("\nDone.")

def _fetch_full_body(token: str, message_id: str):
    """Fetch the full message and return cleaned plain-text body, or None on failure."""
    try:
        r = requests.get(
            f"https://web2.temp-mail.org/messages/{message_id}",
            headers=_auth_headers(token),
            impersonate="firefox",
            timeout=8,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        body = data.get("bodyText", "").strip()
        if not body:
            html = data.get("bodyHtml", "")
            body = _strip_html(html).strip()
        return body or None
    except Exception:
        return None


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