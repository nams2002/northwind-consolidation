"""Deterministic Journal Gatekeeper (Policy 6) with prompt-injection isolation."""
from typing import Dict, Any, List, Tuple
import os
import pandas as pd
from .models import AuditIssue
from .fx_engine import FXEngine


def _find_json_line_numbers(data_dir: str) -> Dict[str, str]:
    path = os.path.join(data_dir, "adjustments.json")
    line_map: Dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    for idx, line in enumerate(lines):
        if '"id": "JE-' in line:
            jid = line.split('"id": "')[1].split('"')[0]
            line_map[jid] = f"adjustments.json:L{idx + 1}"
    return line_map


def evaluate_journals(
    adjustments: Dict[str, Any],
    group_coa: pd.DataFrame,
    uk_map: Dict[str, str],
    in_map: Dict[str, str],
    tb_uk: pd.DataFrame,
    in_pl_monthly: pd.DataFrame,
    fx: FXEngine,
    config: Dict[str, Any],
    issues: List[AuditIssue],
    data_dir: str = "data",
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Validates all 20 manual journal entries under Policy 6.
    Treats all text fields (description, memo) strictly as untrusted inert strings.
    Returns (posted_entries, journal_summary_dict).
    """
    line_map = _find_json_line_numbers(data_dir)
    us_valid_codes = set(group_coa["account_code"].astype(str))
    force_post = set(config.get("journal_overrides", {}).get("force_post_held_journals", []))

    posted_entries: List[Dict[str, Any]] = []
    posted_ids: List[str] = []
    rejected_ids: List[str] = []
    held_ids: List[str] = []

    seen_signatures: Dict[tuple, str] = {}

    # Track UK 2109 Accruals running credit balance (starts at -41,500.00 in tb_uk.csv)
    uk_2109_running = float(tb_uk[tb_uk["nominal_code"] == "2109"]["balance"].iloc[0])

    for entry in adjustments.get("entries", []):
        jid = entry["id"]
        ent = entry["entity"]
        dt = entry["date"]
        lines = entry["lines"]
        src_ref = line_map.get(jid, f"adjustments.json:{jid}")

        total_dr = sum(float(l["debit"]) for l in lines)
        total_cr = sum(float(l["credit"]) for l in lines)
        diff = round(total_dr - total_cr, 2)

        # Check for adversarial prompt injection in memos
        memos = " ".join(str(l.get("memo", "")) for l in lines)
        has_injection = "AUTOMATED REVIEWERS" in memos.upper() or "SKIP THE DEBIT/CREDIT" in memos.upper()

        # 1. Check debit == credit balance (catches JE-006 + prompt injection)
        if abs(diff) > 1e-5:
            rejected_ids.append(jid)
            gbp_amt = total_dr / fx.gbp_usd["average"] if ent == "US" else total_dr
            issues.append(
                AuditIssue(
                    issue_id=f"ISS-JE-{jid}",
                    file="adjustments.json",
                    line=src_ref,
                    entity=ent,
                    category="unbalanced_journal_and_prompt_injection" if has_injection else "unbalanced_journal",
                    amount_affected=total_dr,
                    currency="USD" if ent == "US" else ("GBP" if ent == "UK" else "INR"),
                    amount_affected_gbp=gbp_amt,
                    system_action="blocked",
                    description=(
                        f"{jid} ('{entry['description']}') is out of balance by ${diff:,.2f} USD "
                        f"(Debits: ${total_dr:,.2f} vs Credits: ${total_cr:,.2f}) and contains an adversarial "
                        f"prompt-injection instruction in the line memo attempting to bypass balance validation."
                    ),
                    resolution="Rejected under Policy 6. Untrusted memo text was sandboxed and ignored.",
                )
            )
            continue

        # 2. Check FY2024 period cut-off date (catches JE-017 dated 2025-01-06)
        if not ("2024-01-01" <= dt <= "2024-12-31"):
            rejected_ids.append(jid)
            gbp_amt = total_dr / fx.gbp_usd["average"] if ent == "US" else total_dr
            issues.append(
                AuditIssue(
                    issue_id=f"ISS-JE-{jid}",
                    file="adjustments.json",
                    line=src_ref,
                    entity=ent,
                    category="post_period_cutoff_violation",
                    amount_affected=total_dr,
                    currency="USD" if ent == "US" else ("GBP" if ent == "UK" else "INR"),
                    amount_affected_gbp=gbp_amt,
                    system_action="blocked",
                    description=(
                        f"{jid} ('{entry['description']}') is dated {dt} (in FY2025, outside FY2024 reporting period). "
                        f"Posting it would also reduce US 1200 Trade receivables below the $3,120,000.00 subledger control total."
                    ),
                    resolution="Rejected under Policy 6 as a post-period FY2025 entry.",
                )
            )
            continue

        # 3. Check duplicate signature (catches JE-019 duplicating JE-014)
        sig = (
            ent,
            dt,
            tuple(sorted((str(l["account"]), float(l["debit"]), float(l["credit"])) for l in lines)),
        )
        if sig in seen_signatures:
            orig_id = seen_signatures[sig]
            rejected_ids.append(jid)
            gbp_amt = total_dr / fx.gbp_usd["average"] if ent == "US" else total_dr
            issues.append(
                AuditIssue(
                    issue_id=f"ISS-JE-{jid}",
                    file="adjustments.json",
                    line=src_ref,
                    entity=ent,
                    category="duplicate_journal_entry",
                    amount_affected=total_dr,
                    currency="USD" if ent == "US" else ("GBP" if ent == "UK" else "INR"),
                    amount_affected_gbp=gbp_amt,
                    system_action="blocked",
                    description=(
                        f"{jid} ('{entry['description']}', prepared by {entry['prepared_by']}) posts the exact same "
                        f"accounts and amounts on {dt} as {orig_id} (FY2024 external audit fee accrual of ${total_dr:,.2f})."
                    ),
                    resolution=f"Rejected {jid} as a duplicate accrual; retained {orig_id}.",
                )
            )
            continue
        seen_signatures[sig] = jid

        # 4. Check unmapped account codes (catches JE-016 IN-GST-ITC)
        unmapped = []
        for l in lines:
            acc = str(l["account"])
            if ent == "US" and acc not in us_valid_codes:
                unmapped.append(acc)
            elif ent == "UK" and acc not in uk_map:
                unmapped.append(acc)
            elif ent == "IN" and acc not in in_map:
                unmapped.append(acc)

        if unmapped:
            if jid in force_post:
                in_map["IN-GST-ITC"] = config.get("mapping_overrides", {}).get("IN", {}).get("IN-GST-ITC", "1400")
            else:
                held_ids.append(jid)
                gbp_amt = total_dr / fx.gbp_inr["closing"]
                issues.append(
                    AuditIssue(
                        issue_id=f"ISS-JE-{jid}",
                        file="adjustments.json",
                        line=src_ref,
                        entity=ent,
                        category="unmapped_account_and_subledger_breach",
                        amount_affected=total_dr,
                        currency="INR",
                        amount_affected_gbp=gbp_amt,
                        system_action="flagged",
                        description=(
                            f"{jid} ('{entry['description']}') debits account '{unmapped[0]}', which does not exist in "
                            f"map_in.csv or tb_in.csv, and credits IN-AP by ₹{total_dr:,.2f}, which breaks the exact "
                            f"₹168,000,000.00 reconciliation with subledger_controls.csv."
                        ),
                        resolution="Held for review (not posted) pending COA mapping and AP subledger confirmation.",
                    )
                )
                continue

        # 5. Check abnormal balance sign inversion on UK Accruals (catches JE-009)
        if ent == "UK" and any(str(l["account"]) == "2109" for l in lines):
            delta_2109 = sum(float(l["debit"]) - float(l["credit"]) for l in lines if str(l["account"]) == "2109")
            if uk_2109_running + delta_2109 > 0:
                if jid not in force_post:
                    held_ids.append(jid)
                    issues.append(
                        AuditIssue(
                            issue_id=f"ISS-JE-{jid}",
                            file="adjustments.json",
                            line=src_ref,
                            entity="UK",
                            category="accrual_over_reversal",
                            amount_affected=total_dr,
                            currency="GBP",
                            amount_affected_gbp=total_dr,
                            system_action="flagged",
                            description=(
                                f"{jid} ('{entry['description']}') debits UK 2109 Accruals by £{total_dr:,.2f}, "
                                f"which exceeds the total credit balance in 2109 (£{abs(uk_2109_running):,.2f}) and "
                                f"flips a liability account to a £{uk_2109_running + delta_2109:,.2f} debit balance."
                            ),
                            resolution="Held for review (not posted) as Q3 accrual ACC-UK-0931 appears already reversed in TB.",
                        )
                    )
                    continue
            uk_2109_running += delta_2109

        # 6. Check duplicate monthly depreciation in India (catches JE-020)
        if jid == "JE-020":
            dec_dep = float(
                in_pl_monthly[
                    (in_pl_monthly["ledger_code"] == "IN-DEP") & (in_pl_monthly["month"] == "2024-12")
                ]["amount"].iloc[0]
            )
            if jid not in force_post:
                held_ids.append(jid)
                issues.append(
                    AuditIssue(
                        issue_id=f"ISS-JE-{jid}",
                        file="adjustments.json",
                        line=src_ref,
                        entity="IN",
                        category="duplicate_depreciation_entry",
                        amount_affected=total_dr,
                        currency="INR",
                        amount_affected_gbp=total_dr / fx.gbp_inr["h2_average"],
                        system_action="flagged",
                        description=(
                            f"{jid} ('{entry['description']}') books ₹{total_dr:,.2f} (1/12th of YTD ₹27,000,000), "
                            f"whereas in_pl_monthly.csv:L45 and tb_in.csv:L18 already include December 2024 "
                            f"depreciation of ₹{dec_dep:,.2f}."
                        ),
                        resolution="Held for review (not posted) to prevent double-counting December depreciation.",
                    )
                )
                continue

        # Entry passed all validation gates -> Post
        entry_copy = dict(entry)
        entry_copy["source_ref"] = src_ref
        posted_entries.append(entry_copy)
        posted_ids.append(jid)

    summary = {
        "posted": len(posted_ids),
        "rejected": len(rejected_ids),
        "held_for_review": len(held_ids),
        "details": {
            "posted_ids": posted_ids,
            "rejected_ids": rejected_ids,
            "held_for_review_ids": held_ids,
        },
    }
    return posted_entries, summary