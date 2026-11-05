# Output Validation, Independent Recomputations & AI Error Log

**Bundle ID:** `NWG-D0BC`

---

## 1. Automated Invariant Checks Coded (`src/verifier.py` & `tests/`)

Every run of `python -m src.main` executes five hard assertions in `src/verifier.py` before writing `/output`:

1. **Consolidated Trial Balance Zero-Sum Check:** Verifies $\sum_{c \in \text{COA}} \text{NetBalance}_{\text{GBP}}(c) = 0.00$ across all 31 accounts (actual residual: `£0.00000000`).
2. **Balance Sheet Accounting Identity (`A = L + E`):** Verifies Total Assets (**£28,596,245.74**) − Total Liabilities (**£10,231,437.86**) = Total Equity (**£18,364,807.88**) to `< 1e-6`.
3. **Profit Attribution Split:** Verifies Group Profit (**£2,789,654.53**) = Profit Attributable to Owners (**£2,724,621.75**) + Profit Attributable to NCI (**£65,032.78**).
4. **Double-Entry Elimination Symmetry:** Verifies $\sum \text{Debit} = \sum \text{Credit}$ for each of `ELIM-01` (£1,013,567.44), `ELIM-02` (£7,867,594.17), `ELIM-03` (£65,341.90), `ELIM-04` (£510,774.14), and `ELIM-05` (£500,782.47).
5. **Pre- vs. Post-Acquisition India P&L Reconciliation:** Verifies that Q1 (`2024-04` to `2024-06`) + H2 (`2024-07` to `2024-12`) in `in_pl_monthly.csv` equals 100% of the 9-month YTD P&L lines in `tb_in.csv` (Revenue ₹642,000,000.00, Profit ₹60,000,000.00), and that Q1 profit equals exactly **₹18,000,000.00** per `acquisition_note.md`.

---

## 2. Independent Recomputation Proofs

### A. Opening Group Equity Proof (`prior_year_group.csv` vs. Entity TBs at `2023-12-31`)
We independently proved that opening group equity (**£14,267,097.93**) reconciles to the parent and UK subsidiary opening balances:
* **US Opening Net Assets (excl. UK Investment of $1,270,000.00):**
  $$\$2,000,000.00 (\text{SC}) + \$14,069,373.43 (\text{RE}) - \$1,270,000.00 (\text{Inv in UK}) = \$14,799,373.43\text{ USD}$$
  Translated at the `2023-12-31` opening rate (`1.2730` USD/GBP) = **£11,625,587.93 GBP**.
* **UK Opening Net Assets:**
  $$£1,000,000.00 (\text{SC, eliminated}) + £1,641,510.00 (\text{P\&L Reserve}) = £2,641,510.00\text{ GBP}$$
* **Total Opening Group Equity:**
  $$£11,625,587.93 + £2,641,510.00 = £14,267,097.93\text{ GBP}$$
  Matches `prior_year_group.csv` (`£1,250,000.00 SC + £12,604,747.93 RE + £412,350.00 TR`) to the exact penny.

### B. Direct Component Proof of `translation_reserve_movement` (£43,786.11)
Rather than treating the Translation Reserve (`3300`) as an unverified Balance Sheet plug, `src/verifier.py` recomputes the movement directly from the six underlying currency exposure components:

| Component Exposure | Local Currency Amount | Rate Transition (`From -> To`) | FX Movement (GBP) |
| :--- | ---: | :--- | ---: |
| **1a. US Remaining Opening Net Assets** | $6,525,000.00 USD | `1.2730` (Open) $\rightarrow$ `1.2530` (Close) | **+£81,814.64** |
| **1b. US Cash Used for India Acquisition** | $8,274,373.43 USD | `1.2730` (Open) $\rightarrow$ `1.2645` (1 Jul Spot) | **+£43,692.49** |
| **2. US FY2024 Post-JE Profit** | $1,856,250.00 USD | `1.2780` (FY Avg) $\rightarrow$ `1.2530` (Close) | **+£28,979.74** |
| **3. India Acquisition Net Assets (80% Group Share)** | ₹542,400,000.00 INR | `105.446655` (Spot) $\rightarrow$ `107.281860` (Close) | **-£87,992.40** |
| **4. India H2 Post-Acq Profit (80% Group Share)** | ₹28,040,000.00 INR | `107.791800` (H2 Avg) $\rightarrow$ `107.281860` (Close) | **+£1,236.47** |
| **5. India Goodwill Retranslation (Policy 4)** | ₹147,600,000.00 INR | `105.446655` (Spot) $\rightarrow$ `107.281860` (Close) | **-£23,944.83** |
| **Direct Component Sum** | | | **£43,786.12** |
| **Balance Sheet Equity Bridge (`close_tr - open_tr`)** | | | **£43,786.11** |
| **Unrounded Difference (Explained by ERP 2-dp Rounding)** | | | **£0.0069** |

*Note on the £0.0069 difference:* In `tb_us.csv:L10`, US recorded the INR 690,000,000 acquisition at `83.39` spot as `$8,274,373.43` (rounding `$8,274,373.4261` up by `$0.0039`, or `£0.0031`), and `prior_year_group.csv` rounded opening retained earnings `£12,604,747.9262` up by `£0.0038` (`0.0031 + 0.0038 = £0.0069`).

---

## 3. Three Things Our AI Tool Got Wrong (and the Commits That Fixed Them)

### AI Mistake 1: Default Integer Coercion Stripped Leading Zeros on UK Accounts `0030` and `0031`
* **What the AI Did Wrong:** In the initial ingestion draft, the AI called `pd.read_csv("tb_uk.csv")` and `pd.read_csv("map_uk.csv")` without enforcing `dtype=str`. Pandas inferred `nominal_code` and `local_code` as integers, converting `"0030"` (*Plant and machinery - cost*, £2,900,000) to `30` and `"0031"` (*Plant and machinery - depreciation*, -£1,060,000) to `31`. When `adjustments.json` entry `JE-008` (£22,000 Q4 depreciation top-up) referenced string account `"0031"`, the lookup failed, misstating UK depreciation and PPE by **£22,000.00**.
* **How We Caught It:** Running our journal account mapping check flagged `"0031"` in `JE-008` as an unmapped UK account even though `0031` was visibly present in `map_uk.csv:L8`.
* **Fixing Commit:** `fix(ingestion): enforce strict string dtypes on all CSV loaders to preserve leading zeros on UK 0030/0031` (`src/ingestion.py`).

### AI Mistake 2: Naive Consolidation of India's 9-Month YTD P&L (`tb_in.csv`) Including Pre-Acquisition Q1
* **What the AI Did Wrong:** The AI initially mapped and translated all P&L rows directly from `tb_in.csv` (`FY25 YTD`, covering 1 April to 31 December 2024), overlooking that Northwind India was acquired on **1 July 2024**. That included Q1 (Apr–Jun 2024) pre-acquisition revenue of **₹205,000,000.00** (**£1,901,814.42**) and pre-acquisition profit of **₹18,000,000.00** (**£166,988.58**) inside Group P&L, and double-counted the ₹18M Q1 profit that was already embedded in the ₹678,000,000.00 acquisition net assets.
* **How We Caught It:** Reconciling `tb_in.csv` Equity (`IN-SC` ₹250M + `IN-RE` ₹410M = ₹660M) against `acquisition_note.md` (Net assets at 1 July 2024 = ₹678M) revealed the exact ₹18M Q1 profit bridge, which matched the sum of `2024-04` to `2024-06` in `in_pl_monthly.csv`.
* **Fixing Commit:** `fix(entity-close): slice India P&L using in_pl_monthly.csv to exclude Q1 pre-acquisition profit from Group P&L` (`src/entity_close.py`).

### AI Mistake 3: Omitting Policy 3 Closing-Rate Retranslation on UK's USD Intercompany Payable (`2150`) and Double-Counting the P&L FX Gain (`7300`)
* **What the AI Did Wrong:** First, the AI resolved the £8,108.54 in-transit invoice (`INV-US-2291`) on UK `2150`, bringing UK `2150` to -£498,816.26, but forgot Policy 3 (*"Monetary items in a currency other than the entity's functional currency are retranslated at the closing rate. Differences go to profit or loss (group account 7300)"*). Because UK `2150` is denominated in USD (`-$629,840.00 USD`), failing to retranslate it at `1.2530` left a **£11,957.88** Balance Sheet elimination gap against US `1250` (£510,774.14). Second, when eliminating intercompany P&L (`4200` £500,782.47 vs. `6300` £498,816.26), an intermediate prototype subtracted `ic_pl_fx_diff` (-£1,966.21) from the entity P&L sum, overlooking that crediting `7300` by £1,966.21 merely offsets the £1,966.21 gap between `4200` and `6300` inside P&L (net impact on Group Profit = £0.00).
* **How We Caught It:** Our independent Translation Reserve proof (`src/verifier.py`) differed from the Balance Sheet equity bridge by exactly £1,966.21 (`ic_pl_fx_diff`), immediately pinpointing the double-counted P&L elimination gain.
* **Fixing Commit:** `fix(consolidator): retranslate UK 2150 USD payable per Policy 3 and balance ELIM-05 P&L elimination in 7300` (`src/entity_close.py`, `src/consolidator.py`).