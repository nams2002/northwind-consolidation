# Validation: How I Know the Outputs Are Correct

**Bundle ID:** `NWG-D0BC`

This file separates three things: checks the pipeline runs on itself, tests that compare outputs with independent recomputation, and mistakes made by AI tools that review found.

---

## 1. Checks coded in the pipeline (`src/verifier.py`)

Every run of `python -m src.main` executes five assertions before any file is written. A failure raises `AssertionError` and aborts with no output.

| # | Check | Result on this bundle |
| :-- | :--- | :--- |
| 1 | Consolidated TB zero-sum (all 31 group accounts) | Residual 0.00 |
| 2 | Balance sheet identity: assets = liabilities + equity | Residual 0.00 (£28,596,245.74 = £10,231,437.86 + £18,364,807.88) |
| 3 | Profit attribution: group profit = owners + NCI | £2,789,654.53 = £2,724,621.75 + £65,032.78 |
| 4 | Each of `ELIM-01` to `ELIM-05` balances (debits = credits) | Pass |
| 5 | Translation reserve movement recomputed from six exposures matches the equity bridge within £0.01 | Difference £0.0069 |

**Limitation, stated plainly.** The translation reserve (3300) is the balancing figure in equity, so checks 1 and 2 hold by construction for that line. They catch lost or duplicated lines, not a wrong reserve. Check 5 is the independent test of 3300.

---

## 2. Tests (`tests/`)

| File | What it does | Independent of the pipeline? |
| :--- | :--- | :--- |
| `test_consolidation.py` | Runs the pipeline and checks that all required files exist, the control figures equal the values I have reviewed, the TB and each elimination balance, and every trap is logged in `issues.json`. | **No.** It is a regression (snapshot) test: it protects against change but cannot show the figures are right. |
| `test_independent_recompute.py` | Re-derives goodwill, NCI, group revenue and group profit from the raw CSV/JSON inputs with plain code, and checks India's Q1 + H2 against the 9-month trial balance and the INR 678M acquisition net assets. It imports nothing from `src/`. | **Yes.** |

I also confirmed the independent test can fail: changing the expected NCI share from 20% to 25% makes `test_goodwill_and_nci` fail.

---

## 3. Independent recomputation

All figures below were recomputed from the raw input files, not from pipeline output.

### A. Revenue

| Entity | Calculation | GBP |
| :--- | :--- | ---: |
| US | $18,400,000 / 1.2780 (FY average) | 14,397,496.09 |
| UK | £9,850,000 (`4000` Sales only; `2310` Deferred income is a liability) | 9,850,000.00 |
| India | INR 437,000,000 (Jul to Dec) / 107.7918 (H2 average) | 4,054,111.72 |
| **Group revenue** | | **28,301,607.81** |

### B. Profit, NCI and goodwill

| Item | Calculation | Result |
| :--- | :--- | ---: |
| US profit | $1,856,250 (after posted journals) / 1.2780 | £1,452,464.79 |
| UK profit | £1,044,292.28 per TB, less posted journals £12,200, less in-transit invoice £8,108.54, less FX retranslation loss £11,957.88 | £1,012,025.86 |
| India H2 profit | INR 35,050,000 / 107.7918 | £325,163.88 |
| **Group profit** | | **£2,789,654.53** |
| NCI profit | 20% x INR 35,050,000 / 107.7918 | £65,032.78 |
| NCI closing | 20% x (INR 678,000,000 + 35,050,000) / 107.28186 | £1,329,302.08 |
| Goodwill | (INR 690,000,000 - 80% x INR 678,000,000) / 107.28186 | £1,375,815.07 |

GBP/INR rates are cross rates (Policy 2): closing 1.2530 x 85.62 = 107.28186; H2 average 1.2840 x 83.95 = 107.7918.

### C. Opening equity

US net assets excluding the UK investment: $2,000,000 + $14,069,373.43 - $1,270,000 = $14,799,373.43. At the opening rate 1.2730 this is £11,625,587.93. Adding UK net assets (£1,000,000 share capital + £1,641,510 reserve = £2,641,510) gives £14,267,097.93, matching `prior_year_group.csv` (£1,250,000 + £12,604,747.93 + £412,350) to the penny.

### D. Translation reserve movement (£43,786.11)

| Exposure | Amount | Rate move | GBP |
| :--- | ---: | :--- | ---: |
| US remaining opening net assets | $6,525,000 | 1.2730 to 1.2530 | +81,814.64 |
| US cash used for India acquisition | $8,274,373.43 | 1.2730 to 1.2645 (1 Jul spot) | +43,692.49 |
| US FY2024 profit | $1,856,250 | 1.2780 (average) to 1.2530 | +28,979.74 |
| India acquisition net assets, 80% | INR 542,400,000 | 105.4467 (spot) to 107.28186 | -87,992.40 |
| India H2 profit, 80% | INR 28,040,000 | 107.7918 to 107.28186 | +1,236.47 |
| India goodwill | INR 147,600,000 | 105.4467 to 107.28186 | -23,944.83 |
| **Direct sum** | | | **43,786.11** |

The unrounded difference from the equity bridge is £0.00695. It comes from two inputs that were rounded to 2 decimals: the US books record the India investment as $8,274,373.43 (exact: $8,274,373.4261, worth £0.0031 at closing) and `prior_year_group.csv` rounds opening retained earnings (£0.0038). Together £0.0069.

### E. Reconciliations to source

- India: Q1 + H2 in `in_pl_monthly.csv` equals the 9-month `tb_in.csv` for all eight P&L ledgers. Q1 profit is exactly INR 18,000,000, and INR 250M + 410M + 18M = INR 678M, matching `acquisition_note.md`.
- Subledgers: US and India AR/AP tie to `subledger_controls.csv` exactly. UK AR and AP are each £45,000.00 above their controls (`ISS-SUB-001`).
- Intercompany: £20,066.42 = £8,108.54 (in transit) + £11,957.88 (retranslation). P&L £10,074.75 = £8,108.54 + £1,966.21 (FX on elimination).

### F. Disclosed rounding

Each reported figure is rounded to 2 decimals (Policy 7), so lines on a statement can differ from their total by 1p. The P&L lines sum to £2,789,654.52 against the reported £2,789,654.53. `ELIM-03` debits and credits in `eliminations.csv` differ by 1p (£65,341.90 against £65,341.89).

---

## 4. Things AI tools got wrong (found in review)

These were found by re-reading the AI-written deliverables against the code and data, and by re-running the pipeline.

### Mistake 1: Wrong line references in the architecture document
- **What went wrong:** The trace example cited `tb_us.csv:L23` for account 6500 (real row: L24) and journal lines such as `adjustments.json:L125 (JE-007)` (real: L123). `ISS-JE-020` also cites `in_pl_monthly.csv:L45` for December depreciation (real: L46).
- **How it was caught:** Comparing the document with the `source_rows` in `profit_and_loss.json` and with the row numbers in the data files.
- **Fix:** References corrected in `ARCHITECTURE.md`. Commit: `corrected ARCHITECTURE.m`. The `L45` text in `ISS-JE-020` is still open, see section 5.

### Mistake 2: This validation document described a check that did not exist
- **What went wrong:** An earlier draft said `verifier.py` asserts that India's Q1 + H2 equals the YTD trial balance. The verifier's fifth check is the translation reserve proof. The draft also gave the `ELIM-02` total as £7,867,594.17; `eliminations.csv` totals £7,867,610.17.
- **How it was caught:** Diffing the document against `src/verifier.py` and the generated CSV.
- **Fix:** This document rewritten to match the code, and the Q1 + H2 reconciliation added as an independent test. Commit: 'corrected VALIDATION.md`.

### Mistake 3: The repo did not run from a fresh clone
- **What went wrong:** The README told the reader to `pip install -r requirements.txt`, but the file did not exist, and the README ended without a run command.
- **How it was caught:** Walking through the README steps as a new user.
- **Fix:** `requirements.txt` added and README completed. Commit: `requirements.txt`.

---

## 5. Known open items

- Acquisition inputs and some verifier inputs are written into the code, so a changed `acquisition_note.md` would not flow through.
- The mapping guard (`2310` to `4100`) and the depreciation check (`JE-020`) target this bundle's defects, not general rules.
- `policy_config.json` keys other than `force_post_held_journals`, `mapping_overrides`, `missing_fx_policy.UK_1210_SGD_closing_rate`, `bundle_id` and `initials` are not read by the code.
- The unbalanced-journal message in `issues.json` always says an injection was found and quotes USD, whatever the entity.
- `ISS-JE-020` cites `in_pl_monthly.csv:L45`; the correct row is L46.
- UK £45,000.00 AR/AP variance: flagged, not adjusted. If a controller adjusts it, total assets and total liabilities each fall by £45,000.00 and equity is unchanged.