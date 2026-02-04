# `data/samples/l2beat/` — L2BEAT endpoint discovery + schema snapshots

This directory exists to make L2BEAT ingestion **swarm-friendly**:

- No browser DevTools required.
- “Discovery” is **curlable** and reproducible.
- Keep tracked artifacts small (schema snapshots, tiny samples).

## Canonical discovery outcome (2026-02-04)

L2BEAT scaling costs data is served via a **tRPC** endpoint:

- Base URL: `https://l2beat.com/api/trpc`
- Relevant procedures (observed in the site JS bundle):
  - `costs.table` (per-project totals over a time range; USD/ETH/gas breakdown)
  - `costs.chart` (aggregate chart time series over a time range; used for UI charting)
  - `costs.projectChart` (single-project time series over a time range; used for per-project charting)

## Curlable request format (important)

L2BEAT uses a JSON-string transformer for tRPC inputs. For GET queries, the request is:

- URL: `https://l2beat.com/api/trpc/<procedure>?batch=1&input=<ENCODED>`
- `ENCODED = encodeURIComponent(JSON.stringify({"0": JSON.stringify(<input_object>)}))`

Example input object for rollups-only:

```json
{"range":[START_TS,END_TS],"filter":{"type":"rollups"}}
```

Where `START_TS` and `END_TS` are UNIX timestamps (seconds).

## Recommended discovery workflow (no browser)

1) Fetch the page HTML:

```bash
curl -sS 'https://l2beat.com/scaling/costs' -o /tmp/l2beat_costs.html
```

2) Confirm the page embeds a dehydrated query state (`window.__SSR_DATA__`) with a sample query key
and a sample range:

```bash
python - <<'PY'
import json, pathlib, re
html = pathlib.Path("/tmp/l2beat_costs.html").read_text(encoding="utf-8", errors="replace")
m = re.search(r"window\.__SSR_DATA__\s*=\s*", html)
if not m:
    raise SystemExit("window.__SSR_DATA__ not found")
tail = html[m.end():].lstrip()
ssr, _end = json.JSONDecoder().raw_decode(tail)
print(ssr["props"]["queryState"]["queries"][0]["queryKey"])
PY
```

3) Use the repo script to snapshot responses + write raw manifests:

```bash
python src/etl/l2beat_fetch.py --run-date YYYY-MM-DD --mode table --filter-type rollups
python src/etl/l2beat_fetch.py --run-date YYYY-MM-DD --mode chart  --filter-type rollups

# Track provenance (recommended; does not execute the command, it records it)
python scripts/make_raw_manifest.py l2beat data/raw/l2beat/YYYY-MM-DD --as-of YYYY-MM-DD -- bash -lc \
  "python src/etl/l2beat_fetch.py --run-date YYYY-MM-DD --mode table --filter-type rollups && \
   python src/etl/l2beat_fetch.py --run-date YYYY-MM-DD --mode chart --filter-type rollups"
```

## Response schema snapshot (high-level)

All procedures respond (in batch mode) as JSON arrays with one element. That element contains:

- `result.data`: a **string containing JSON** (parse it again).

For `costs.table`, after parsing `result.data`, the payload is a JSON object:

- Keys: project IDs (typically equal to L2BEAT project slugs, e.g., `"arbitrum"`)
- Values: object with:
  - `usd`: `{ total, calldata, blobs, compute, overhead }` (numbers)
  - `eth`: `{ total, calldata, blobs, compute, overhead }` (numbers)
  - `gas`: `{ total, calldata, blobs, compute, overhead }` (integers)
  - `uopsCount`: integer

For `costs.projectChart`, after parsing `result.data`, the payload includes:

- `chart`: list of `[timestamp, ...]` rows (parse `result.data` as JSON; see `src/etl/offchain/trpc.py`)
- `syncedUntil`: timestamp
- `hasBlobs`: boolean

## Notes / constraints

- This repo treats L2BEAT as **triangulation**, not the authoritative STR numerator.
- For swarm runs, store:
  - endpoint + request parameters (this README),
  - raw snapshot(s) under `data/raw/l2beat/<run-date>/...`,
  - a raw manifest under `data/raw_manifest/l2beat_<run-date>.json`.
