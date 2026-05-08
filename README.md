# suk

**Upto 4 live disposable inboxes in your terminal, persistent across sessions — zero browser, zero clicks.**

<img width="400" height="348" alt="Screencast" src="https://github.com/user-attachments/assets/dda54a68-69b3-449e-b7dd-db4780548284" />

## Install

```bash
pip install suk
```

## Usage

```bash
suk                      # open saved inbox (creates one on first run)
suk --new                # burn current address, get a fresh one
suk --sessions <n>       # spin up n inboxes (1–4) and listen on all simultaneously
suk --list               # list all saved sessions
suk --open <n>           # reopen saved session by slot number
suk --open <a> <b> ...   # open multiple slots simultaneously
suk --open all           # reopen every saved session at once
```

Emails print to terminal in real time. Sessions persist in `~/.suk_sessions.json` — close and reopen any inbox anytime with `--open`.

## License

MIT