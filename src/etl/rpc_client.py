from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


DEFAULT_RPC_ENV_VAR = "ETH_RPC_URL"


class RpcError(RuntimeError):
    def __init__(self, *, code: int | None, message: str, data: Any | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def get_rpc_url_from_env(env_var: str = DEFAULT_RPC_ENV_VAR) -> str:
    url = os.environ.get(env_var)
    if not url:
        raise RuntimeError(f"Missing required RPC URL env var: {env_var}")
    return url


def int_to_hex_quantity(value: int) -> str:
    if value < 0:
        raise ValueError("Quantity must be non-negative")
    return hex(value)


def hex_quantity_to_int(value: Any) -> int:
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        raise TypeError(f"Expected hex quantity string, got {type(value)}")
    if value.startswith("0x"):
        return int(value, 16)
    return int(value)


def _default_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "User-Agent": "l2-l1-rent-analysis/0.1 (+https://github.com/)",
    }


@dataclass
class RpcClient:
    url: str
    timeout_seconds: int = 30
    retries: int = 3
    backoff_seconds: float = 1.0
    headers: dict[str, str] | None = None

    def _post_json(self, body: bytes) -> bytes:
        merged = _default_headers()
        if self.headers:
            merged.update(self.headers)

        last_exc: Exception | None = None
        for attempt in range(max(0, self.retries) + 1):
            try:
                req = urllib.request.Request(self.url, method="POST", headers=merged, data=body)
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    return resp.read()
            except urllib.error.HTTPError as exc:
                last_exc = exc
                status = int(getattr(exc, "code", 0) or 0)
                if (status == 429 or 500 <= status < 600) and attempt < self.retries:
                    time.sleep(self.backoff_seconds * (2**attempt))
                    continue
                raise
            except Exception as exc:
                last_exc = exc
                if attempt < self.retries:
                    time.sleep(self.backoff_seconds * (2**attempt))
                    continue
                raise

        # Should be unreachable.
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("RPC request failed unexpectedly")

    def call(self, method: str, params: list[Any] | None = None) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or [],
        }
        raw = self._post_json(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        resp = json.loads(raw.decode("utf-8", errors="replace"))
        if not isinstance(resp, dict):
            raise ValueError(f"Unexpected JSON-RPC response type: {type(resp)}")
        if "error" in resp:
            err = resp.get("error")
            if isinstance(err, dict):
                raise RpcError(code=err.get("code"), message=str(err.get("message", "RPC error")), data=err.get("data"))
            raise RpcError(code=None, message=str(err), data=None)
        return resp.get("result")

