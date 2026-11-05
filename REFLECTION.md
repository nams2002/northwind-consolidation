# One-Page Reflection: Scaling Enterprise Financial Consolidation

**Bundle ID:** `NWG-D0BC`

---

## 1. What We Would Build Differently with 3 Months Instead of 12 Hours

With 3 months to build a production consolidation engine for Plainflow, we would evolve four core subsystems:

1. **Event-Sourced Double-Entry Ledger Store (PostgreSQL + Immutable Journal Graph):** Instead of in-memory dictionaries recomputed from flat CSVs on every run, every ERP import, local adjustment, FX retranslation, and consolidation elimination would be stored as an immutable, versioned journal event in PostgreSQL with `NUMERIC(28, 10)` fixed-point arithmetic. Every number on any statement would query a materialised lineage DAG back to the raw ERP payload hash.
2. **Multi-Step Ownership & Effective Interest Graph Engine:** Replace hardcoded 2-tier parent-subsidiary logic with a directed graph capable of handling step acquisitions, partial disposals, indirect/tiered holdings (e.g., US owns 80% of India, which owns 60% of Singapore), and equity-method associates (IAS 28).
3. **Interactive Controller Workbench with Diff & Sign-Off State:** Replace `policy_config.json` with a full review UI where controllers inspect held-for-review journals (`JE-009`, `JE-016`, `JE-020`), mapping overrides (`UK 2310 -> 2300`), and subledger variances (`UK £45,000 AR/AP`), attach supporting evidence, and cryptographically sign off on each resolution with a permanent audit log.
4. **Automated Cash Flow & Deferred Tax Consolidation:** Utilise the `cash_flow_category` metadata in `group_coa.csv` alongside working-capital FX separation (isolating real operating cash flows from closing-rate FX movements and acquisition opening balances) and IAS 12 deferred tax on consolidation adjustments.

---

## 2. Where This Prototype Would Break at Scale (Thousands of Accounts, Dozens of Entities)

1. **$O(N^2)$ Pairwise Intercompany Matching Across Multi-Hop Supply Chains:** Our prototype matches a single bilateral invoice table (`US` $\leftrightarrow$ `UK`) on exact `doc_ref` strings (`INV-US-2291`) and carries zero inventory markup. Across 50 entities trading goods in multiple currencies with credit notes, partial settlements, batched wire transfers, and **unrealised profit in ending inventory (URP)**, exact `doc_ref` matching breaks down. At scale, you need a bipartite graph matching engine with tolerance thresholds, automated clearing-house rules, and SKU/margin tracking to eliminate intercompany inventory markups.
2. **Memory & Latency of String-Concatenated Lineage (`source_rows`):** Concatenating `source_rows` strings (`tb_us.csv:L1; adjustments.json:L49...`) works cleanly for 3 entities and 72 monthly rows. With 50 entities, 10,000 local accounts, and millions of general ledger lines, string lists bloat memory and CSV exports. Production requires pointer-based lineage IDs stored in a relational join table (`statement_line_id -> ledger_batch_id -> raw_erp_row_id`).
3. **Stateful Multi-Year Roll-Forward of Historical Equity & Goodwill Pools:** Our prototype consumes a single `prior_year_group.csv` snapshot. Across dozens of entities acquired at different historical dates with partial impairments, dividends paid in foreign currencies, and share buybacks, the engine must maintain vintage-layered historical equity and goodwill ledgers per entity across reporting periods.

---

## 3. One Thing About This Problem We Think Plainflow Is Underestimating

**The "Post-Consolidation ERP Drift" Problem (Versioning Late Re-Exports Without Losing Human Judgment):**

In take-home benchmarks, the input bundle (`data/`) is frozen once and processed cleanly. In real mid-to-large enterprises during close week (Day 1 to Day 8), **subsidiary trial balances are never ingested once.** The India controller will re-export Tally Prime on Day 4 after fixing GST (`JE-016`), the UK controller will re-export Sage 50 on Day 5 after posting a contra entry for the £45,000 AR/AP subledger variance, and the US team will send a revised `adjustments_v4.json` two hours before the audit committee deck is due.

The hardest engineering problem in AI-native financial reporting is not running the first consolidation pass—it is **stateful delta re-consolidation**. When an entity uploads `tb_uk_v2.csv`, the system must deterministically diff `v2` against `v1`, preserve every human controller sign-off and mapping override that still applies, automatically invalidate and re-open any human sign-off whose underlying source rows changed (for example, automatically dropping manual journal `JE-008` if the UK controller subsequently booked that £22,000 depreciation inside `tb_uk_v2.csv`), and show the CFO an exact waterfall of what changed between Draft 1 and Draft 2. Building that **stateful diff-and-invalidation engine** is far harder than the consolidation math itself, and it is what ultimately determines whether finance teams trust the platform during a live close.