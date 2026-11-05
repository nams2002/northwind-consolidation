"""Executable pytest suite verifying Northwind Group consolidation invariants and trap handling."""
import json
import os
import subprocess
import pandas as pd
import pytest


@pytest.fixture(scope="module")
def consolidated_output(tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("output")
    cmd = ["python", "-m", "src.main", "--data-dir", "data", "--output-dir", str(out_dir), "--config", "policy_config.json"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert res.returncode == 0, f"Pipeline failed:\n{res.stderr}"
    return out_dir


def test_required_files_exist(consolidated_output):
    expected = [
        "consolidated_tb.csv",
        "balance_sheet.json",
        "profit_and_loss.json",
        "changes_in_equity.json",
        "eliminations.csv",
        "issues.json",
        "control_figures_ls.json",
    ]
    for fname in expected:
        assert os.path.exists(os.path.join(consolidated_output, fname)), f"Missing {fname}"


def test_control_figures_exact_values(consolidated_output):
    with open(os.path.join(consolidated_output, "control_figures_ls.json"), encoding="utf-8") as f:
        cf = json.load(f)

    assert cf["group_revenue"] == 28301607.81
    assert cf["group_profit"] == 2789654.53
    assert cf["profit_owners"] == 2724621.75
    assert cf["profit_nci"] == 65032.78
    assert cf["nci_closing"] == 1329302.08
    assert cf["goodwill_closing"] == 1375815.07
    assert cf["translation_reserve_movement"] == 43786.11
    assert cf["total_assets"] == 28596245.74
    assert cf["total_equity"] == 18364807.88

    # Honest null on missing GBP/SGD closing rate
    assert cf["sgd_bank_gbp"]["value"] is None
    assert "missing from fx_rates.csv" in cf["sgd_bank_gbp"]["reason"]

    # Journal counts: 14 posted, 3 rejected, 3 held for review
    assert cf["journals"]["posted"] == 14
    assert cf["journals"]["rejected"] == 3
    assert cf["journals"]["held_for_review"] == 3
    assert set(cf["journals"]["details"]["rejected_ids"]) == {"JE-006", "JE-017", "JE-019"}
    assert set(cf["journals"]["details"]["held_for_review_ids"]) == {"JE-009", "JE-016", "JE-020"}


def test_trial_balance_and_eliminations_balance(consolidated_output):
    tb = pd.read_csv(os.path.join(consolidated_output, "consolidated_tb.csv"))
    assert abs(tb["debit_gbp"].sum() - tb["credit_gbp"].sum()) < 0.05
    assert (tb["source_rows"].str.len() > 0).all()

    elims = pd.read_csv(os.path.join(consolidated_output, "eliminations.csv"))
    for eid, grp in elims.groupby("elimination_id"):
        assert abs(grp["debit_gbp"].sum() - grp["credit_gbp"].sum()) < 0.02, f"{eid} unbalanced"


def test_traps_logged_in_issues_json(consolidated_output):
    with open(os.path.join(consolidated_output, "issues.json"), encoding="utf-8") as f:
        issues_data = json.load(f)

    issue_ids = {i["issue_id"] for i in issues_data["issues"]}
    # Verify all major traps were caught and logged
    assert "ISS-FX-001" in issue_ids       # Missing GBP/SGD closing rate
    assert "ISS-MAP-001" in issue_ids      # UK 2310 Deferred income mapped to 4100 Revenue
    assert "ISS-JE-JE-006" in issue_ids    # Unbalanced + Prompt injection memo
    assert "ISS-JE-JE-017" in issue_ids    # Post-period 2025-01-06 cut-off error
    assert "ISS-JE-JE-019" in issue_ids    # Duplicate external audit fee accrual
    assert "ISS-JE-JE-009" in issue_ids    # UK 2109 Accruals over-reversal
    assert "ISS-JE-JE-016" in issue_ids    # Unmapped IN-GST-ITC + AP subledger breach
    assert "ISS-JE-JE-020" in issue_ids    # Duplicate India Dec depreciation
    assert "ISS-SUB-001" in issue_ids      # UK £45,000 AR/AP subledger variance
    assert "ISS-IC-001" in issue_ids       # Intercompany in-transit & Policy 3 FX
    assert "ISS-ACQ-001" in issue_ids      # India Q1 Apr-Jun pre-acquisition P&L cut-off