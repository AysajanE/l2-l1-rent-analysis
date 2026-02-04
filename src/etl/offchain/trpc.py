from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
import urllib.parse

from .http import http_get_text


@dataclass(frozen=True)
class TrpcBatchResult:
    raw_response_text: str
    parsed_data: Any


def _encode_trpc_batch_input(input_obj: dict[str, Any]) -> str:
    """Encode a single-input tRPC batch query input.

    L2BEAT uses a JSON-string transformer for tRPC input serialization. For GET query requests,
    the client encodes `input` as:

      encodeURIComponent(JSON.stringify({ "0": JSON.stringify(input_obj) }))
    """
    inner = json.dumps(input_obj, separators=(",", ":"))
    outer = {"0": inner}
    return urllib.parse.quote(json.dumps(outer, separators=(",", ":")), safe="")


def trpc_query_batch1(
    *,
    base_url: str,
    procedure: str,
    input_obj: dict[str, Any],
    timeout_seconds: int = 30,
) -> TrpcBatchResult:
    """Execute a GET tRPC query using batch=1 encoding.

    Returns the raw JSON response text and the parsed inner `result.data` payload.
    """
    base = base_url.rstrip("/")
    url = f"{base}/{procedure}?batch=1&input={_encode_trpc_batch_input(input_obj)}"
    raw = http_get_text(
        url,
        timeout_seconds=timeout_seconds,
        headers={"x-trpc-source": "nextjs-react"},
    )

    outer = json.loads(raw)
    if not isinstance(outer, list) or not outer:
        raise ValueError(f"Unexpected tRPC response shape (expected list): {type(outer)}")
    item = outer[0]
    if not isinstance(item, dict):
        raise ValueError("Unexpected tRPC response item (expected object)")
    if "error" in item:
        raise RuntimeError(f"tRPC error: {item['error']}")
    result = item.get("result")
    if not isinstance(result, dict):
        raise ValueError("Unexpected tRPC response (missing result object)")
    data = result.get("data")
    if not isinstance(data, str):
        raise ValueError("Unexpected tRPC response (result.data is not a string)")

    parsed = json.loads(data)
    return TrpcBatchResult(raw_response_text=raw, parsed_data=parsed)
