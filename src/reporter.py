"""Output Reporter: writes all required CSV and JSON deliverables to /output."""
import csv
import json
import os
from typing import Dict, Any, List
import pandas as pd
from .models import AuditIssue, EliminationEntry


def write_outputs(
    output_dir: str,
    group_coa: pd.DataFrame,
    cons_result: Dict[str, Any],
    ic_reconciliation: Dict[str, Any],
    sgd_info: Dict[str, Any],
    journal_summary: Dict[str, Any],
    issues: List[AuditIssue],
    verification_report: Dict[str, Any],
    config: Dict[str, Any],
) -> None:
    os.makedirs(output_dir, exist_ok=True)
    cons_tb = cons_result["cons_tb"]
    m = cons_result["metrics"]
    elims: List[EliminationEntry] = cons_result["eliminations"]

    # 1. Write consolidated_tb.csv
    tb_path = os.path.join(output_dir, "consolidated_tb.csv")
    with open(tb_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "account_code", "account_name", "account_type", "statement",
            "debit_gbp", "credit_gbp", "net_balance_gbp", "source_rows"
        ])
        for _, row in group_coa.iterrows():
            code = str(row["account_code"])
            bal = cons_tb[code].amount_gbp
            dr = round(bal, 2) if bal > 0 else 0.00
            cr = round(-bal, 2) if bal < 0 else 0.00
            net = round(bal, 2)
            if abs(net) == 0.0:
                net = 0.00
            sources_str = "; ".join(cons_tb[code].source_rows)
            writer.writerow([
                code, row["account_name"], row["account_type"], row["statement"],
                f"{dr:.2f}", f"{cr:.2f}", f"{net:.2f}", sources_str
            ])

    # 2. Write eliminations.csv
    elim_path = os.path.join(output_dir, "eliminations.csv")
    with open(elim_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "elimination_id", "category", "group_code", "account_name",
            "debit_gbp", "credit_gbp", "description", "source_rows"
        ])
        for e in elims:
            writer.writerow([
                e.elim_id, e.category, e.group_code, e.account_name,
                f"{round(e.debit_gbp, 2):.2f}", f"{round(e.credit_gbp, 2):.2f}",
                e.description, "; ".join(e.source_rows)
            ])

    # 3. Write balance_sheet.json
    bs_lines = []
    for _, row in group_coa[group_coa["statement"] == "BS"].iterrows():
        code = str(row["account_code"])
        atype = row["account_type"]
        if code == "3200":
            raw_val = -m["close_re"]
            sources = cons_tb[code].source_rows + ["profit_and_loss.json:profit_owners"]
        else:
            raw_val = cons_tb[code].amount_gbp
            sources = cons_tb[code].source_rows

        pres_val = round(raw_val, 2) if atype == "Asset" else round(-raw_val, 2)
        if abs(pres_val) == 0.0:
            pres_val = 0.00
        bs_lines.append({
            "account_code": code,
            "account_name": row["account_name"],
            "account_type": atype,
            "amount_gbp": pres_val,
            "source_rows": sources,
        })

    balance_sheet_payload = {
        "statement": "Consolidated Balance Sheet",
        "as_of": "2024-12-31",
        "currency": "GBP",
        "assets": [l for l in bs_lines if l["account_type"] == "Asset"],
        "liabilities": [l for l in bs_lines if l["account_type"] == "Liability"],
        "equity": [l for l in bs_lines if l["account_type"] == "Equity"],
        "totals": {
            "total_assets": round(m["total_assets"], 2),
            "total_liabilities": round(m["total_liabilities"], 2),
            "net_assets": round(m["total_assets"] - m["total_liabilities"], 2),
            "equity_attributable_to_owners": round(m["close_sc"] + m["close_re"] + m["close_tr"], 2),
            "non_controlling_interest": round(m["nci_closing"], 2),
            "total_equity": round(m["total_equity"], 2),
        },
    }
    with open(os.path.join(output_dir, "balance_sheet.json"), "w", encoding="utf-8") as f:
        json.dump(balance_sheet_payload, f, indent=2)

    # 4. Write profit_and_loss.json
    pl_lines = []
    for _, row in group_coa[group_coa["statement"] == "PL"].iterrows():
        code = str(row["account_code"])
        atype = row["account_type"]
        raw_val = cons_tb[code].amount_gbp
        pres_val = round(-raw_val, 2)
        if abs(pres_val) == 0.0:
            pres_val = 0.00
        pl_lines.append({
            "account_code": code,
            "account_name": row["account_name"],
            "account_type": atype,
            "amount_gbp": pres_val,
            "source_rows": cons_tb[code].source_rows,
        })

    gross_profit = round(-cons_tb["4100"].amount_gbp - cons_tb["4200"].amount_gbp - cons_tb["5100"].amount_gbp, 2)
    operating_profit = round(
        gross_profit - sum(cons_tb[c].amount_gbp for c in ["6100", "6200", "6300", "6400", "6500"]), 2
    )
    pbt = round(operating_profit - cons_tb["7100"].amount_gbp - cons_tb["7300"].amount_gbp, 2)

    pl_payload = {
        "statement": "Consolidated Statement of Profit or Loss",
        "period": "FY2024 (Year ended 31 December 2024)",
        "currency": "GBP",
        "line_items": pl_lines,
        "subtotals": {
            "group_revenue": round(m["group_revenue"], 2),
            "gross_profit": gross_profit,
            "operating_profit": operating_profit,
            "profit_before_tax": pbt,
            "group_profit": round(m["group_profit"], 2),
        },
        "attribution": {
            "profit_attributable_to_owners": round(m["profit_owners"], 2),
            "profit_attributable_to_nci": round(m["profit_nci"], 2),
        },
    }
    with open(os.path.join(output_dir, "profit_and_loss.json"), "w", encoding="utf-8") as f:
        json.dump(pl_payload, f, indent=2)

    # 5. Write changes_in_equity.json
    nci_acq_spot_gbp = (0.20 * 678_000_000.0) / (1.2645 * 83.39)
    nci_fx_mov = round(m["nci_closing"], 2) - round(nci_acq_spot_gbp, 2) - round(m["profit_nci"], 2)
    cie_payload = {
        "statement": "Consolidated Statement of Changes in Equity",
        "period": "FY2024 (Year ended 31 December 2024)",
        "currency": "GBP",
        "opening_balance_2024_01_01": {
            "share_capital": round(m["open_sc"], 2),
            "retained_earnings": round(m["open_re"], 2),
            "translation_reserve": round(m["open_tr"], 2),
            "owners_total": round(m["open_sc"] + m["open_re"] + m["open_tr"], 2),
            "non_controlling_interest": round(m["open_nci"], 2),
            "total_equity": round(m["open_sc"] + m["open_re"] + m["open_tr"] + m["open_nci"], 2),
            "source_rows": ["prior_year_group.csv:L2-L5"],
        },
        "movements": {
            "acquisition_of_subsidiary_india_2024_07_01": {
                "share_capital": 0.00,
                "retained_earnings": 0.00,
                "translation_reserve": 0.00,
                "non_controlling_interest": round(nci_acq_spot_gbp, 2),
                "total_equity": round(nci_acq_spot_gbp, 2),
                "source_rows": ["acquisition_note.md:L3-L14", "fx_rates.csv:L5", "fx_rates.csv:L10"],
            },
            "profit_for_the_year": {
                "share_capital": 0.00,
                "retained_earnings": round(m["profit_owners"], 2),
                "translation_reserve": 0.00,
                "non_controlling_interest": round(m["profit_nci"], 2),
                "total_equity": round(m["group_profit"], 2),
            },
            "other_comprehensive_income_translation_differences": {
                "share_capital": 0.00,
                "retained_earnings": 0.00,
                "translation_reserve": round(m["translation_reserve_movement"], 2),
                "non_controlling_interest": round(nci_fx_mov, 2),
                "total_equity": round(round(m["translation_reserve_movement"], 2) + round(nci_fx_mov, 2), 2),
                "component_breakdown_owners": verification_report["tr_components_gbp"],
            },
        },
        "closing_balance_2024_12_31": {
            "share_capital": round(m["close_sc"], 2),
            "retained_earnings": round(m["close_re"], 2),
            "translation_reserve": round(m["close_tr"], 2),
            "owners_total": round(m["close_sc"] + m["close_re"] + m["close_tr"], 2),
            "non_controlling_interest": round(m["nci_closing"], 2),
            "total_equity": round(m["total_equity"], 2),
        },
    }
    with open(os.path.join(output_dir, "changes_in_equity.json"), "w", encoding="utf-8") as f:
        json.dump(cie_payload, f, indent=2)

    # 6. Write issues.json
    issues_payload = {
        "bundle_id": config.get("bundle_id", "NWG-D0BC"),
        "total_issues_logged": len(issues),
        "issues": [iss.to_dict() for iss in issues],
    }
    with open(os.path.join(output_dir, "issues.json"), "w", encoding="utf-8") as f:
        json.dump(issues_payload, f, indent=2)

    # 7. Write control_figures_<initials>.json (and control_figures.json)
    control_payload = {
        "group_revenue": round(m["group_revenue"], 2),
        "group_profit": round(m["group_profit"], 2),
        "profit_owners": round(m["profit_owners"], 2),
        "profit_nci": round(m["profit_nci"], 2),
        "nci_closing": round(m["nci_closing"], 2),
        "goodwill_closing": round(m["goodwill_closing"], 2),
        "translation_reserve_movement": round(m["translation_reserve_movement"], 2),
        "total_assets": round(m["total_assets"], 2),
        "total_equity": round(m["total_equity"], 2),
        "intercompany_difference": ic_reconciliation,
        "sgd_bank_gbp": {
            "value": sgd_info["value"],
            "reason": sgd_info["reason"],
        },
        "journals": journal_summary,
    }
    initials = config.get("initials", "ls").lower()
    with open(os.path.join(output_dir, f"control_figures_{initials}.json"), "w", encoding="utf-8") as f:
        json.dump(control_payload, f, indent=2)
    with open(os.path.join(output_dir, "control_figures.json"), "w", encoding="utf-8") as f:
        json.dump(control_payload, f, indent=2)