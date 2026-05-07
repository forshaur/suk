"""
suk — disposable inbox in your terminal.

Usage:
    suk                       open saved inbox, or create one if none exists
    suk --new                 create a fresh inbox (replaces slot 0)
    suk --list                list all saved sessions
    suk --open <n>            open saved session in slot n
    suk --open all            open all saved sessions simultaneously
    suk --open <a> <b> ...    open specific slots simultaneously
    suk --version             print version and exit
"""

import sys
from importlib.metadata import version as pkg_version, PackageNotFoundError

from suk.mail import (
    create_mailbox,
    listen,
    load_saved_mailbox,
    list_sessions,
    open_session,
    open_sessions_multi,
    MAX_SESSIONS,
    _load_sessions,
)
from suk.updater import check_for_updates


def _get_version():
    try:
        return pkg_version("suk")
    except PackageNotFoundError:
        return "unknown"


def main():
    args = sys.argv[1:]

    if not args:
        update_thread = check_for_updates()
        saved = load_saved_mailbox()
        if saved:
            token, mailbox = saved
        else:
            print("No saved inbox found, creating one...")
            token, mailbox = create_mailbox()
        update_thread.join(timeout=1.5)
        listen(token, mailbox, slot=0)
        return

    if args[0] == "--version":
        print(f"suk {_get_version()}")
        return

    if args[0] in ("--help", "-h"):
        print(__doc__.strip())
        return

    # ── suk --new ─────────────────────────────────────────────────────────────
    if args[0] == "--new":
        update_thread = check_for_updates()
        token, mailbox = create_mailbox()
        update_thread.join(timeout=1.5)
        listen(token, mailbox, slot=0)
        return

    # ── suk --list ────────────────────────────────────────────────────────────
    if args[0] == "--list":
        list_sessions()
        return

    # ── suk --open <n | all | a b c> ─────────────────────────────────────────
    if args[0] == "--open":
        rest = args[1:]
        if not rest:
            print(f"Usage: suk --open <slot>  |  suk --open all  |  suk --open <a> <b> ...")
            sys.exit(1)

        update_thread = check_for_updates()

        if rest[0] == "all":
            sessions = _load_sessions()
            slots = [i for i, s in enumerate(sessions) if s]
            if not slots:
                print("No saved sessions. Run `suk` to create one.")
                sys.exit(0)
            update_thread.join(timeout=1.5)
            open_sessions_multi(slots)
            return

        # one or more slot numbers
        slots = []
        for tok in rest:
            if not tok.isdigit():
                print(f"Invalid slot '{tok}'. Use integers 0-{MAX_SESSIONS - 1} or 'all'.")
                sys.exit(1)
            slot = int(tok)
            if not (0 <= slot < MAX_SESSIONS):
                print(f"Slot {slot} out of range (0-{MAX_SESSIONS - 1}).")
                sys.exit(1)
            slots.append(slot)

        update_thread.join(timeout=1.5)
        if len(slots) == 1:
            open_session(slots[0])
        else:
            open_sessions_multi(slots)
        return

    print(f"Unknown command: {args[0]}\n")
    print(__doc__.strip())
    sys.exit(1)


if __name__ == "__main__":
    main()