"""Audit log for every Brave and OpenRouter request and every routing decision.

Each line of ``Data/Logs/api-requests.jsonl`` is one JSON object: a ``request``
entry holds the full URL, request body, response status, headers, body and
timing; a ``decision`` entry records which path the pipeline chose and why.
API keys and cookies are never written.
"""

from __future__ import annotations

import contextvars
import io
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parents[1] / "Data" / "Logs" / "api-requests.jsonl"
_SECRET_HEADERS = {"authorization", "x-subscription-token", "cookie", "set-cookie"}

# The organization currently being enriched, attached to every entry.
record_context: contextvars.ContextVar[dict] = contextvars.ContextVar("record_context", default={})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decode(raw: bytes | None):
    if not raw:
        return None
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except ValueError:
        return text


def _headers(items) -> dict[str, str]:
    return {key: value for key, value in items if key.lower() not in _SECRET_HEADERS}


def _write(entry: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def decision(kind: str, **details) -> None:
    """Record a routing decision, e.g. Brave accepted or the fallback triggered."""
    entry = {"timestamp": _now(), "type": "decision", "kind": kind, **record_context.get(), **details}
    _write(entry)
    print(f"      [decision] {kind} {record_context.get().get('org_id', '')} {details.get('reason', '')}".rstrip(), flush=True)


def send(request: urllib.request.Request, provider: str, purpose: str, timeout: float) -> bytes:
    """Perform ``request``, log it in full, and return the raw response body.

    Errors propagate exactly as from ``urlopen`` (an ``HTTPError`` keeps a
    readable body) after the attempt has been logged.
    """
    entry = {
        "timestamp": _now(),
        "type": "request",
        "provider": provider,
        "purpose": purpose,
        **record_context.get(),
        "method": request.get_method(),
        "url": request.full_url,
        "request_headers": _headers(request.header_items()),
        "request_body": _decode(request.data),
    }
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            entry.update(status=response.status, response_headers=_headers(response.headers.items()), response_body=_decode(raw))
            return raw
    except urllib.error.HTTPError as error:
        raw = error.read()
        entry.update(status=error.code, response_headers=_headers(error.headers.items()), response_body=_decode(raw))
        raise urllib.error.HTTPError(error.url, error.code, error.reason, error.headers, io.BytesIO(raw)) from None
    except Exception as error:
        entry.update(status=None, error=f"{type(error).__name__}: {error}")
        raise
    finally:
        entry["duration_ms"] = round((time.monotonic() - started) * 1000)
        _write(entry)
        print(
            f"      [api] {provider} {purpose} {entry.get('org_id', '')} "
            f"status={entry.get('status')} {entry['duration_ms']}ms",
            flush=True,
        )
