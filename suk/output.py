"""Machine-readable output helpers."""

import json
import sys

SCHEMA_VERSION = "1"


def envelope(data=None, error=None, meta=None) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": error is None,
        "data": data,
        "error": error,
        "meta": meta or {},
    }


def error_obj(code: str, message: str, hint: str = None, retryable: bool = False) -> dict:
    return {
        "code": code,
        "message": message,
        "hint": hint,
        "retryable": retryable,
    }


def emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()
