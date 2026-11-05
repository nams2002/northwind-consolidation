"""Group Consolidation Engine: Eliminations, Goodwill, NCI, Equity Bridge, and Consolidated TB."""
from typing import Dict, Any, List
import pandas as pd
from .models import AccountBalance, EliminationEntry
from .fx_engine import FXEngine


def run_group_consolidation(
    us_accts: Dict[str, AccountBalance],
    uk_accts: Dict[str, AccountBalance],
    in_accts: Dict[str, AccountBalance],
    group_coa: pd.DataFrame,
    prior_year_group: pd.DataFrame,
    fx: FXEngine,
) -> Dict[str, Any]:
    """Combines translated entity trial balances, posts eliminations, and computes statements."""
    coa_names = dict(zip(group_coa["account_code"], group_coa["account_name"]))
    eliminations: List[EliminationEntry] = []

    # 1. Aggregate BS (<3000) and P&L (>=4000) across US, UK, IN
    cons_tb: Dict[str, AccountBalance] = {}
    for code in group_coa["account_code"]:
        cons_tb[code] = AccountBalance(code)
        if int(code) < 3000 or int(code) >= 4000:
            for ent_dict in (us_accts, uk_accts, in_accts):
                if code in ent_dict:
                    b = ent_dict[code]
                    cons_tb[code].add(0.0, b.amount_gbp, b.source_rows)

    # 2. ELIM-01: Eliminate Investment in Northwind UK Ltd (US 1600 vs UK 3100 Share Capital)
    us_1600_gbp = us_accts["1600"].amount_gbp  # 1,270,000 / 1.2530 = 1,013,567.438148 GBP
    uk_3000_gbp = abs(uk_accts["3100"].amount_gbp)  # 1,000,000.00 GBP
    elim01_sources = us_accts["1600"].source_rows + uk_accts["3100"].source_rows
    eliminations.extend([
        EliminationEntry(
            "ELIM-01", "uk_investment_elimination", "3100", coa_names["3100"],
            uk_3000_gbp, 0.0, elim01_sources, "Eliminate UK subsidiary share capital"
        ),
        EliminationEntry(
            "ELIM-01", "uk_investment_elimination", "3300", coa_names["3300"],
            us_1600_gbp - uk_3000_gbp, 0.0, elim01_sources,
            "Eliminate FX retranslation on parent USD investment in UK against translation reserve"
        ),
        EliminationEntry(
            "ELIM-01", "uk_investment_elimination", "1600", coa_names["1600"],
            0.0, us_1600_gbp, elim01_sources, "Eliminate parent carrying investment in Northwind UK Ltd"
        ),
    ])
    cons_tb["1600"].add(0.0, -us_1600_gbp, ["eliminations.csv:ELIM-01"])

    # 3. ELIM-02: India Acquisition Elimination, Goodwill (Policy 4), and Acquisition NCI
    goodwill_inr = 690_000_000.0 - (0.80 * 678_000_000.0)  # 147,600,000.0 INR
    goodwill_closing_gbp = goodwill_inr / fx.gbp_inr["closing"]  # 1,375,815.070693 GBP
    us_1610_gbp = us_accts["1610"].amount_gbp  # 8,274,373.43 / 1.2530 = 6,603,649.984038 GBP
    in_sc_close_gbp = 250_000_000.0 / fx.gbp_inr["closing"]
    in_pre_re_close_gbp = 428_000_000.0 / fx.gbp_inr["closing"]
    nci_acq_close_gbp = (0.20 * 678_000_000.0) / fx.gbp_inr["closing"]
    elim02_tr_plug = (us_1610_gbp + nci_acq_close_gbp) - (
        in_sc_close_gbp + in_pre_re_close_gbp + goodwill_closing_gbp
    )
    elim02_sources = (
        us_accts["1610"].source_rows
        + in_accts["3100"].source_rows
        + in_accts["3200"].source_rows
        + ["acquisition_note.md:L3-L14"]
    )
    eliminations.extend([
        EliminationEntry(
            "ELIM-02", "india_acquisition_elimination", "3100", coa_names["3100"],
            in_sc_close_gbp, 0.0, elim02_sources, "Eliminate India pre-acquisition share capital (250M INR)"
        ),
        EliminationEntry(
            "ELIM-02", "india_acquisition_elimination", "3200", coa_names["3200"],
            in_pre_re_close_gbp, 0.0, elim02_sources,
            "Eliminate India pre-acquisition reserves (410M Apr 1 + 18M Q1 profit = 428M INR)"
        ),
        EliminationEntry(
            "ELIM-02", "india_acquisition_elimination", "1700", coa_names["1700"],
            goodwill_closing_gbp, 0.0, elim02_sources,
            "Recognise Goodwill on India acquisition (147.6M INR retranslated at closing rate 107.28186)"
        ),
        EliminationEntry(
            "ELIM-02", "india_acquisition_elimination", "3300", coa_names["3300"],
            elim02_tr_plug, 0.0, elim02_sources,
            "Translation reserve movement on India acquisition net assets, goodwill, and USD investment"
        ),
        EliminationEntry(
            "ELIM-02", "india_acquisition_elimination", "1610", coa_names["1610"],
            0.0, us_1610_gbp, elim02_sources, "Eliminate parent investment in Northwind India Pvt Ltd"
        ),
        EliminationEntry(
            "ELIM-02", "india_acquisition_elimination", "3400", coa_names["3400"],
            0.0, nci_acq_close_gbp, elim02_sources,
            "Recognise 20% Non-Controlling Interest share of India acquisition net assets at closing rate"
        ),
    ])
    cons_tb["1610"].add(0.0, -us_1610_gbp, ["eliminations.csv:ELIM-02"])
    cons_tb["1700"].add(0.0, goodwill_closing_gbp, elim02_sources + ["eliminations.csv:ELIM-02"])

    # 4. ELIM-03: NCI 20% Share of India H2 Post-Acquisition Profit
    in_h2_profit_inr = -sum(b.amount_local for k, b in in_accts.items() if int(k) >= 4000)
    in_h2_profit_gbp = -sum(b.amount_gbp for k, b in in_accts.items() if int(k) >= 4000)
    profit_nci_gbp = 0.20 * in_h2_profit_gbp
    nci_h2_close_gbp = (0.20 * in_h2_profit_inr) / fx.gbp_inr["closing"]
    elim03_sources = ["in_pl_monthly.csv:L4..L73", "acquisition_note.md:L4"]
    eliminations.extend([
        EliminationEntry(
            "ELIM-03", "nci_post_acq_profit_allocation", "3200", coa_names["3200"],
            profit_nci_gbp, 0.0, elim03_sources, "Allocate 20% of India H2 profit to Non-Controlling Interest"
        ),
        EliminationEntry(
            "ELIM-03", "nci_post_acq_profit_allocation", "3300", coa_names["3300"],
            nci_h2_close_gbp - profit_nci_gbp, 0.0, elim03_sources,
            "FX translation adjustment on NCI share of H2 profit (H2 average vs closing rate)"
        ),
        EliminationEntry(
            "ELIM-03", "nci_post_acq_profit_allocation", "3400", coa_names["3400"],
            0.0, nci_h2_close_gbp, elim03_sources, "Credit 20% of India H2 post-acquisition net asset increase to NCI"
        ),
    ])

    # 5. ELIM-04: Intercompany Balance Sheet Elimination (US 1250 vs UK 2150)
    ic_bs_gbp = us_accts["1250"].amount_gbp  # 510,774.142059 GBP
    elim04_sources = us_accts["1250"].source_rows + uk_accts["2150"].source_rows
    eliminations.extend([
        EliminationEntry(
            "ELIM-04", "intercompany_bs_elimination", "2150", coa_names["2150"],
            ic_bs_gbp, 0.0, elim04_sources, "Eliminate UK intercompany payable (after in-transit & Policy 3 FX)"
        ),
        EliminationEntry(
            "ELIM-04", "intercompany_bs_elimination", "1250", coa_names["1250"],
            0.0, ic_bs_gbp, elim04_sources, "Eliminate US intercompany receivable"
        ),
    ])
    cons_tb["1250"].add(0.0, -ic_bs_gbp, ["eliminations.csv:ELIM-04"])
    cons_tb["2150"].add(0.0, ic_bs_gbp, ["eliminations.csv:ELIM-04"])

    # 6. ELIM-05: Intercompany P&L Management Fee Elimination (US 4200 vs UK 6300 -> diff to 7300 per Policy 5)
    us_4200_gbp = abs(us_accts["4200"].amount_gbp)  # 500,782.472613 GBP
    uk_6300_gbp = uk_accts["6300"].amount_gbp       # 498,816.259505 GBP
    ic_pl_fx_gain = us_4200_gbp - uk_6300_gbp       # 1,966.213108 GBP (Cr to 7300)
    elim05_sources = us_accts["4200"].source_rows + uk_accts["6300"].source_rows
    eliminations.extend([
        EliminationEntry(
            "ELIM-05", "intercompany_pl_elimination", "4200", coa_names["4200"],
            us_4200_gbp, 0.0, elim05_sources, "Eliminate US intercompany management fee income"
        ),
        EliminationEntry(
            "ELIM-05", "intercompany_pl_elimination", "6300", coa_names["6300"],
            0.0, uk_6300_gbp, elim05_sources, "Eliminate UK intercompany management fee expense"
        ),
        EliminationEntry(
            "ELIM-05", "intercompany_pl_elimination", "7300", coa_names["7300"],
            0.0, ic_pl_fx_gain, elim05_sources,
            "Record remaining exchange difference on eliminating IC income and expense in 7300 (Policy 5)"
        ),
    ])
    cons_tb["4200"].add(0.0, us_4200_gbp, ["eliminations.csv:ELIM-05"])
    cons_tb["6300"].add(0.0, -uk_6300_gbp, ["eliminations.csv:ELIM-05"])
    cons_tb["7300"].add(0.0, -ic_pl_fx_gain, ["eliminations.csv:ELIM-05"])

    # 7. Compute Consolidated P&L, Balance Sheet, and Closing Equity (3100, 3200, 3300, 3400)
    group_revenue = -cons_tb["4100"].amount_gbp
    group_profit = -sum(cons_tb[c].amount_gbp for c in group_coa["account_code"] if int(c) >= 4000)
    profit_owners = group_profit - profit_nci_gbp

    total_assets = sum(cons_tb[c].amount_gbp for c in group_coa["account_code"] if int(c) < 2000)
    total_liabilities = -sum(cons_tb[c].amount_gbp for c in group_coa["account_code"] if 2000 <= int(c) < 3000)
    total_equity = total_assets - total_liabilities

    prior_map = dict(zip(prior_year_group["group_account"], prior_year_group["amount_gbp"].astype(float)))
    prior_refs = dict(zip(prior_year_group["group_account"], prior_year_group["source_ref"]))

    open_sc = prior_map["3100"]  # 1,250,000.00
    open_re = prior_map["3200"]  # 12,604,747.93
    open_tr = prior_map["3300"]  # 412,350.00
    open_nci = prior_map["3400"] # 0.00

    close_sc = open_sc
    close_re = open_re + profit_owners
    in_closing_na_inr = 678_000_000.0 + in_h2_profit_inr
    nci_closing = 0.20 * (in_closing_na_inr / fx.gbp_inr["closing"])
    close_tr = total_equity - (close_sc + close_re + nci_closing)
    tr_movement = close_tr - open_tr

    # Set Equity lines in Consolidated TB
    cons_tb["3100"].add(0.0, -close_sc, [prior_refs["3100"], "eliminations.csv:ELIM-01", "eliminations.csv:ELIM-02"])
    cons_tb["3200"].add(
        0.0,
        -(open_re - profit_nci_gbp),
        [prior_refs["3200"], "eliminations.csv:ELIM-02", "eliminations.csv:ELIM-03"],
    )
    cons_tb["3300"].add(
        0.0,
        -close_tr,
        [prior_refs["3300"], "eliminations.csv:ELIM-01", "eliminations.csv:ELIM-02", "eliminations.csv:ELIM-03"],
    )
    cons_tb["3400"].add(
        0.0,
        -nci_closing,
        [prior_refs["3400"], "eliminations.csv:ELIM-02", "eliminations.csv:ELIM-03"],
    )

    return {
        "cons_tb": cons_tb,
        "eliminations": eliminations,
        "metrics": {
            "group_revenue": group_revenue,
            "group_profit": group_profit,
            "profit_owners": profit_owners,
            "profit_nci": profit_nci_gbp,
            "nci_closing": nci_closing,
            "goodwill_closing": goodwill_closing_gbp,
            "translation_reserve_movement": tr_movement,
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "total_equity": total_equity,
            "open_sc": open_sc,
            "open_re": open_re,
            "open_tr": open_tr,
            "open_nci": open_nci,
            "close_sc": close_sc,
            "close_re": close_re,
            "close_tr": close_tr,
            "in_h2_profit_inr": in_h2_profit_inr,
            "us_profit_usd": -sum(b.amount_local for k, b in us_accts.items() if int(k) >= 4000),
        },
    }