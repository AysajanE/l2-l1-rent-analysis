<scratchpad>
- Distinct data requirements:
  - Off-chain standardized L2 fundamentals by day: L2 fees, rent_paid (L1 costs), profit, txcount (growthepie).
  - Independent cross-check of L1 costs by rollup (L2BEAT costs series + tracked tx list).
  - Blob market state + blob usage by time and (ideally) rollup labels (Blobscan; fallback: raw chain).
  - Raw Ethereum L1 data: blocks/headers, txs, receipts; post‑4844 blob tx identification and required header fields.
  - Rollup attribution registry: batch poster/sequencer/prover addresses + key L1 contracts; validity windows; evidence links.
  - ETH issuance series (daily) + ETH/USD price series (daily) for secondary metrics.
- Logical collection phases (aligned to research plan):
  - Phase 0: repo/protocol lock + data dictionary + rollup universe list.
  - Phase 1: ingest off-chain vendor datasets (growthepie; L2BEAT; Blobscan).
  - Phase 2: extract raw L1 chain data (block/tx/receipt; blob fields).
  - Phase 3: build/version rollup attribution registry (addresses/contracts with validity dates).
  - Phase 4: compute rollup-attributed L1 costs + burn/tips decomposition (data processing, but still “collection” of derived tables).
  - Phase 5: QA + reconciliation tables + coverage metrics; freeze analysis-ready daily panel.
- Source mapping:
  - growthepie: primary for L2Fees + RentPaid + Profit + Txcount (daily panel).
  - on-chain computed L1 fees: primary for burn/tips decomposition and “auditable” rent.
  - L2BEAT costs: secondary triangulation for rent/cost breakdown (calldata vs blobs vs compute/overhead).
  - Blobscan: secondary/assistive for blob usage + labeling utilities; raw chain as fallback.
  - Issuance: primary from consensus-layer feeds (beacon APIs) or a reputable derived dataset; secondary from Ultrasound/others (cross-check).
  - Prices: primary from CoinGecko (or equivalent); secondary from CryptoCompare/Coinbase.
- Optimal sequence & dependencies:
  - Need rollup universe list + date window before any pulls.
  - Need growthepie master.json before exporting metrics (to confirm exact metric keys).
  - Need Dencun activation timestamp as regime boundary (March 13, 2024 13:55 UTC / epoch 269568) to split extraction logic. 
  - Need attribution registry before rollup-attributed on-chain fee aggregation.
- Special technical considerations:
  - EIP‑4844 blob tx (type‑3) fees: execution gas fee + blob fee; blob base fee derived from header fields; many datasets omit blob fields—validate early.
  - Address drift: posters change; use validity windows + ongoing detection of new senders to known rollup contracts.
  - Vendor drift: snapshot every pull; store raw JSON and “master metadata” per run.
</scratchpad>

<data_collection_plan>

## Phase 0 — Project initialization, protocol lock, and data dictionary

### 1. Phase name and objectives

**Phase 0: Initialization + Protocol Lock**

* Set up the repo, environment, secrets handling, and immutable snapshot conventions.
* Freeze: rollup inclusion rules, STR definition, units, and regime split boundary.
* Produce the authoritative data dictionary and table schemas used by later phases.

### 2. Data requirements

* Protocol metadata:

  * **Dencun activation boundary:** March 13, 2024 13:55 UTC (epoch 269568).
* Rollup universe seed list (initial “candidate rollups”):

  * From growthepie origins list (via master.json).
  * From L2BEAT “rollups” list (manual/derived from site, for cross-check).
* Technical definitions:

  * STR numerator = rollup L1 costs (rent paid).
  * STR denominator = rollup user fees on L2.

### 3. Primary source with detailed collection instructions

**Primary:** growthepie `master.json` (origin list + metric catalog)

* Access method: HTTP GET to `https://api.growthepie.com/v1/master.json` (public). ([Grow the Pie][1])
* Authentication: none indicated in docs; verify at run time.

### 4. Secondary source with detailed collection instructions

**Secondary:** L2BEAT scaling summary pages (manual capture) + internal API if discoverable

* Access method: browser/manual export and/or internal API exploration (see Phase 1B).
* Caveat: L2BEAT notes internal APIs exist but are not guaranteed stable.

### 5. Specific metrics/fields to collect with definitions

**Required (protocol metadata)**

* `dencun_activation_utc`: `"2024-03-13T13:55:00Z"` (regime split for blob fields logic).
* `analysis_start_date`: `"2022-01-01"`
* `analysis_end_date`: `"present"` (rolling; resolved at run time)

**Required (growthepie master metadata)**

* `origins`: mapping of `origin_key` → rollup name / metadata (store full object)
* `metrics`: mapping of `metric_key` → definition / unit hints (store full object)
* `api_version` or any version fields if present

### 6. Temporal parameters

* Start: 2022‑01‑01
* End: run date (e.g., current date in system context is 2026‑01‑15; but always compute “today” at runtime).
* Granularity: metadata is point-in-time snapshot.
* Update frequency: **snapshot on every pipeline run** (daily if operating continuously).

### 7. Collection procedure (step-by-step)

1. **Create repo structure** (see Phase 7 for structure).
2. Create `config/project.yml` containing:

   * `start_date`, `end_date`, `dencun_activation_utc`
   * `sources`: growthepie base URL, Blobscan base URL, etc.
3. Pull growthepie `master.json` and store raw snapshot:

   * Save as: `data/raw/growthepie/master/{run_date}/master.json`
   * Also compute and store hash: `sha256(master.json)` in `data/manifests/raw_files.csv`.
4. From `master.json`, generate:

   * `reference/origins_catalog.parquet` (one row per origin)
   * `reference/metrics_catalog.parquet` (one row per metric)
5. Draft the **Data Dictionary** (`docs/data_dictionary.md`) with:

   * For each table: fields, units, required/optional, primary key.
6. Freeze a `rollup_universe_v0.csv` with columns:

   * `rollup_id` (internal stable ID), `origin_key` (growthepie), `display_name`, `category` (optimistic/zk/other if known), `in_scope` (bool), `notes`.

### 8. Attribution/mapping requirements

Not yet executed, but define now:

* `rollup_id` is the stable internal join key across all datasets.
* `origin_key` (growthepie) and `l2beat_slug` are foreign keys.
* Rollup address registry will be versioned (Phase 3).

### 9. Validation and quality checks

* Ensure `master.json` parse succeeds and yields non-empty `origins` and `metrics`.
* Store a “diff report” between last snapshot and current snapshot:

  * newly added/removed origins
  * newly added/removed metrics
* Any change triggers a “schema drift alert” requiring human review before continuing.

### 10. Output specifications

* `data/raw/growthepie/master/{YYYY-MM-DD}/master.json`
* `data/reference/origins_catalog.parquet`
* `data/reference/metrics_catalog.parquet`
* `data/reference/rollup_universe_v0.csv`
* `docs/data_dictionary.md`

### 11. Success criteria

* A new team member can identify:

  * which rollups are in-scope,
  * which metric keys correspond to fees/rent/profit/txcount in ETH and USD,
  * and the fixed regime boundary time.

### 12. Estimated effort and dependencies

* Effort: 0.5–1.5 person-days (mostly setup + documentation).
* Dependencies: none.

---

## Phase 1A — growthepie daily fundamentals ingestion (primary STR denominator + vendor rent series)

### 1. Phase name and objectives

**Phase 1A: growthepie ingestion**

* Collect daily L2 fundamentals per rollup needed for STR:

  * `fees`, `rent_paid`, `profit`, `txcount` (and ETH-denominated counterparts if separate metric keys exist).
* Snapshot raw exports to prevent methodology drift.

### 2. Data requirements

From growthepie, daily time series by rollup:

* L2 user fees (denominator)
* L1 rent paid by rollup (vendor numerator candidate)
* Profit and tx count (interpretation and scaling controls)

### 3. Primary source with detailed collection instructions

**Primary:** growthepie export endpoints (`/v1/export/{METRIC}.json`) ([Grow the Pie][1])

* Access method: HTTP GET
* Authentication: none indicated
* Notes:

  * `fundamentals.json` exists but appears limited (e.g., last 90 days). Use **export** for full history. ([Grow the Pie][1])

**Key endpoints**

* `https://api.growthepie.com/v1/master.json` (metadata; Phase 0)
* `https://api.growthepie.com/v1/export/{METRIC}.json` (full time series per metric) ([Grow the Pie][1])

### 4. Secondary source with detailed collection instructions

**Secondary:** DefiLlama / rollup explorers / rollup fee vaults (only for spot checks on top rollups)

* Access method: API or explorer export
* Use only when growthepie is missing days or appears inconsistent.

### 5. Specific metrics/fields to collect with definitions

**Required metrics (must be collected)**

1. `fees` (L2 user fees)
2. `rent_paid` (L1 cost paid by rollup)
3. `profit` (= fees − rent_paid, in the growthepie methodology)
4. `txcount` (daily transaction count)

**Strongly recommended (if available as separate keys)**

* `fees_eth`, `rent_paid_eth`, `profit_eth` (ETH-denominated series). growthepie notes currency variants often exist as separate metric keys (e.g., `_eth`). ([Grow the Pie][1])

**Raw record schema (from docs)**
Each export record includes: ([Grow the Pie][1])

* `metric_key` (string): metric identifier (e.g., `"rent_paid"`)
* `origin_key` (string): rollup identifier (e.g., `"arbitrum_one"`)
* `date` (string, YYYY-MM-DD)
* `value` (number): metric value (unit depends on metric)

**Units**

* You must infer units per `metric_key` using `metrics_catalog` from `master.json` and/or by comparing `fees` vs `fees_eth` magnitudes.
* Store units explicitly in the normalized tables (`unit` column).

### 6. Temporal parameters

* Start date: 2022‑01‑01
* End date: run date (inclusive; if API lags, allow latest to be missing)
* Granularity: daily
* Update frequency:

  * Historical backfill: one-time full pull
  * Ongoing: daily incremental pull + weekly full pull (to detect revisions)

### 7. Collection procedure (step-by-step)

**Step 1 — Determine correct metric keys**

1. Load `data/reference/metrics_catalog.parquet`.
2. Confirm the exact keys for:

   * fees (USD vs ETH)
   * rent_paid (USD vs ETH)
   * profit (USD vs ETH)
   * txcount
3. Record chosen keys in `config/growthepie_metrics.yml`.

**Step 2 — Pull raw exports**
For each `metric_key` in `config/growthepie_metrics.yml`:

1. Download: `GET /v1/export/{metric_key}.json`
2. Save raw response as:

   * `data/raw/growthepie/export/{metric_key}/{run_date}/{metric_key}.json`
3. Compute and store checksum in `data/manifests/raw_files.csv`.

**Step 3 — Normalize into a single fact table**

1. Parse JSON into a table with columns:

   * `date`, `origin_key`, `metric_key`, `value`
2. Add:

   * `run_date`, `source="growthepie"`, `snapshot_path`
3. Write normalized parquet partitioned by `metric_key` and `run_date`:

   * `data/normalized/growthepie_metrics/metric_key={k}/run_date={YYYY-MM-DD}/part-000.parquet`

**Step 4 — Pivot into “analysis-ready vendor panel”**
Create:

* `data/analysis_ready/vendor_daily_rollup_panel.parquet` with columns:

  * `date`, `rollup_id`, `fees_eth`, `fees_usd`, `rent_paid_eth`, `rent_paid_usd`, `profit_eth`, `profit_usd`, `txcount`
    Rules:
* If ETH series is missing, keep USD but flag `fees_eth_missing=true`.
* Never mix units without explicit conversion.

**Edge cases & failure handling**

* API rate limits: implement exponential backoff + retry (e.g., 1s, 2s, 4s, 8s, max 5 attempts).
* Partial downloads: verify JSON parses and row count > 0 before accepting; else retry.
* Missing days: keep as null and log to `data/qa/gaps_report_growthepie.csv`.

### 8. Attribution/mapping requirements

* Map `origin_key` → `rollup_id` via `rollup_universe_v0.csv`.
* If new origins appear in master.json, mark them `in_scope=false` until reviewed.

### 9. Validation and quality checks

**Basic checks**

* For each metric:

  * Coverage ≥ 95% of days for in-scope rollups (per research plan success threshold).
  * No negative values for `txcount`, `fees`, `rent_paid` (unless documented).
* Identity check (vendor-level):

  * `profit ≈ fees − rent_paid` (allow small rounding error; tolerance 0.5–1.0% depending on units).

**Cross-checks (spot)**

* Select top 5 rollups by `fees_eth` in last 30 days:

  * Compare monthly sums of `rent_paid` to on-chain computed costs (Phase 4).
  * Flag if abs diff > 10% and investigate.

### 10. Output specifications

* Raw:

  * `data/raw/growthepie/export/{metric_key}/{run_date}/{metric_key}.json`
* Normalized:

  * `data/normalized/growthepie_metrics/.../*.parquet`
* Analysis-ready:

  * `data/analysis_ready/vendor_daily_rollup_panel.parquet`
* QA:

  * `data/qa/growthepie_coverage_report_{run_date}.csv`

### 11. Success criteria

* For each in-scope rollup:

  * daily `fees` and `rent_paid` series exist for ≥95% of days since 2022‑01‑01
* All raw inputs are snapshotted and reproducible.

### 12. Estimated effort and dependencies

* Effort: 1–2 person-days for implementation + first full pull; then minutes/day for monitoring.
* Dependencies: Phase 0 completed (metric keys + rollup mapping).

---

## Phase 1B — L2BEAT costs ingestion (secondary rent/cost triangulation)

### 1. Phase name and objectives

**Phase 1B: L2BEAT costs ingestion**

* Collect an independent estimate of L2→L1 costs, preferably broken down by:

  * calldata, blobs, compute, overhead (as shown on their costs tooling).
* Use as triangulation (not necessarily as the main numerator).

L2BEAT’s costs page defines onchain costs as fees paid by L2s to Ethereum for posting tx data/proofs/state updates. ([L2BEAT][2])

### 2. Data requirements

* Per rollup, per day:

  * `total_cost` (ETH and/or USD)
  * `calldata_cost`, `blob_cost`, `compute_cost`, `overhead_cost` (if provided)
  * If possible: list of tracked L1 transactions used to compute those costs (addresses or tx hashes).

### 3. Primary source with detailed collection instructions

**Primary:** Discover and use L2BEAT internal API endpoints (preferred)
L2BEAT acknowledges the website uses an internal API (example shown for TVL endpoints), but they do not guarantee stability.

**Discovery procedure (must-do once and document)**

1. Open the costs page in a browser: `https://l2beat.com/scaling/costs`. ([L2BEAT][2])
2. Open DevTools → Network tab.
3. Filter requests by substring: `api`, `json`, `cost`, `scaling`.
4. Identify the request(s) that return the data backing the table/chart.
5. Copy:

   * request URL
   * query parameters (date range, currency, granularity)
   * response schema
6. Record these in `config/l2beat_endpoints.yml` and snapshot the response for an initial run.

### 4. Secondary source with detailed collection instructions

**Secondary:** HTML scraping or manual export (fallback only)

* If no API is discoverable:

  1. For each in-scope rollup’s project page on L2BEAT, locate “Onchain costs” section and extract time series by scraping.
  2. If the UI supports selecting time range (e.g., “1Y”), iterate across ranges and stitch, but **prefer the API**.

### 5. Specific metrics/fields to collect with definitions

**Required**

* `date` (YYYY-MM-DD)
* `l2beat_slug` (e.g., “arbitrum”, “base”)
* `total_cost_eth` (ETH)
* `total_cost_usd` (USD)
* `source_timestamp` (when collected)

**Optional**

* `calldata_cost_*`, `blob_cost_*`, `compute_cost_*`, `overhead_cost_*`
* `tracked_tx_count`
* `tracked_tx_hashes` (array) or `tracked_addresses` (array)

### 6. Temporal parameters

* Start: 2022‑01‑01 (if L2BEAT supports it; otherwise earliest available)
* End: run date
* Granularity: daily preferred; weekly acceptable only if daily unavailable (but must be flagged)
* Update frequency: weekly (enough for triangulation), plus ad-hoc re-pulls when they change methodology.

### 7. Collection procedure (step-by-step)

1. **Endpoint discovery & schema capture** (one-time):

   * Save a “network capture note” in `docs/l2beat_api_discovery.md` with screenshots and sample responses.
2. **Backfill pull**:

   * For each rollup and date range supported, download time series.
   * Save raw JSON:

     * `data/raw/l2beat/costs/{run_date}/{l2beat_slug}.json`
3. **Normalization**:

   * Convert to a standard table with required fields.
4. **Consistency mapping**:

   * Map `l2beat_slug` to `rollup_id` via `reference/rollup_universe_*.csv`.

**Edge cases**

* If only rolling windows are allowed, automate repeated downloads (e.g., 30-day windows) and stitch, deduplicating by date.
* If costs are presented in “PER L2 USER OP” units, ignore for STR; keep as optional.

### 8. Attribution/mapping requirements

* Store mapping table:

  * `rollup_id`, `l2beat_slug`, `display_name`
* If L2BEAT splits a rollup (e.g., “OP Mainnet” vs “Optimism”), record alias rules.

### 9. Validation and quality checks

* Coverage check: at least 80% day coverage for top 10 rollups (triangulation standard).
* Monthly aggregate comparison:

  * Compare L2BEAT `total_cost_eth` vs growthepie `rent_paid_eth`:

    * Acceptable: within 5–10% for mature rollups; else investigate.
* Track “methodology drift”:

  * If response schema changes, freeze old pull and version the parser.

### 10. Output specifications

* Raw:

  * `data/raw/l2beat/costs/{run_date}/{l2beat_slug}.json`
* Normalized:

  * `data/normalized/l2beat_costs_daily.parquet`
* QA:

  * `data/qa/l2beat_vs_growthepie_costs_{run_date}.csv`

### 11. Success criteria

* L2BEAT costs are ingestible in an automated way (API or robust scrape).
* At least monthly aggregates can be computed for cross-checking.

### 12. Estimated effort and dependencies

* Effort: 1–3 person-days (mostly endpoint discovery + parser).
* Dependencies: Phase 0 rollup mapping.

---

## Phase 1C — Blobscan ingestion (blob usage and labeling utilities)

### 1. Phase name and objectives

**Phase 1C: Blobscan ingestion**

* Collect blob market and blob usage data to characterize regimes (min blob fee vs congestion).
* Use Blobscan as:

  * a convenience data source (when it provides aggregates),
  * and/or a labeling helper for rollup blob usage attribution.

Blobscan documents a REST API at `api.blobscan.com` and notes some internal endpoints are JWT-protected.

### 2. Data requirements

At minimum (daily):

* `blob_base_fee` (base fee per blob gas, in wei)
* `blob_gas_used` per block/day
* `blob_tx_count` per day
* `blobs_count` per day (or infer from blob gas used)
* Optional: by rollup labels (daily blob usage by rollup)

### 3. Primary source with detailed collection instructions

**Primary:** Blobscan API (Swagger/OpenAPI)

* Base: `https://api.blobscan.com/` (Swagger UI)
* Access method:

  1. Open Swagger UI in browser.
  2. Export OpenAPI spec (often `openapi.json` / `swagger.json`; discover via Swagger UI).
  3. Generate client code or call endpoints directly.

### 4. Secondary source with detailed collection instructions

**Secondary:** Raw chain computation (Phase 2 + Phase 4)

* If Blobscan endpoints are incomplete/unavailable, compute blob stats from L1 blocks/txs directly.

### 5. Specific metrics/fields to collect with definitions

**Required (daily blob market state)**

* `date` (UTC day)
* `baseFeePerBlobGas_wei` (wei; derived or direct from API)
* `blobGasUsed` (blob gas units)
* `excessBlobGas` (blob gas units)
* `blob_tx_count` (count of type‑3 txs)
* `blobs_count` (count of blobs; if only gas given: `blobGasUsed / 131072`)

**Optional (attribution helpers)**

* `rollup_label` (string)
* `rollup_blob_tx_hashes` (array)
* `rollup_blob_gas_used`

### 6. Temporal parameters

* Start: 2024‑03‑13 (EIP‑4844 activation; no blobs before)
* End: run date
* Granularity:

  * block-level preferred for validation,
  * daily aggregates for analysis
* Update frequency: daily

### 7. Collection procedure (step-by-step)

1. **Discover endpoints via Swagger UI**:

   * Identify endpoints for:

     * blocks (with blob fields),
     * transactions (filter to blob tx),
     * stats/aggregations if available.
   * Record in `config/blobscan_endpoints.yml`.
2. **Backfill block/day aggregates**:

   * Pull in time chunks (e.g., 1 day or 10k blocks).
3. **Store raw**:

   * `data/raw/blobscan/{endpoint}/{run_date}/...json`
4. **Normalize** into:

   * `blobscan_blocks.parquet` (block-level)
   * `blobscan_daily.parquet` (daily aggregates)
5. **If rollup labeling exists**:

   * Pull rollup-labeled blob usage series; store as `blobscan_rollup_daily.parquet`.

**Edge cases**

* API pagination: implement cursor/offset handling; always persist pagination tokens.
* If rate-limited: backoff and resume; ensure idempotency (don’t duplicate records).

### 8. Attribution/mapping requirements

* If Blobscan provides rollup mapping, store it as “evidence” for Phase 3 registry.
* Do not use Blobscan labels blindly; treat as a seed and validate against on-chain sender/to patterns.

### 9. Validation and quality checks

* Cross-check daily blobGasUsed from Blobscan vs raw chain daily aggregation (Phase 4) on a sample month; tolerance ≤1%.
* Verify `baseFeePerBlobGas_wei >= 1` always (EIP minimum).
* Detect missing blocks/days and log.

### 10. Output specifications

* Raw: `data/raw/blobscan/...`
* Normalized:

  * `data/normalized/blobscan_blocks.parquet`
  * `data/normalized/blobscan_daily.parquet`
  * `data/normalized/blobscan_rollup_daily.parquet` (if available)

### 11. Success criteria

* Daily blob market state series is complete post‑Dencun (≥95% day coverage).
* Blobscan-derived aggregates reconcile to on-chain aggregates.

### 12. Estimated effort and dependencies

* Effort: 1–2 person-days if endpoints are clear; 3–5 if manual Swagger exploration is needed.
* Dependencies: none, but Phase 2 improves validation.

---

## Phase 1D — Price and issuance inputs (for USD series + burn vs issuance)

### 1. Phase name and objectives

**Phase 1D: ETH price + issuance ingestion**

* Collect daily ETH/USD price (for secondary USD conversions).
* Collect daily ETH issuance (for `RollupBurnShareOfIssuance`).

### 2. Data requirements

**Required**

* `eth_usd_price_close` per UTC day
* `eth_issuance` per UTC day (ETH units)
* Optional:

  * `eth_supply_total` per day
  * `burn_total` per day (for consistency, though rollup burn computed separately)

### 3. Primary source with detailed collection instructions

**Price (primary):** CoinGecko API (or institutional equivalent)

* Access method: REST API
* Auth: may require API key depending on plan.

**Issuance (primary):** Consensus-layer data feed / beacon chain API

* Options:

  1. Beacon node API (if you operate one)
  2. Public beacon explorer API (e.g., beaconcha.in) with API key

*(Because issuance sourcing is operationally variable, you must document which choice you made and keep it consistent.)*

### 4. Secondary source with detailed collection instructions

* Price (secondary): CryptoCompare / Coinbase exchange candles.
* Issuance (secondary): a reputable derived dataset (e.g., ultrasound.money API) used only as cross-check.

### 5. Specific metrics/fields to collect with definitions

**Price table (daily)**

* `date` (UTC)
* `eth_usd_close`
* `eth_usd_open`, `high`, `low` (optional)
* `source`

**Issuance table (daily)**

* `date` (UTC)
* `issuance_eth` (ETH)
* `source`
* `method` (e.g., “beacon rewards aggregated by epoch”)

### 6. Temporal parameters

* Start: 2022‑01‑01
* End: run date
* Granularity: daily
* Update frequency: daily

### 7. Collection procedure (step-by-step)

1. Pull daily ETH/USD candles; store raw JSON.
2. Normalize into `prices_daily.parquet`.
3. Pull issuance series; store raw JSON.
4. Normalize into `issuance_daily.parquet`.
5. Create QA join:

   * Check no missing days > 2 consecutive; else flag.

### 8. Attribution/mapping requirements

None (global series).

### 9. Validation and quality checks

* Price: compare CoinGecko vs secondary source monthly average; tolerance 1–2% (exchange differences).
* Issuance: compare primary vs secondary within 0.5–1% monthly; if drift, investigate method.

### 10. Output specifications

* `data/normalized/prices_daily.parquet`
* `data/normalized/issuance_daily.parquet`

### 11. Success criteria

* Continuous daily series for both inputs with documented provenance.

### 12. Estimated effort and dependencies

* Effort: 0.5–2 person-days depending on issuance method.
* Dependencies: none.

---

## Phase 2 — Raw Ethereum L1 extraction (blocks, transactions, receipts; blob fields post‑Dencun)

### 1. Phase name and objectives

**Phase 2: Raw L1 extraction**

* Build a complete transaction-level dataset sufficient to compute:

  * rollup-paid L1 execution fees,
  * blob fees (post‑Dencun),
  * base-fee burn vs validator tips decomposition.

### 2. Data requirements

**Required block fields (per block)**

* `block_number`
* `timestamp` (UTC)
* `base_fee_per_gas` (wei) — EIP‑1559
* `gas_used`, `gas_limit`
* Post‑Dencun:

  * `blob_gas_used` (aka `blobGasUsed`)
  * `excess_blob_gas` (aka `excessBlobGas`)

**Required transaction fields (per tx)**

* `tx_hash`
* `block_number`, `tx_index`
* `from_address`, `to_address`
* `type` (tx type; must identify type‑3 blob txs)
* `gas_used` (from receipt)
* `effective_gas_price` (from receipt; wei)
* `status` (success/fail)
* `max_fee_per_gas`, `max_priority_fee_per_gas` (optional, for diagnostics)

**Required blob tx fields (type‑3 only)**

* `blob_versioned_hashes` (array) OR `blob_count`
* `max_fee_per_blob_gas` (if available)
* Derivations:

  * `blob_gas_used_tx = blob_count * 131072`
  * `base_fee_per_blob_gas` (computed from block header if not directly provided)

### 3. Primary source with detailed collection instructions

**Primary:** Ethereum full node archive indexing OR a third-party “enhanced RPC” provider + internal index

* Access method: JSON-RPC + batch requests
* Authentication: depends on provider (API key typical)

**Recommended minimum RPC methods**

* `eth_getBlockByNumber` (with transactions or without; choose performance)
* `eth_getTransactionReceipt`
* Post‑Dencun additional methods may exist, but do not rely on them; prefer header fields.

### 4. Secondary source with detailed collection instructions

**Secondary:** Public warehouse datasets (BigQuery / parquet dumps) for pre‑Dencun and as a performance accelerator

* Use only after verifying they include post‑4844 blob fields (many lag).

### 5. Specific metrics/fields to collect with definitions

**Block table** (`l1_blocks`)

* `block_number` (int)
* `block_hash` (hex)
* `timestamp` (int; seconds since epoch)
* `base_fee_per_gas_wei` (int)
* `gas_used` (int)
* `gas_limit` (int)
* `blob_gas_used` (int; null pre‑Dencun)
* `excess_blob_gas` (int; null pre‑Dencun)

**Transaction receipt table** (`l1_receipts`)

* `tx_hash`
* `block_number`
* `from_address`, `to_address`
* `tx_type` (int)
* `gas_used`
* `effective_gas_price_wei`
* `status`

**Type‑3 blob tx extension** (`l1_blob_tx`)

* `tx_hash`
* `blob_count` (int)
* `max_fee_per_blob_gas_wei` (optional)
* `blob_versioned_hashes` (optional; store if available)

### 6. Temporal parameters

* Start: 2022‑01‑01 (block number determined by nearest timestamp)
* End: run date
* Granularity:

  * block-level and tx-level
* Update frequency:

  * Historical backfill: one-time
  * Ongoing: daily “yesterday” backfill + periodic reorg-safe refresh (last 7 days)

### 7. Collection procedure (step-by-step)

**Step 0 — Choose extraction mode**

* Mode A (recommended for most teams): RPC provider + incremental indexing to a local warehouse (Postgres/BigQuery/Parquet).
* Mode B: Public warehouse + RPC supplement for missing fields.

**Step 1 — Determine block ranges**

1. Query block number at `start_date` by binary search on timestamp.
2. Do the same for `end_date`.
3. Store bounds in `data/reference/block_bounds.json`.

**Step 2 — Extract blocks**

1. For each block number in range:

   * Pull block header fields; store `base_fee_per_gas`, `gas_used`, `blob_gas_used`, `excess_blob_gas`.
2. Write to partitioned parquet:

   * `data/raw/l1/blocks/run_date=YYYY-MM-DD/part-*.parquet`

**Step 3 — Extract candidate rollup transactions**
Two approaches (choose one; document choice):

* **Approach 3.1 (broad, safer):** Extract *all* transactions, then filter by attribution registry later (Phase 4).
* **Approach 3.2 (narrow, cheaper):** Extract only transactions where:

  * `from_address` in known rollup poster list (Phase 3), OR
  * `to_address` is a known rollup inbox/proof contract (Phase 3),
  * plus all type‑3 txs (for blob usage completeness).

For a first build, use Approach 3.1 for correctness; optimize later.

**Step 4 — Receipts**

* For each extracted tx hash, fetch receipt; store required receipt fields.

**Step 5 — Blob tx parsing**

* For txs with `tx_type==3`:

  * parse `blob_versioned_hashes` if available; else infer blob count from tx fields if provider exposes it.
  * if blob count cannot be extracted from tx, you must fall back to:

    * node/provider that exposes type‑3 tx payload fields, or
    * an auxiliary index (e.g., Blobscan) to get blob count per tx.
* Store `blob_count` and `blob_versioned_hashes` where possible.

**Edge cases**

* Reorgs: always re-pull the last N days (N=7) and overwrite partitions (or keep versioned partitions and “latest view”).
* Failed txs: still pay base fee burn; ensure receipts with `status=0` are included. Blob fee is also charged per EIP‑4844 semantics; don’t drop failed txs.

### 8. Attribution/mapping requirements

* Phase 2 produces raw L1 tables; attribution is applied in Phase 4 using Phase 3 registry.

### 9. Validation and quality checks

* Block continuity: no missing block numbers in extracted range.
* Receipt coverage: ≥ 99.9% of tx hashes have receipts.
* Post‑Dencun blob sanity:

  * After `dencun_activation_utc`, `blob_gas_used` and `excess_blob_gas` should be present in headers.
  * Type‑3 txs should exist on active days; if none found for long windows, your extractor likely missed tx types.

### 10. Output specifications

* `data/raw/l1/blocks/*.parquet`
* `data/raw/l1/txs/*.parquet`
* `data/raw/l1/receipts/*.parquet`
* `data/raw/l1/blob_tx/*.parquet`

### 11. Success criteria

* Raw L1 dataset can recompute:

  * total L1 burn and tips for any subset of txs,
  * blob fee burn post‑Dencun (if blob tx fields are available).

### 12. Estimated effort and dependencies

* Effort: 5–20 person-days depending on infra and whether you index all txs.
* Dependencies: Phase 0 (date bounds) + Phase 3 if using narrow extraction.

---

## Phase 3 — Rollup attribution registry (versioned mapping of L1 activity to rollups)

### 1. Phase name and objectives

**Phase 3: Attribution registry**

* Build a **versioned rollup attribution registry** mapping L1 transactions to rollups via:

  * sender addresses (batch posters / sequencers / provers),
  * key destination contracts (inbox, output oracle, verifier),
  * validity windows (start/end dates),
  * evidence links and change log.

### 2. Data requirements

For each rollup:

* `rollup_id`
* Address sets (all optional but at least one required):

  * `batch_poster_addresses` (EOA/contract senders)
  * `prover_addresses`
  * `bridge/inbox/oracle/verifier_contracts` (to-addresses)
* Validity windows:

  * `valid_from_utc`, `valid_to_utc` (nullable for open-ended)
* Provenance:

  * `source_type` (Blobscan/L2BEAT/official docs/manual)
  * `source_url`
  * `evidence_note`

### 3. Primary source with detailed collection instructions

**Primary:** Combination of:

* Blobscan labels/utilities (if available) as seeds (Phase 1C)
* L2BEAT “tracked transactions” / project pages as seeds (manual capture)
* Official rollup docs/explorers (manual capture)

Because no single canonical registry exists, this phase is inherently “curation + verification.”

### 4. Secondary source with detailed collection instructions

**Secondary:** On-chain inference

* Discover new poster addresses by:

  * watching transactions that call known rollup inbox contracts,
  * clustering by recurrent senders,
  * confirming through rollup docs or explorer tags.

### 5. Specific metrics/fields to collect with definitions

Registry file: `rollup_registry_vX.Y.json` (or csv) with tables:

**Table A: rollups**

* `rollup_id` (primary key)
* `display_name`
* `tech` (optimistic/zk)
* `in_scope` (bool)
* `notes`

**Table B: address_mappings**

* `rollup_id`
* `address` (hex, checksum normalized)
* `address_role` (batch_poster | prover | misc)
* `valid_from_utc`
* `valid_to_utc`
* `source_url`
* `confidence` (high/med/low)

**Table C: contract_mappings**

* `rollup_id`
* `contract_address`
* `contract_role` (inbox | output_oracle | verifier | bridge | other)
* `valid_from_utc`
* `valid_to_utc`
* `source_url`
* `confidence`

### 6. Temporal parameters

* Registry covers whole analysis window (2022‑01‑01 → present).
* Update frequency:

  * scheduled: monthly review
  * event-driven: when coverage drops or new addresses detected

### 7. Collection procedure (step-by-step)

1. Start with `rollup_universe_v0.csv` (Phase 0).
2. For each in-scope rollup, populate initial addresses/contracts:

   * Prefer explicit references from official docs or explorer labels.
   * Add Blobscan/L2BEAT as supporting evidence, not sole evidence.
3. Validate each address:

   * Check it appears in L1 txs interacting with the rollup’s known contracts.
4. Set validity windows:

   * If exact changeover date known, set precisely.
   * Else:

     * set `valid_from` = first observed tx timestamp,
     * set `valid_to` = null and revise later.
5. Version and changelog:

   * Save registry as `data/reference/rollup_registry/v1.0/rollup_registry.json`
   * Maintain `data/reference/rollup_registry/CHANGELOG.md` recording:

     * what changed, why, evidence, date.

### 8. Attribution/mapping requirements

* Define attribution precedence rules (implemented in Phase 4):

  1. If `from_address` matches registry address with active validity → attribute to rollup.
  2. Else if `to_address` matches known inbox/verifier contract and sender is unknown → attribute with low confidence and add to “candidate new poster list.”
  3. Else un-attributed.

### 9. Validation and quality checks

* Coverage metric (post‑Dencun):

  * compute share of blob fee spend attributable to registry rollups; target ≥90% (research plan).
* Stability checks:

  * if top sender addresses by spend are un-attributed, registry is incomplete.
* Auditability:

  * every mapping row must have `source_url` and `confidence`.

### 10. Output specifications

* `data/reference/rollup_registry/vX.Y/rollup_registry.json`
* `data/reference/rollup_registry/CHANGELOG.md`
* `data/qa/registry_coverage_report_{run_date}.csv`

### 11. Success criteria

* Post‑Dencun: ≥90% of blob-carrying tx spend is attributable to registry entries.
* Pre‑Dencun: top rollup calldata spend largely attributable (target ≥80%, harder historically).

### 12. Estimated effort and dependencies

* Effort: 3–10 person-days initial build; then 0.5–1 day/month maintenance.
* Dependencies: Phase 1C/1B helpful; Phase 2 needed for validation.

---

## Phase 4 — Rollup-attributed L1 fee computation + burn/tips/blob decomposition (derived collection tables)

### 1. Phase name and objectives

**Phase 4: On-chain computed rent + decomposition**

* Compute daily rollup L1 cost from raw chain data using registry attribution.
* Decompose into:

  * base fee burn (EIP‑1559)
  * blob fee burn (EIP‑4844, post‑Dencun)
  * validator tips (priority fees)

### 2. Data requirements

Inputs:

* Phase 2 raw L1 blocks/receipts/txs (+ blob tx details)
* Phase 3 attribution registry

Outputs (daily, by rollup):

* `l1_total_cost_eth`
* `burn_base_eth`
* `burn_blob_eth`
* `tips_eth`
* `blob_base_fee_state` (daily avg/median)
* `blob_utilization` (daily blob gas used / max)

### 3. Primary source with detailed collection instructions

**Primary:** Raw chain data (Phase 2) + registry (Phase 3)

### 4. Secondary source with detailed collection instructions

* Blobscan and L2BEAT, used for:

  * missing blob_count per tx
  * reconciliation

### 5. Specific metrics/fields to collect with definitions

**Per transaction (derived)**

* `burn_base_wei = gas_used * base_fee_per_gas_wei`
* `tips_wei = gas_used * (effective_gas_price_wei - base_fee_per_gas_wei)`
* `burn_blob_wei = blob_gas_used_tx * base_fee_per_blob_gas_wei`

  * where `blob_gas_used_tx = blob_count * 131072`

**Per rollup per day (aggregate)**

* `l1_total_cost_eth = (sum(gas_used*effective_gas_price) + sum(burn_blob)) / 1e18`
* `burn_base_eth = sum(burn_base_wei)/1e18`
* `tips_eth = sum(tips_wei)/1e18`
* `burn_blob_eth = sum(burn_blob_wei)/1e18`

**Attribution labels**

* `rollup_id` or `unattributed`
* `attribution_confidence` (high/med/low)

### 6. Temporal parameters

* Start: 2022‑01‑01
* End: run date
* Granularity:

  * compute at tx-level then aggregate to daily
* Update frequency:

  * daily incremental recompute for last 7 days
  * monthly full recompute (ensures deterministic rebuild)

### 7. Collection procedure (step-by-step)

1. Load registry version pinned for the run (e.g., v1.2).
2. Join receipts/txs to blocks to get:

   * `base_fee_per_gas_wei` per tx (from block)
   * post‑Dencun blob header fields for blob base fee computation
3. Identify rollup-related txs:

   * `from_address` matches registry address within validity window.
4. Compute per-tx fee components:

   * burn_base, tips, burn_blob
5. Aggregate to daily rollup tables:

   * group by `date_utc` and `rollup_id`
6. Produce residual bucket:

   * `rollup_id="unattributed_rollup_like"` for txs going to rollup contracts but sender unknown
   * `rollup_id="other"` for everything else (optional)
7. Store both tx-level (sampled) and daily aggregates.

**Edge cases**

* Transactions with `effective_gas_price < base_fee_per_gas` should not occur; if seen, treat as data error.
* If blob_count missing for type‑3 tx:

  * mark tx `blob_count_missing=true`
  * attempt enrichment from Blobscan by tx hash
  * if still missing, exclude from burn_blob but keep separate “missing blob fee” bucket and report.

### 8. Attribution/mapping requirements

* All attribution must record:

  * registry version
  * rule used (from-match vs to-match)
* Keep a “candidate new poster address” list from residuals:

  * `data/qa/new_poster_candidates_{run_date}.csv`

### 9. Validation and quality checks

* Identity (per tx):
  `execution_fee_wei = gas_used * effective_gas_price_wei`
  `execution_fee_wei ≈ burn_base_wei + tips_wei` (exact in integer arithmetic)
* Post‑Dencun:

  * `burn_blob_wei >= 0` and correlates with blob tx presence.
* Cross-source reconciliation (monthly):

  * Compare on-chain `l1_total_cost_eth` vs growthepie `rent_paid_eth` by rollup and month:

    * target tolerance: 5–10% for top rollups; else explain and document.

### 10. Output specifications

* `data/analysis_ready/onchain_daily_rollup_costs.parquet`
* `data/normalized/onchain_tx_costs_sample.parquet` (optional sampled tx-level)
* `data/qa/reconciliation_growthepie_vs_onchain_{run_date}.csv`
* `data/qa/attribution_coverage_{run_date}.csv`

### 11. Success criteria

* Daily on-chain cost + decomposition exists for ≥95% of days for top rollups.
* Accounting identities hold.
* Attribution coverage meets targets (≥90% blob spend attributed post‑Dencun).

### 12. Estimated effort and dependencies

* Effort: 3–8 person-days depending on compute scale.
* Dependencies: Phase 2 + Phase 3.

---

## Phase 5 — Build the analysis-ready daily panel (STR inputs + regime variables + provenance)

### 1. Phase name and objectives

**Phase 5: Final daily panel assembly**

* Produce the single analysis-ready dataset for the research team:

  * by rollup by day
  * includes vendor fees, vendor rent, on-chain rent decomposition, blob regime vars, prices, issuance.

### 2. Data requirements

Join outputs from:

* Phase 1A vendor panel
* Phase 4 on-chain costs and decomposition
* Phase 1C blob regime metrics (or Phase 4 derived)
* Phase 1D prices and issuance

### 3. Primary source with detailed collection instructions

Primary is the integrated dataset built from earlier phases (internal).

### 4. Secondary source with detailed collection instructions

None (this is a merge); but keep source-level tables.

### 5. Specific metrics/fields to collect with definitions

Final table: `daily_rollup_panel`

**Keys**

* `date` (UTC)
* `rollup_id`

**Vendor series**

* `l2_fees_eth` (from growthepie)
* `l2_fees_usd` (optional)
* `vendor_rent_paid_eth` (growthepie)
* `vendor_profit_eth`
* `txcount`

**On-chain computed**

* `onchain_l1_cost_eth`
* `onchain_burn_base_eth`
* `onchain_burn_blob_eth`
* `onchain_tips_eth`
* `onchain_cost_coverage_flag` (if incomplete)

**Blob regime vars (daily)**

* `blob_base_fee_wei_avg`
* `blob_base_fee_wei_p50`
* `blob_utilization` (0–1)
* `blob_fee_at_min_flag` (base fee == 1 wei, or within epsilon)

**Macro inputs**

* `eth_usd_close`
* `issuance_eth`

**Provenance**

* `growthepie_run_date`, `onchain_run_date`, `registry_version`

### 6. Temporal parameters

* Start: 2022‑01‑01
* End: run date
* Granularity: daily
* Update frequency: daily (incremental rebuild for last 14 days; full rebuild monthly)

### 7. Collection procedure (step-by-step)

1. Validate each input table has consistent `date` domain and `rollup_id`.
2. Merge in this order:

   * growthepie vendor panel (base)
   * on-chain costs (left join; keep nulls)
   * blob regime vars
   * prices + issuance (global join by date)
3. Produce derived flags:

   * missingness indicators for each critical series.
4. Write final parquet and a CSV export.

### 8. Attribution/mapping requirements

* Registry version must be recorded per row.
* If registry updates, rebuild on-chain cost series for affected periods and bump dataset version.

### 9. Validation and quality checks

* Coverage:

  * `l2_fees_eth` and `vendor_rent_paid_eth` coverage ≥95% for in-scope rollups.
* Sanity:

  * STR denominator nonzero days: count and store.
* Outlier detection:

  * any day where `vendor_rent_paid_eth > l2_fees_eth` flagged (possible, but investigate).
* Reconciliation summary:

  * monthly diff between vendor rent and on-chain rent.

### 10. Output specifications

* `data/analysis_ready/daily_rollup_panel_v{dataset_version}.parquet`
* `data/analysis_ready/daily_rollup_panel_v{dataset_version}.csv`
* `docs/panel_schema.md`

### 11. Success criteria

* One file is sufficient for the analysis team to compute STR, decompositions, regime splits, and counterfactual inputs.
* Every figure in the research plan can be generated without additional data pulls.

### 12. Estimated effort and dependencies

* Effort: 1–2 person-days.
* Dependencies: Phase 1A, Phase 4, Phase 1D.

---

## Phase 6 — Ongoing operations: refresh cadence, drift detection, and reproducibility guarantees

### 1. Phase name and objectives

**Phase 6: Ops + monitoring**

* Ensure this becomes a living metric system:

  * daily updates
  * drift alerts
  * deterministic rebuilds

### 2. Data requirements

* Run logs and manifests
* Drift reports (metric catalog/origin list changes)
* QA dashboards (coverage + reconciliation)

### 3. Primary source with detailed collection instructions

Internal logs + manifests.

### 4. Secondary source with detailed collection instructions

None.

### 5. Specific metrics/fields to collect with definitions

* `run_id`, `run_date`, `git_commit_hash`
* `source_snapshots` (paths + hashes)
* `coverage_metrics`
* `reconciliation_metrics`

### 6. Temporal parameters

* Daily runs; weekly full refresh; monthly full rebuild.

### 7. Collection procedure (step-by-step)

1. Daily run:

   * pull growthepie incrementals + master.json snapshot
   * pull blob regime incrementals
   * refresh last 7 days of L1 raw (reorg-safe)
   * recompute Phase 4 aggregates for last 7 days
   * rebuild Phase 5 panel for last 14 days
2. Weekly run:

   * re-download growthepie full exports (detect revisions)
3. Monthly run:

   * full deterministic rebuild from raw snapshots

### 8. Attribution/mapping requirements

* If new poster candidates appear, update registry as vX.(Y+1) and rerun Phase 4 for affected ranges.

### 9. Validation and quality checks

* Alert triggers:

  * new growthepie metric keys
  * origin added/removed
  * attribution coverage falls below target
  * vendor vs on-chain rent diff exceeds thresholds

### 10. Output specifications

* `data/manifests/run_manifest_{run_id}.json`
* `data/qa/alerts_{run_date}.csv`

### 11. Success criteria

* Any run can be reproduced exactly using:

  * raw snapshots + pinned code + pinned registry version.

### 12. Estimated effort and dependencies

* Effort: initial 1–2 days to set up automation; then low ongoing.
* Dependencies: all prior phases.

---

## Phase 7 — Data storage, organization, naming conventions, and documentation (global)

### Directory structure (mandatory)

```
project_root/
  config/
    project.yml
    growthepie_metrics.yml
    l2beat_endpoints.yml
    blobscan_endpoints.yml
  data/
    raw/
      growthepie/
        master/YYYY-MM-DD/master.json
        export/{metric_key}/YYYY-MM-DD/{metric_key}.json
      l2beat/
        costs/YYYY-MM-DD/{slug}.json
      blobscan/
        {endpoint}/YYYY-MM-DD/*.json
      l1/
        blocks/run_date=YYYY-MM-DD/*.parquet
        txs/run_date=YYYY-MM-DD/*.parquet
        receipts/run_date=YYYY-MM-DD/*.parquet
        blob_tx/run_date=YYYY-MM-DD/*.parquet
    normalized/
      growthepie_metrics/...
      l2beat_costs_daily.parquet
      blobscan_blocks.parquet
      blobscan_daily.parquet
      prices_daily.parquet
      issuance_daily.parquet
    reference/
      origins_catalog.parquet
      metrics_catalog.parquet
      rollup_universe_v*.csv
      rollup_registry/
        vX.Y/rollup_registry.json
        CHANGELOG.md
    analysis_ready/
      vendor_daily_rollup_panel.parquet
      onchain_daily_rollup_costs.parquet
      daily_rollup_panel_v*.parquet
      daily_rollup_panel_v*.csv
    qa/
      *.csv
  docs/
    data_dictionary.md
    panel_schema.md
    l2beat_api_discovery.md
    blobscan_api_discovery.md
```

### File formats

* Raw: JSON (exact bytes from API), Parquet for L1 bulk tables
* Normalized/analysis-ready: Parquet (primary), CSV (export)
* Registry: JSON + CSV (both), versioned directory

### Snapshot/versioning approach

* Every pipeline run has:

  * `run_id` (UUID)
  * `run_date` (UTC date)
  * `git_commit_hash`
* Every raw file has:

  * SHA-256 checksum recorded in `data/manifests/raw_files.csv`

### Documentation requirements

* Every dataset has a short “README” with:

  * source + endpoint
  * extraction logic
  * known limitations
* Registry has changelog with evidence links.

---

## Notes the team must not ignore

1. **Do not trust dashboards without snapshotting.** Vendor series can revise history; your raw snapshot is the audit anchor.
2. **Blob fields are the #1 technical risk.** Validate early that your raw L1 extraction includes enough info to compute blob fees per tx.
3. **Registry versioning is non-negotiable.** If you change attribution, you must be able to reproduce the old results.

</data_collection_plan>

[1]: https://docs.growthepie.xyz/api "API | growthepie Knowledge"
[2]: https://l2beat.com/scaling/costs "Costs - L2BEAT"
