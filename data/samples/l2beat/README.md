# `data/samples/l2beat/` — L2BEAT endpoint discovery + schema snapshots

This directory exists to make L2BEAT ingestion **swarm-friendly**:

- No browser DevTools required.
- “Discovery” is **curlable** and reproducible.
- Keep tracked artifacts small (schema snapshots, tiny samples).

## Canonical discovery outcome (2026-02-10)

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

3) Use the repo script to fetch snapshots, normalize daily costs, and write manifests:

```bash
# Requires parquet writer support (`pyarrow`) in the Python environment.
python src/etl/l2beat_fetch.py \
  --run-date YYYY-MM-DD \
  --start-date 2022-01-01 \
  --end-date YYYY-MM-DD \
  --filter-type rollups \
  --write-raw-manifest \
  --write-processed-manifest \
  --write-sample
```

The script writes raw snapshots under `data/raw/l2beat/YYYY-MM-DD/`, builds
`data/processed/l2beat/l2beat_costs_daily.parquet`, writes
`data/raw_manifest/l2beat_YYYY-MM-DD.json`, writes
`data/processed_manifest/l2beat_costs_daily_YYYY-MM-DD.json`, and (if requested)
creates `data/samples/l2beat/l2beat_costs_daily_sample.csv`.

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
- `stats.total.eth` / `stats.total.usd`: range totals used for schema drift checks

For normalized daily total-cost extraction in `src/etl/l2beat_fetch.py`:

- `date_utc` comes from `chart[i][0]` (UNIX timestamp, UTC day).
- `total_cost_eth` is computed as `chart[i][2] + chart[i][5] + chart[i][8] + chart[i][11]`.
- `total_cost_usd` is computed as `chart[i][3] + chart[i][6] + chart[i][9] + chart[i][12]`.
- Rows are mapped via registry `l2beat_slug -> rollup_id` and filtered by
  `in_scope`, `status`, `start_date_utc`, and `end_date_utc`.

## Notes / constraints

- This repo treats L2BEAT as **triangulation**, not the authoritative STR numerator.
- For swarm runs, store:
  - endpoint + request parameters (this README),
  - raw snapshot(s) under `data/raw/l2beat/<run-date>/...`,
  - a raw manifest under `data/raw_manifest/l2beat_<run-date>.json`.
- Golden samples should use the repo’s canonical sample window (see `data/samples/README.md`) and the canonical rollup subset where feasible.
