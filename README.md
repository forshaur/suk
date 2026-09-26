# suk

Disposable temporary email inbox available as a Python SDK and a CLI tool.

`suk` allows users to manage up to four simultaneous disposable email inboxes directly from the terminal without a web browser or registration. Additionally, `suk` provides a Python client library (`Mailbox`) for automated testing, web scraping, bot development, and CI/CD pipelines.

---

## Key Features

- **CLI Terminal Interface**: Monitor incoming messages in real time with auto-refreshing terminal panels.
- **Multi-Inbox Support**: Maintain up to four isolated active inbox slots concurrently.
- **Session Persistence**: Reopen existing temporary mailboxes across terminal restarts.
- **Local Message Storage**: History saved locally to ensure received emails are retained.
- **Pure Python SDK**: Zero terminal or UI overhead when imported programmatically.
- **Smart Polling & Filtering**: Synchronous and predicate-based message waiting for automated workflows.

---

## Requirements

- Python 3.8 or higher
- Operating Systems: Linux, macOS, Windows

---

## Installation

Install `suk` from PyPI using `pip`:

```bash
pip install suk
```

---

# User Guide (CLI)

The CLI tool enables instant disposable email inbox creation and management directly from your command prompt.

## Command Reference

| Command | Description |
| --- | --- |
| `suk` | Opens the saved default inbox (slot 0), or creates one if no inbox exists. |
| `suk --new` | Replaces slot 0 with a fresh temporary email address. |
| `suk --add` | Allocates a new disposable inbox in the next empty slot (up to 4 slots total). |
| `suk --list` | Displays a list of all active saved session slots and their email addresses. |
| `suk --open <slot>` | Opens a specific saved session slot (for example, `suk --open 1`). |
| `suk --open <a> <b>` | Opens multiple specified session slots simultaneously (for example, `suk --open 0 2`). |
| `suk --open all` | Opens all saved active session slots in parallel terminal views. |
| `suk --shred all` | Permanently deletes all saved session tokens, addresses, and local message history. |
| `suk --shred history` | Deletes local message history while retaining active inbox sessions. |
| `suk --version` | Prints the installed package version. |
| `suk --help` | Displays help and command usage instructions. |

## Session & Storage Mechanics

`suk` maintains state across executions using local JSON storage files in the user's home directory (`~`):

- **Session Configuration**: `~/.suk_sessions.json` stores active session tokens, mailbox addresses, and slot assignments.
- **Email History**: `~/.suk_history.json` retains downloaded email metadata and message contents across CLI sessions.

---

# Developer Guide (Python SDK)

The `suk` Python package provides a lightweight client layer (`suk.Mailbox`) without terminal UI rendering or side effects.

## Quick Start

```python
from suk import Mailbox

# Generate a new disposable mailbox
inbox = Mailbox.create()
print(f"Temporary Email Address: {inbox.address}")

# Wait for an incoming message matching criteria
message = inbox.wait_for_message(timeout=120)
print(f"Subject: {message.subject}")
print(f"From: {message.sender}")
print(f"Body Preview: {message.body_text}")
```

## API Reference

### Mailbox

`suk.Mailbox(token: str, address: str)`

Represents an active disposable email inbox instance.

#### Class Methods

##### `Mailbox.create() -> Mailbox`

Requests a new temporary email address from the upstream service.

- **Returns**: A new `Mailbox` instance containing a valid API bearer token and email address.
- **Raises**: `APIError` if network issues occur or the upstream service responds with a non-200 HTTP code.

```python
inbox = Mailbox.create()
print(inbox.address)
```

#### Constructor

##### `Mailbox(token: str, address: str)`

Initializes a `Mailbox` from a pre-existing token and address string. Useful for restoring persisted sessions.

```python
inbox = Mailbox(token="saved_bearer_token", address="user@example.com")
```

#### Instance Methods

##### `get_messages() -> list[Message]`

Retrieves a list of messages currently present in the inbox.

- **Returns**: A list of `Message` instances populated with basic header information and text previews.
- **Raises**:
  - `MailboxExpiredError`: If the mailbox token has expired (HTTP 401 or 403).
  - `APIError`: If an unexpected HTTP failure occurs.

```python
messages = inbox.get_messages()
for msg in messages:
    print(msg.sender, msg.subject)
```

##### `get_message_detail(message_id: str) -> Message`

Fetches the complete text and HTML body of a specific message by its unique ID.

- **Parameters**: `message_id` (str) - The unique identifier of the target message.
- **Returns**: A `Message` instance with `body_text` and `body_html` populated.
- **Raises**: `APIError` if retrieval fails.

```python
detail = inbox.get_message_detail(msg.id)
print(detail.body_text)
print(detail.body_html)
```

##### `wait_for_message(predicate=None, timeout=60, poll_interval=3) -> Message`

Blocks execution until a message satisfying the optional `predicate` function arrives.

- **Parameters**:
  - `predicate` (`Callable[[Message], bool]`, optional): Filter function returning `True` for the desired message. Default is `None` (accepts first new message).
  - `timeout` (`int`, optional): Maximum wait time in seconds before aborting. Default is 60 seconds.
  - `poll_interval` (`float`, optional): Interval between polling requests in seconds. Default is 3 seconds.
- **Returns**: A fully populated `Message` object.
- **Raises**:
  - `WaitTimeoutError`: If no matching message is received within `timeout` seconds.
  - `MailboxExpiredError`: If the session expires while polling.
  - `APIError`: On HTTP communication failures.

```python
# Wait for an email containing an activation code
msg = inbox.wait_for_message(
    predicate=lambda m: "activation" in m.subject.lower(),
    timeout=90
)
```

---

### Message

`suk.models.Message`

A data model holding email content and metadata.

#### Fields

| Field | Type | Description |
| --- | --- | --- |
| `id` | `str` | Unique message ID string. |
| `sender` | `str` | Sender email address (`From` header). |
| `subject` | `str` | Message subject string. |
| `body_text` | `str` | Plain-text content of the message body. |
| `body_html` | `Optional[str]` | HTML body string (populated when details are fetched). |
| `received_at` | `Optional[float]` | Local Unix timestamp recorded when message was fetched. |

#### Methods

##### `to_dict() -> dict`

Serializes the `Message` instance into a standard Python dictionary suitable for JSON exporting.

```python
msg_data = msg.to_dict()
```

---

### Exception Hierarchy

All package exceptions derive from `SukError`.

```
SukError
 ├── APIError
 ├── MailboxExpiredError
 └── WaitTimeoutError
```

| Exception | Cause |
| --- | --- |
| `SukError` | Base class for all exceptions in `suk`. |
| `APIError` | Upstream service returns an unexpected HTTP response. |
| `MailboxExpiredError` | Mailbox session token has expired or is invalid. |
| `WaitTimeoutError` | `wait_for_message()` exceeded the designated timeout. |

```python
from suk import SukError, MailboxExpiredError

try:
    messages = inbox.get_messages()
except MailboxExpiredError:
    print("Session expired. Creating new mailbox...")
    inbox = Mailbox.create()
except SukError as err:
    print(f"SDK operation failed: {err}")
```

---

## SDK Integration Examples

### Extracting Verification / OTP Codes

```python
import re
from suk import Mailbox

inbox = Mailbox.create()
print(f"Registering user with address: {inbox.address}")

# Trigger registration request externally using inbox.address ...

message = inbox.wait_for_message(
    predicate=lambda m: "verification" in m.subject.lower(),
    timeout=60
)

match = re.search(r"\b\d{6}\b", message.body_text)
if match:
    otp_code = match.group(0)
    print(f"Extracted OTP code: {otp_code}")
```

### Pytest Integration Fixture

```python
import pytest
from suk import Mailbox

@pytest.fixture
def temp_inbox():
    return Mailbox.create()

def test_user_registration(temp_inbox):
    # Perform registration using temp_inbox.address
    
    msg = temp_inbox.wait_for_message(
        predicate=lambda m: "Welcome" in m.subject,
        timeout=30
    )
    assert msg.sender == "no-reply@service.com"
    assert "Thank you for signing up" in msg.body_text
```

### Session State Serialization

```python
import json
from suk import Mailbox

# Store session credentials
inbox = Mailbox.create()
credentials = {"token": inbox.token, "address": inbox.address}

with open("session.json", "w") as f:
    json.dump(credentials, f)

# Restore session in a separate script or process
with open("session.json", "r") as f:
    data = json.load(f)

restored_inbox = Mailbox(token=data["token"], address=data["address"])
print(f"Restored inbox for {restored_inbox.address}")
```

---

# Development & Architecture

## Package Architecture

```
suk/
├── __init__.py       # Package exports and version metadata
├── client.py         # Pure Python SDK (Mailbox class and HTTP logic)
├── models.py         # Data structures (Message dataclass)
├── exceptions.py     # Custom exception definitions
├── cli.py            # CLI entrypoint and argument parser
├── mail.py           # Terminal display loops and Rich panel layouts
├── history.py        # Local storage handlers (~/.suk_history.json)
└── updater.py        # Background update checker thread
```

## Setting Up for Local Development

1. Clone the repository:
   ```bash
   git clone https://github.com/forshaur/suk.git
   cd suk
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   # On Linux/macOS:
   source venv/bin/activate
   # On Windows:
   venv\Scripts\activate
   ```

3. Install the package in editable mode:
   ```bash
   pip install -e .
   ```

## Dependencies

- `curl-cffi`: Network transport with browser impersonation to communicate with upstream APIs.
- `requests`: General HTTP utilities.
- `rich`: Terminal rendering, color formatting, and dynamic display panels.

---

## License

This project is licensed under the MIT License. See the [LICENSE](file:///c:/Users/Shaurya/Documents/project/suk/LICENSE) file for details.