from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HttpResponse:
    url: str
    status: int
    headers: dict[str, str]
    body: bytes


def _default_headers() -> dict[str, str]:
    return {
        # Some providers block requests without a UA.
        "User-Agent": "l2-l1-rent-analysis/0.1 (+https://github.com/)",
    }


def http_get(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout_seconds: int = 30,
    retries: int = 4,
    backoff_seconds: float = 1.0,
) -> HttpResponse:
    """Fetch bytes from a URL with simple exponential backoff retries."""
    merged = _default_headers()
    if headers:
        merged.update(headers)

    last_exc: Exception | None = None
    for attempt in range(max(0, retries) + 1):
        try:
            req = urllib.request.Request(url, headers=merged)
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                body = resp.read()
                return HttpResponse(
                    url=url,
                    status=int(getattr(resp, "status", 200)),
                    headers={k.lower(): v for k, v in (resp.headers or {}).items()},
                    body=body,
                )
        except urllib.error.HTTPError as exc:
            # Retry 5xx only.
            last_exc = exc
            if 500 <= int(exc.code) < 600 and attempt < retries:
                time.sleep(backoff_seconds * (2**attempt))
                continue
            raise
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(backoff_seconds * (2**attempt))
                continue
            raise

    # Should be unreachable.
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("http_get failed unexpectedly")


def http_get_text(url: str, *, encoding: str = "utf-8", **kwargs: Any) -> str:
    resp = http_get(url, **kwargs)
    return resp.body.decode(encoding, errors="replace")


def http_get_json(url: str, **kwargs: Any) -> Any:
    text = http_get_text(url, **kwargs)
    return json.loads(text)

