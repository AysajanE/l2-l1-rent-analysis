**Meta-Block**

* **Scope:** End-to-end empirical research plan to test whether Ethereum L1 captures durable economic rent from L2 scaling (rollups), using a single primary metric (“Settlement Take Rate”) plus on-chain validation and policy counterfactuals.
* **Confidence score:** 0.86 (data sources exist and the hypothesis is falsifiable; the main execution risk is address attribution + metric-definition drift across dashboards).
* **Perspective:** Skeptical, investor/governance-grade measurement. Treat dashboards as *claims* that must be reconciled to raw chain data.

---

## RESEARCH OVERVIEW

### Core research question

**Is Ethereum L1’s “take rate” on rollup economics rising, stable, or decaying toward ~0 as L2 usage scales?**

This operationalizes Lyn Alden’s core critique: *utility rails face competition and their revenues trend toward marginal cost*, so coinholders often don’t capture sustained value—even if the rails are useful.

### Research objectives and scope

**Objective 1 (primary):** Quantify and trend-test Ethereum L1’s take rate on L2 user-fee revenue using real data.
**Objective 2 (mechanism):** Decompose the take rate into **(i) burn to all ETH holders** vs **(ii) tip revenue to validators/stakers**, and test whether rollup scaling reliably increases either. ([Ethereum Improvement Proposals][1])
**Objective 3 (regimes):** Identify whether take rate is **regime-dependent** (e.g., “blob fees at minimum for long periods” vs “blob congestion spikes”). ([Galaxy][2])
**Objective 4 (policy):** Quantify how a blob-fee floor/reserve mechanism (e.g., EIP‑7918) would have changed take rate historically (counterfactual).

**Scope boundaries (keep it sharp):**

* Focus on **Ethereum mainnet settlement** and **rollups that post data to Ethereum** (optimistic + ZK rollups).
* Time window: from **Jan 1, 2022 → present** (captures meaningful L2 era; includes EIP‑4844 “Dencun” regime change on **March 13, 2024**). ([Galaxy][2])
* Exclude: token price forecasting, “ETH monetary premium” debates not tied to measurable fee/burn/issuance channels, and non-Ethereum DA (except as a competitive explanation, not as the core measurement).

### Why this research matters

* **Investors:** Separates “Ethereum is used” from “ETH captures value,” directly addressing Alden’s “rails vs value capture” critique.
* **Governance / protocol design:** Provides evidence for or against changes aimed at tightening the link between L2 growth and L1 economics (e.g., EIP‑7918’s reserve price motivation).
* **L2 ecosystem participants:** Makes L2 margin vs L1 rent explicit, enabling honest discussion of who captures surplus.

---

## THEORETICAL FRAMEWORK

### Key hypotheses to be tested

Define the single “hinge” metric first.

#### Primary metric: Settlement Take Rate (STR)

For day *t*:

[
\textbf{STR}*t ;=; \frac{\sum_i \text{RentPaid}*{i,t}}{\sum_i \text{L2Fees}_{i,t}}
]

Where for each rollup *i*:

* **L2Fees_{i,t}:** total fees paid by users on that L2 on day *t*.
* **RentPaid_{i,t}:** total fees the L2 paid to Ethereum L1 for posting data/proofs/state updates on day *t* (“rent” to L1). (This aligns to standard “rent paid” / “costs” concepts in L2 fundamental datasets.) ([labels.growthepie.com][3])

#### Hypotheses (falsifiable)

**H0 (Minimum viable bear):**

* STR has a **negative trend**, and/or
* STR is **structurally lower** post‑Dencun (EIP‑4844) than pre‑Dencun, and remains low as L2s scale.
  Interpretation: L1 DA/settlement becomes **commodity-priced**, L2s keep margin, ETH fee/burn linkage weakens. ([Galaxy][2])

**H1 (Minimum viable bull):**

* STR is **stable or rising** with L2 scale (or rises during high-usage regimes), implying L1 captures durable rent from L2 growth.
  Interpretation: Ethereum functions as a “court system” with pricing power; L2 growth mechanically feeds ETH burn and/or validator revenue. ([Ethereum Improvement Proposals][1])

**H2 (Regime dependence):**
STR is materially higher when blob markets are *not* pinned near minimum prices and/or when blob utilization is high; otherwise STR compresses. ([Galaxy][2])

**H3 (Policy counterfactual):**
A reserve/floor mechanism (EIP‑7918) would materially raise the lower tail of blob fees and increase STR and rollup-driven burn in historical data.

### Bull vs bear articulation (consolidated)

* **Bull story (must show up in data):** “As L2 usage grows, L2s pay non-trivial rent to L1 often enough that L1 burn + validator tips scale with L2 activity.”
* **Bear story (must show up in data):** “L2 usage grows, but blob DA stays cheap most of the time; L2s keep most economics; L1 rent capture trends toward zero share.”

### Critical variables and mechanisms

**Mechanisms on L1 (value accrual channels):**

* **Base fee burn** (EIP‑1559): base fee is burned; validators keep only priority fees. ([Ethereum Improvement Proposals][4])
* **Blob fee burn** (EIP‑4844): blob fee is deducted and **burned** (not refunded even if tx fails). ([Ethereum Improvement Proposals][1])
* **Priority fees (“tips”)**: paid to validators (and thus to stakers after MEV‑Boost/PBS flows, depending on setup). ([Galaxy][2])

**Mechanisms on L2 (economic production and margin):**

* **User fee revenue** (denominator of STR).
* **L1 rent/costs** (numerator).
* **L2 profit margin**: L2Fees − RentPaid (important for interpreting who captures surplus).

---

## RESEARCH DESIGN & METHODOLOGY

### Phase 0 — Research protocol and preregistration

**Objectives**

* Lock definitions before touching results to prevent “metric shopping.”
* Specify rollup inclusion criteria and cutoffs.

**Methods**

* Draft a short preregistered protocol with:

  * Primary question + hypotheses (H0–H3).
  * Exact STR formula(s) and units (ETH-native first; USD second).
  * Inclusion list rules (e.g., top rollups by fees/tx count; must settle to Ethereum L1).
  * Key regime dates: Dencun (March 13, 2024) and any other identified protocol breaks. ([Galaxy][2])

**Outputs**

* Protocol document + data dictionary + analysis checklist.

**Success criteria**

* A third party can read the protocol and reproduce the analysis plan without extra interpretation.

---

### Phase 1 — Data inventory and acquisition (off-chain + on-chain)

**Objectives**

* Build a daily panel dataset containing L2 fees, L1 rent, and blob market conditions.

**Primary data sources**

1. **growthepie API** (daily L2 fundamentals: fees, rent paid, profit, tx counts).

   * Use the public API endpoint and export endpoints for full history.
2. **L2BEAT costs** as an independent dataset for L1 costs by rollup (triangulation + methodological cross-check). ([labels.growthepie.com][5])
3. **Blobscan API** for blob usage and blob-carrying tx metrics, plus rollup labeling utilities to help attribution. ([docs.blobscan.com][6])
4. **Raw Ethereum L1 data** (blocks, txs, receipts; blob fields post‑4844):

   * BigQuery/public chain datasets or self-hosted archive node indexing (choose based on budget/infra).
   * Must include `base_fee_per_gas`, `gas_used`, `effective_gas_price`, and blob-related fields (`blob_gas_used`, `excess_blob_gas`, blob tx identification). ([Ethereum Improvement Proposals][1])

**Collection approach**

* Build an automated ETL that:

  * Downloads/caches daily growthepie fundamentals.
  * Pulls L2Beat cost series at consistent granularity.
  * Pulls Blobscan blob time series (block/day aggregates and rollup blob usage).
  * Extracts L1 tx fee components for rollup-related transactions from raw chain data.

**Outputs**

* Raw “landing” tables (immutable snapshots) + normalized analysis tables.

**Success criteria**

* ≥95% day coverage for the included rollups over the analysis window.
* A deterministic rebuild from raw snapshots.

---

### Phase 2 — Rollup attribution map (who is paying L1 rent?)

**Objectives**

* Accurately attribute L1 transactions (especially blob-carrying transactions) to specific rollups.

**Methods**

* Create a **versioned rollup attribution registry**:

  * Batch poster / sequencer submission addresses.
  * Key contracts (inbox, output oracle, validity proof contract) where relevant.
* Seed the registry from:

  * Blobscan rollups utility and metadata. ([docs.blobscan.com][7])
  * L2Beat tracked costs context (which rollups, what types of costs). ([labels.growthepie.com][5])
  * Official rollup docs/explorers as needed (explicitly recorded in registry with sources).

**Outputs**

* `rollup_registry_vX.Y` (CSV/JSON) + change log.

**Success criteria**

* For post‑Dencun period: ≥90% of blob-carrying tx spend is attributable to a known rollup registry entry (measured by fee volume).

---

### Phase 3 — Metric construction (STR + decomposition)

**Objectives**

* Compute STR and its decompositions in a way that is consistent across regimes (pre- and post‑4844).

**Core computed metrics**

1. **STR (total):**

   * Numerator: `RentPaid` (total L1 cost borne by rollups).
   * Denominator: `L2Fees` (total user fees paid on L2).
2. **Burn vs tips decomposition (Ethereum value accrual channels):**

   * **Base fee burn** (EIP‑1559):
     [
     \text{BurnBase}_{tx} = \text{gasUsed} \times \text{baseFeePerGas}
     ]
     (base fee is always burned). ([Ethereum Improvement Proposals][4])
   * **Blob fee burn** (EIP‑4844):
     [
     \text{BurnBlob}_{tx} = \text{blobGasUsed} \times \text{baseFeePerBlobGas}
     ]
     (blob fee burned). ([Ethereum Improvement Proposals][1])
   * **Validator tips**:
     [
     \text{Tips}*{tx} = \text{TotalFeePaid}*{tx} - \text{BurnBase}*{tx} - \text{BurnBlob}*{tx}
     ]
     (priority fees go to validators). ([Galaxy][2])
3. **Rollup margin metrics**

   * `L2Profit = L2Fees - RentPaid`
   * `L2ProfitMargin = L2Profit / L2Fees`
4. **Relevance-to-supply metric (stakeholder-facing)**

   * `RollupBurnShareOfIssuance = (BurnBase + BurnBlob attributable to rollups) / Issuance`
   * Issuance can be sourced/estimated from Ethereum issuance documentation and/or consensus-layer data feeds; treat as its own validated input.

**Outputs**

* Analysis-ready daily panel dataset:

  * By-rollup-by-day + ecosystem aggregates.
* Unit-tested metric functions.

**Success criteria**

* Internal accounting identities hold (e.g., total fee = burn + tips + blob burn) within rounding error.

---

### Phase 4 — Validation and reconciliation (no “dashboard science”)

**Objectives**

* Ensure STR isn’t an artifact of one vendor’s methodology.

**Validation strategy (triangulation)**

1. **RentPaid cross-check**

   * Compare:

     * growthepie `rent_paid`
     * L2Beat cost series
     * on-chain computed L1 fees for rollup-submitter addresses (from the registry)
   * Reconcile differences by:

     * Address coverage gaps
     * Misattributed tx categories (proof submissions vs batch submissions)
     * Unit conversion timing (ETH price used for USD series)

2. **Fees cross-check**

   * For a subset of top rollups (e.g., top 5 by fees):

     * Compare growthepie user-fee totals to rollup explorer stats or on-chain fee vault inflows where measurable.

**Outputs**

* Validation report:

  * per-rollup error bands
  * “trusted series” selection rules
  * residual analysis (what’s missing and why)

**Success criteria**

* Monthly aggregates match within pre-specified tolerance (e.g., <5–10% depending on rollup) or have a documented cause.

---

### Phase 5 — Core empirical analysis (answer the single question)

**Objectives**

* Determine whether STR is rising, stable, or decaying, and whether it scales with L2 growth.

**Analytical approaches**

1. **Trend test (primary)**

   * Plot STR(t) with 7d/30d smoothing.
   * Fit a time trend with HAC/Newey–West errors (time series autocorrelation).
   * Nonparametric monotonic trend test (Mann–Kendall) as robustness.

2. **Structural break test**

   * Explicit break at **March 13, 2024 (Dencun/EIP‑4844 activation)**. ([Galaxy][2])
   * Use Chow test / Bai–Perron multiple break detection to see if STR regime shifted and whether it reverted.

3. **Elasticity test (scaling test)**

   * Estimate:

     * `log(RentPaid_total) ~ α + β log(L2Fees_total) + controls`
     * `log(RentPaid_total) ~ α + β log(L2TxCount_total) + controls`
   * Interpretation:

     * β ≈ 1 → rent scales proportionally with L2 activity (supports bull channel).
     * β ≈ 0 → rent decouples from scaling (supports bear channel).

4. **Blob relevance test (are blob fees “basically irrelevant”?)**

   * Compute:

     * fraction of days `baseFeePerBlobGas` is at/near the minimum (per EIP‑4844 min base fee is 1). ([Ethereum Improvement Proposals][1])
     * distribution of blob fees and their contribution to total rollup L1 spend.
   * Relate STR to blob market states:

     * `STR(t) ~ f(blob_utilization, baseFeePerBlobGas, L1 baseFeePerGas, …)`

5. **Decomposition analysis**

   * Report how much of rollup-paid L1 rent becomes:

     * burn (benefits all holders)
     * validator tips (benefits stakers)
   * This directly maps to ETH value accrual channels defined by EIP‑1559 and EIP‑4844. ([Ethereum Improvement Proposals][1])

**Expected outputs**

* A small set of stakeholder-grade figures (see “Visualization requirements” below).
* Statistical appendix (regression tables + diagnostics).

**Success criteria**

* Clear directional conclusion on STR trend and scaling elasticity, robust to:

  * rollup set choices
  * outlier trimming
  * alternative data sources (growthepie vs L2Beat vs on-chain)

---

### Phase 6 — Policy and counterfactual analysis (EIP‑7918-style reserve price)

**Objectives**

* Quantify whether “fixing blob underpricing” would have materially altered take rate historically.

**Method**

* Implement the EIP‑7918 reserve/floor mechanism as specified (reserve price tied to execution base fee).
* Recompute a **counterfactual blob fee series** and resulting:

  * `RentPaid_cf`
  * `STR_cf`
  * `BurnBlob_cf`
* Compare to Fidelity-style interpretation: blob fees often go to zero for prolonged periods; a reserve price is proposed to prevent underpricing and strengthen economic ties to L2 usage.

**Outputs**

* Counterfactual STR “what would have happened” charts.
* Sensitivity analysis over key parameter assumptions.

**Success criteria**

* Counterfactual is fully auditable (every transformation traceable to protocol rules + observed base fees).

---

### Phase 7 — Synthesis and stakeholder communication

**Objectives**

* Convert metrics into a decision-relevant narrative (without hand-waving).

**Methods**

* Build an interpretation rubric (see Decision Criteria below).
* Produce two layers:

  * **Executive summary** (what the data says, what it implies).
  * **Technical appendix** (data sources, validation, robustness, code pointers).

**Outputs**

* Investor/governance deck
* Full report
* Reproducible repo + dataset release (if permitted)
* Optional dashboard (STR + decompositions over time)

**Success criteria**

* A skeptical reviewer can reproduce the headline figure from raw data.

---

## DATA REQUIREMENTS

### Required datasets (minimum viable)

**Off-chain standardized metrics**

* growthepie API:

  * daily `fees`, `rent_paid`, `profit`, `txcount` by rollup.
* L2Beat costs:

  * cost breakdown series for rollups (independent cross-check). ([labels.growthepie.com][5])
* Blobscan API:

  * blob usage metrics + rollup mapping utilities. ([docs.blobscan.com][6])

**On-chain Ethereum data**

* Blocks/headers: base fee, blob gas used, excess blob gas. ([Ethereum Improvement Proposals][1])
* Transactions/receipts: gas used, effective gas price, tx type (including type‑3), sender/recipient.
* For post‑4844 blobs: fields required to compute blob fees per spec. ([Ethereum Improvement Proposals][1])

**Protocol/event metadata**

* Dencun activation time and context (for regime split). ([Galaxy][2])
* EIP‑1559 and EIP‑4844 semantics (burn vs tips vs blob burn). ([Ethereum Improvement Proposals][4])

### Data validation approaches (non-negotiable)

* **Triangulation** of key series (RentPaid and fees) across at least two independent sources plus on-chain computation where feasible.
* **Attribution registry** versioning with audit trail.
* **Snapshotting** all third-party API pulls (avoid “moving target” dashboards).

### Tools and infrastructure

* **Data layer:** BigQuery (or equivalent), plus local parquet snapshots.
* **Pipeline:** Python + SQL; deterministic builds; CI tests.
* **Reproducibility:** Git + locked dependencies + data versioning (DVC or similar).
* **Statistical tooling:** robust time-series regression with HAC errors; bootstrap methods for confidence bands.

---

## ANALYSIS PLAN

### Statistical tests and estimands

**Primary estimand:** slope/trend of STR(t) and post‑ vs pre‑Dencun level shift.
**Secondary estimands:** elasticity β of rent vs L2 scale; regime effect sizes; burn-vs-tips decomposition shares.

Recommended tests:

* Mann–Kendall trend test (monotonic trend; distribution-free).
* OLS with Newey–West standard errors for STR trend and elasticity regressions.
* Chow test / Bai–Perron for structural breaks.
* Block bootstrap for confidence intervals (handles autocorrelation).

### Visualization requirements (the “must-have” charts)

1. **STR over time** (aggregate + top rollups), annotated with Dencun date.
2. **RentPaid vs L2Fees scatter** (log-log), with fitted elasticity line.
3. **Decomposition of RentPaid:** burn (base+blob) vs tips over time.
4. **Blob market state:** baseFeePerBlobGas distribution + fraction of time at minimum + overlay with STR.
5. **Rollup-driven burn vs issuance** (ratio time series; rolling averages).

### Interpretation framework

Translate numbers into the bull/bear language explicitly:

* **Evidence for “commoditized DA” (bear-leaning):**

  * STR trends downward and remains low post‑Dencun.
  * Rent elasticity to L2 scale ≈ 0 or very small.
  * Blob fees mostly at/near minimum; spikes are rare and do not shift long-run STR. ([Galaxy][2])

* **Evidence for “monetized settlement layer” (bull-leaning):**

  * STR stable or rising with scale (or rises in predictable high-demand regimes).
  * Rent elasticity meaningfully > 0 and stable across robustness checks.
  * Rollup-driven burn becomes a non-trivial, persistent component relative to issuance.

---

## DELIVERABLES & COMMUNICATION

### Outputs to produce

1. **Research protocol + codebook** (frozen before results).
2. **Validated dataset** (daily panel + rollup registry + snapshots).
3. **Technical report** (methods, validation, tests, robustness).
4. **Stakeholder deck** (10–15 slides) with:

   * the one question
   * STR results
   * decomposition and implications
   * policy counterfactuals
5. **Reproducible code repository** (ETL + analysis + figure generation).
6. Optional: **Interactive dashboard** for ongoing monitoring.

### Decision criteria based on results (explicit)

Use a simple rubric for stakeholders:

* **Grade A (supports ETH value-accrual via L2 growth):**

  * STR is non-decreasing (statistically + visually) and elasticity is clearly positive.
  * Decomposition shows meaningful burn/tips scaling with L2 activity.

* **Grade B (mixed):**

  * STR flat but low; rent scales in levels but share remains small; burn channel weak, tips channel moderate.

* **Grade C (supports Alden-style commoditization thesis):**

  * STR decays toward ~0 and/or rent elasticity ≈ 0; blob fees largely irrelevant outside brief spikes.

---

## TIMELINE & MILESTONES

Suggested sequencing (you can compress or expand depending on staffing):

1. **Milestone 1 — Protocol lock**

   * Finalize hypotheses, definitions, rollup inclusion list, and validation plan.

2. **Milestone 2 — Data pipeline operational**

   * Automated pulls + raw on-chain extracts + immutable snapshots.

3. **Milestone 3 — Attribution registry v1**

   * Rollup mapping validated on post‑4844 blob txs.

4. **Milestone 4 — Validation report**

   * growthepie vs L2Beat vs on-chain reconciled; tolerances met or deviations explained.

5. **Milestone 5 — Core STR results**

   * Trend + break + elasticity + decomposition figures complete.

6. **Milestone 6 — Counterfactual results**

   * EIP‑7918 scenario analysis delivered with sensitivity bands.

7. **Milestone 7 — Stakeholder package**

   * Deck + report + repo released (internal or public).

---

## RISKS & LIMITATIONS

### Data quality / definition risks

* **Metric-definition drift:** “fees” and “rent paid” may differ across providers and over time (methodology updates).
  **Mitigation:** snapshot inputs; triangulate; publish reconciliation table.

* **Attribution incompleteness:** rollups change batcher addresses; multiple posters; shared infra; proofs vs batches.
  **Mitigation:** versioned registry; periodic re-labeling; residual bucket; sensitivity analysis excluding ambiguous txs.

* **Denominator manipulation:** L2 fees can be policy-controlled (subsidies, fee holidays), affecting STR even if L1 rent is unchanged.
  **Mitigation:** report both **ratio (STR)** and **level** results (RentPaid in ETH/day), plus alternative denominators (tx count, data posted).

### Methodological limitations

* **Causality vs correlation:** STR trend may reflect changing fee policy, compression tech, and demand; not a single causal driver.
  **Mitigation:** regime splits, event studies, and transparent “mechanism mapping” rather than over-claiming causality.

* **USD conversions add noise:** ETH price volatility can distort USD series.
  **Mitigation:** do primary analysis in ETH units; use USD as secondary.

### External validity

* Future protocol changes (e.g., blob fee mechanism changes, capacity changes) can shift conclusions.
  **Mitigation:** treat this as a living metric framework; update STR monitoring post-upgrades; include counterfactual modules.

---

```text
Selected sources (requested link format)
[Alden 2025](https://www.lynalden.com/why-most-cryptocurrencies-wont-accrue-value/ "Why Most Cryptocurrencies Won’t Accrue Value")
[EIP-1559 2019](https://eips.ethereum.org/EIPS/eip-1559 "EIP-1559: Fee market change for ETH 1.0 chain")
[EIP-4844 2022](https://eips.ethereum.org/EIPS/eip-4844 "EIP-4844: Shard Blob Transactions")
[EIP-7918 2025](https://eips.ethereum.org/EIPS/eip-7918 "EIP-7918: Blob base fee bounded by execution cost")
[growthepie 2025](https://docs.growthepie.xyz/api "API | growthepie Knowledge")
[L2BEAT 2026](https://l2beat.com/scaling/costs "Costs - L2BEAT")
[Blobscan 2025](https://docs.blobscan.com/docs/api "API - Docs")
[Galaxy 2024](https://www.galaxy.com/insights/research/ethereum-150-days-after-dencun "150 Days After Dencun | Galaxy")
[Fidelity 2025](https://www.fidelitydigitalassets.com/research-and-insights/fusaka-upgrade-scaling-meets-value-accrual "The Fusaka Upgrade: Scaling Meets Value Accrual")
```

[1]: https://eips.ethereum.org/EIPS/eip-4844 "EIP-4844: Shard Blob Transactions"
[2]: https://www.galaxy.com/insights/research/ethereum-150-days-after-dencun "150 Days After Dencun | Galaxy"
[3]: https://labels.growthepie.com/fundamentals/rent-paid?utm_source=chatgpt.com "Rent Paid to L1"
[4]: https://eips.ethereum.org/EIPS/eip-1559 "EIP-1559: Fee market change for ETH 1.0 chain"
[5]: https://labels.growthepie.com/fundamentals/rent-paid "Rent Paid to Ethereum | growthepie"
[6]: https://docs.blobscan.com/docs/api "API - Docs"
[7]: https://docs.blobscan.com/docs/codebase-overview?utm_source=chatgpt.com "Codebase overview - Docs"
