# Key Architectural & Accounting Design Decisions

**Bundle ID:** `NWG-D0BC`

---

## Decision 1: Three-Tier Journal Classification (`Posted` vs. `Rejected` vs. `Held for Review`)

* **Context:** `adjustments.json` contains 20 manual journal entries, and the `journals` control figure requires counts of entries **posted**, **rejected**, and **held for review**.
* **Options Considered:**
  1. *Binary Validation (17 Posted, 3 Rejected):* Only reject entries that fail basic syntax/balance/date checks (`JE-006`, `JE-017`, `JE-019`) and auto-post `JE-009`, `JE-016`, and `JE-020`.
  2. *Three-Tier Substantive Gatekeeping (14 Posted, 3 Rejected, 3 Held for Review):* Reject clear policy/duplicate/balance violations (`JE-006`, `JE-017`, `JE-019`), and place entries with substantive accounting defects (`JE-009`, `JE-016`, `JE-020`) into `held_for_review` (unposted pending controller sign-off, with config toggles in `policy_config.json`).
* **Choice:** Option 2 (14 Posted, 3 Rejected, 3 Held for Review).
* **Trade-Off:** Requires deeper cross-file validation logic (checking running account balances, subledger control totals, and monthly P&L trends), but prevents corrupting the financial statements with an unmapped account (`IN-GST-ITC` in `JE-016` that also breaks the ₹168M AP subledger match), a liability sign-flip (`JE-009` flipping UK `2109` Accruals to a £15,700 debit balance), and double-counted December depreciation (`JE-020` booking ₹2.25M on top of ₹3.24M already in `in_pl_monthly.csv`).
* **AI Tool Suggestion & Our Action:** The AI initially suggested mapping `IN-GST-ITC` to `1400 Prepayments` and posting `JE-009`, `JE-016`, and `JE-020` automatically. We **rejected** automatic posting and instead engineered `journal_gatekeeper.py` to hold all three for review while exposing `force_post_held_journals` in `policy_config.json`.

---

## Decision 2: Handling Missing `GBP/SGD` Closing Rate on UK Account `1210` (`£23,010.00`)

* **Context:** UK nominal account `1210` (*Bank - DBS SGD*) holds `SGD 40,000.00` with a book balance of £23,010.00 GBP (`tb_uk.csv:L3`). Policy 3 requires retranslating foreign currency monetary items at the closing rate, which is omitted from `fx_rates.csv`.
* **Options Considered:**
  1. *Extrapolate/Estimate Rate:* Use the FY2024 average rate (`1.7120`, giving £23,364.49) or look up the historical 31 Dec 2024 market rate externally.
  2. *Null Control Figure + Retain Carrying Book Value in Cash (`1100`):* Report `"value": null` for `sgd_bank_gbp` in `control_figures_ls.json`, retain the £23,010.00 carrying book value in Group Cash (`1100`), and log the assumption in `issues.json`.
  3. *Null Control Figure + Zero Out Account `1210`:* Exclude £23,010.00 from `total_assets`, causing the UK Trial Balance to go out of balance by £23,010.00.
* **Choice:** Option 2.
* **Trade-Off:** Group Cash (`1100`, £7,810,225.90) includes £23,010.00 at its historical carrying rate rather than closing rate, which is explicitly disclosed in `issues.json` (`ISS-FX-001`), while preserving double-entry balance and strictly obeying the Appendix rule: *"Never estimate or fill in a value from outside the inputs. An honest null scores better than a confident guess."*
* **AI Tool Suggestion & Our Action:** The AI suggested using the average rate `1.7120` as a proxy if a float was required, or returning `null` for `sgd_bank_gbp` while keeping £23,010.00 in `1100`. We **accepted** the `null` control figure + £23,010.00 carrying value retention.

---

## Decision 3: Slicing India's 9-Month YTD Trial Balance (`tb_in.csv`) Using `in_pl_monthly.csv`

* **Context:** Northwind India Pvt Ltd has a 1 April–31 March fiscal year (`entities.csv:L4`) and was acquired on 1 July 2024 (`acquisition_note.md`). `tb_in.csv` exports 9-month YTD P&L (`FY25 YTD`, Apr–Dec 2024, ₹642M revenue, ₹60M profit).
* **Options Considered:**
  1. *Time-Apportion `tb_in.csv` by 6/9ths:* Multiply YTD P&L lines by `6/9`.
  2. *Exact Monthly Cut-Off via `in_pl_monthly.csv`:* Transfer Q1 (Apr–Jun 2024) P&L (Revenue ₹205M, Profit ₹18M) to pre-acquisition retained earnings (`3200`) as of 1 July 2024, and consolidate only H2 (Jul–Dec 2024, Revenue ₹437M, unadjusted profit ₹42M) into Group P&L at the H2 average rate (`107.791800`).
* **Choice:** Option 2.
* **Trade-Off:** Requires joining `tb_in.csv` BS lines with `in_pl_monthly.csv` H2 P&L lines and verifying that Q1 + H2 equals `tb_in.csv` YTD to the rupee, but achieves 100% precision and reconciles India's 1 July 2024 net assets (`₹250M SC + ₹410M Apr 1 RE + ₹18M Q1 profit = ₹678M`) to `acquisition_note.md`.
* **AI Tool Suggestion & Our Action:** In early exploration, a naive TB ingestion script used `tb_in.csv` P&L lines directly. We caught this via the `acquisition_note.md` ₹18M Q1 profit check and **replaced** it with the exact monthly cut-off in `src/entity_close.py`.

---

## Decision 4: Two-Step Resolution of UK Intercompany Payable (`2150`) Under Policies 3 and 5

* **Context:** US `1250` Intercompany Receivable is $640,000.00 (£510,774.14 at closing rate `1.2530`), while UK `2150` Due to Northwind Inc is booked at -£490,707.72 (`txn_amount: -629840.00 USD`).
* **Options Considered:**
  1. *Plug Elimination Difference Directly to `7300` on Consolidation:* Eliminate £510,774.14 against £490,707.72 and dump the entire £20,066.42 BS difference and £10,074.75 P&L difference into `7300`.
  2. *Apply Policy 5 (In-Transit) + Policy 3 (Entity-Level Monetary Retranslation) Before Elimination:* First record `INV-US-2291` ($10,160.00 = £8,108.54 at `1.2530`) in UK (`Dr 6300 / Cr 2150`). Second, retranslate UK's existing `-$629,840.00 USD` monetary liability at `1.2530` (-£502,665.60 vs. -£490,707.72 booked), recording £11,957.88 FX loss in UK (`Dr 7300 / Cr 2150`). Third, eliminate P&L `4200` (£500,782.47) against UK `6300` (£498,816.26), crediting the £1,966.21 FX gain to `7300` per Policy 5.
* **Choice:** Option 2.
* **Trade-Off:** Separates entity-level foreign-currency retranslation (Policy 3: £11,957.88 loss) from consolidation-level intercompany P&L elimination (Policy 5: £1,966.21 gain), yielding a net `7300` expense of £9,991.67 and explaining both the BS (£20,066.42) and P&L (£10,074.75) intercompany differences cleanly.
* **AI Tool Suggestion & Our Action:** The AI initially resolved only the P&L side (£8,108.54 in-transit + £1,966.21 FX diff) and missed retranslating UK's `-$629,840.00 USD` payable on the Balance Sheet. We **corrected** this in `src/entity_close.py`.

---

## Decision 5: Remapping UK `2310 Deferred Income` (£180,000.00) from `4100` to `2300`

* **Context:** `map_uk.csv:L12` maps UK local code `2310` (*Deferred income*) to Group code `4100` (*Revenue*).
* **Options Considered:**
  1. *Follow `map_uk.csv` Literally:* Leave £180,000.00 in Group Revenue (`4100`).
  2. *Block Wrong Mapping & Remap to `2300` (*Deferred income*):* Override `2310 -> 2300` and log in `issues.json`.
* **Choice:** Option 2.
* **Trade-Off:** Changes UK Revenue from £10,030,000.00 to £9,850,000.00, preventing a material £180,000.00 overstatement of Group Revenue and Profit.
* **AI Tool Suggestion & Our Action:** The AI spotted the name/type mismatch between `2310 Deferred income` and `2300 Deferred income` immediately during mapping inspection; we **accepted** the override and built `src/mapping_guard.py`.

---

## Decision 6: Treatment of UK £45,000.00 Subledger Variance (`1100` AR and `2100` AP)

* **Context:** `tb_uk.csv` reports raw `1100 Debtors control` of £1,985,000.00 and `2100 Creditors control` of £1,210,000.00, whereas `subledger_controls.csv` reports £1,940,000.00 and £1,165,000.00 (both £45,000.00 lower).
* **Options Considered:**
  1. *Post an Unrequested £45,000.00 Contra Journal (`Dr 2100 / Cr 1100`):* Force GL to match the subledgers.
  2. *Retain Audited TB Balances & Flag in `issues.json` (`ISS-SUB-001`):* Keep the TB balances (adjusted only for valid journal `JE-011`) and flag the £45,000.00 variance for investigation.
* **Choice:** Option 2.
* **Trade-Off:** Because neither the subledger nor the GL indicates whether the £45,000.00 difference is an unposted contra-settlement or a subledger export cut-off issue, inventing an adjustment violates the rule against fabricating entries. Flagging preserves TB traceability and has £0.00 impact on Net Assets.
* **AI Tool Suggestion & Our Action:** We **accepted** the recommendation to flag rather than fabricate an adjustment, and added a `subledger_policy` flag in `policy_config.json`.