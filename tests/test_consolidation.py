"""Independent recomputation of key control figures straight from the raw input files.

Nothing here imports from src/. It re-derives each figure with plain csv/json code and
compares it with what the pipeline wrote, so a bug in the pipeline cannot also be in the check.
Journal decisions (which entries are valid) are stated explicitly below, see DECISIONS.md.
"""
import csv
import json
import os
import subprocess
import sys

import pytest

DATA = "data"
REJECTED = {"JE-006", "JE-017", "JE-019"}   # unbalanced+injection, post-period, duplicate
HELD = {"JE-009", "JE-016", "JE-020"}       # held for review, not posted
TOL = 0.006                                  # figures are rounded to 2dp


def _rows(name):
    with open(os.path.join(DATA, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def cf(tmp_path_factory):
    out = tmp_path_factory.mktemp("indep_output")
    res = subprocess.run(
        [sys.executable, "-m", "src.main", "--data-dir", DATA, "--output-dir", str(out),
         "--config", "policy_config.json"],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    with open("policy_config.json", encoding="utf-8") as f:
        initials = json.load(f)["initials"].lower()
    with open(out / f"control_figures_{initials}.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def inputs():
    fx = {(r["base_currency"], r["quote_currency"], r["rate_type"]): float(r["rate"]) for r in _rows("fx_rates.csv")}
    gbp_usd = {t: fx[("GBP", "USD", t)] for t in ("opening", "average", "h2_average", "spot", "closing")}
    gbp_inr = {t: gbp_usd[t] * fx[("USD", "INR", t)] for t in gbp_usd}  # Policy 2 cross rate
    with open(os.path.join(DATA, "adjustments.json"), encoding="utf-8") as f:
        entries = json.load(f)["entries"]
    posted = [e for e in entries if e["id"] not in REJECTED | HELD]
    return gbp_usd, gbp_inr, posted


IN_PL = {"IN-REV", "IN-COGS", "IN-EMP", "IN-RENT", "IN-DEP", "IN-OTH", "IN-FIN", "IN-TXE"}


def _us_pl_usd(posted):
    tot = 0.0
    for r in _rows("tb_us.csv"):
        if int(r["account_code"]) >= 4000:
            tot += float(r["debit"]) - float(r["credit"])
    for e in posted:
        if e["entity"] == "US":
            for l in e["lines"]:
                if int(l["account"]) >= 4000:
                    tot += float(l["debit"]) - float(l["credit"])
    return -tot  # profit, credit positive


def _in_h2_inr(posted):
    """India profit and revenue for Jul-Dec 2024 only, from the monthly file plus posted journals."""
    profit = rev = 0.0
    for r in _rows("in_pl_monthly.csv"):
        if r["month"] >= "2024-07":
            amt = float(r["amount"]) * (1 if r["dr_cr"] == "Cr" else -1)
            profit += amt
            if r["ledger_code"] == "IN-REV":
                rev += amt
    for e in posted:
        if e["entity"] == "IN":
            for l in e["lines"]:
                if l["account"] in IN_PL:
                    amt = float(l["credit"]) - float(l["debit"])
                    profit += amt
                    if l["account"] == "IN-REV":
                        rev += amt
    return profit, rev


def test_india_q1_plus_h2_equals_ytd_and_acquisition_net_assets():
    monthly = {}
    for r in _rows("in_pl_monthly.csv"):
        monthly[r["ledger_code"]] = monthly.get(r["ledger_code"], 0.0) + float(r["amount"]) * (1 if r["dr_cr"] == "Dr" else -1)
    for r in _rows("tb_in.csv"):
        if r["ledger_code"] in IN_PL:
            tb = float(r["amount"]) * (1 if r["dr_cr"] == "Dr" else -1)
            assert abs(tb - monthly[r["ledger_code"]]) < 0.005, r["ledger_code"]
    q1_profit = sum(float(r["amount"]) * (1 if r["dr_cr"] == "Cr" else -1)
                    for r in _rows("in_pl_monthly.csv") if r["month"] <= "2024-06")
    assert q1_profit == 18_000_000.0
    assert 250_000_000 + 410_000_000 + q1_profit == 678_000_000  # acquisition_note.md


def test_goodwill_and_nci(cf, inputs):
    _, gbp_inr, posted = inputs
    goodwill_inr = 690_000_000 - 0.80 * 678_000_000
    assert cf["goodwill_closing"] == pytest.approx(goodwill_inr / gbp_inr["closing"], abs=TOL)
    h2_profit, _ = _in_h2_inr(posted)
    assert cf["profit_nci"] == pytest.approx(0.20 * h2_profit / gbp_inr["h2_average"], abs=TOL)
    assert cf["nci_closing"] == pytest.approx(0.20 * (678_000_000 + h2_profit) / gbp_inr["closing"], abs=TOL)


def test_group_revenue(cf, inputs):
    gbp_usd, gbp_inr, posted = inputs
    us_rev = -sum(float(r["debit"]) - float(r["credit"]) for r in _rows("tb_us.csv") if r["account_code"] == "4100")
    for e in posted:
        if e["entity"] == "US":
            us_rev -= sum(float(l["debit"]) - float(l["credit"]) for l in e["lines"] if l["account"] == "4100")
    uk_rev = -sum(float(r["balance"]) for r in _rows("tb_uk.csv") if r["nominal_code"] == "4000")  # 2310 is NOT revenue
    _, in_rev = _in_h2_inr(posted)
    expected = us_rev / gbp_usd["average"] + uk_rev + in_rev / gbp_inr["h2_average"]
    assert cf["group_revenue"] == pytest.approx(expected, abs=TOL)


def test_group_profit_and_attribution(cf, inputs):
    gbp_usd, gbp_inr, posted = inputs
    us_gbp = _us_pl_usd(posted) / gbp_usd["average"]

    uk = -sum(float(r["balance"]) for r in _rows("tb_uk.csv") if int(r["nominal_code"]) >= 4000)
    for e in posted:
        if e["entity"] == "UK":
            for l in e["lines"]:
                if int(l["account"]) >= 4000:
                    uk -= float(l["debit"]) - float(l["credit"])
    ic = _rows("intercompany.csv")
    us_docs = {r["doc_ref"]: float(r["doc_amount"]) for r in ic if r["reporting_entity"] == "US"}
    uk_docs = {r["doc_ref"] for r in ic if r["reporting_entity"] == "UK"}
    in_transit = sum(a for d, a in us_docs.items() if d not in uk_docs) / gbp_usd["closing"]   # Policy 5
    uk_2150 = next(r for r in _rows("tb_uk.csv") if r["nominal_code"] == "2150")
    fx_loss = abs(float(uk_2150["txn_amount"])) / gbp_usd["closing"] - abs(float(uk_2150["balance"]))  # Policy 3
    uk_gbp = uk - in_transit - fx_loss  # IC fee elimination nets to nil in profit (FX gain stays in 7300)

    in_gbp = _in_h2_inr(posted)[0] / gbp_inr["h2_average"]
    expected = us_gbp + uk_gbp + in_gbp
    assert cf["group_profit"] == pytest.approx(expected, abs=TOL)
    assert cf["profit_nci"] + cf["profit_owners"] == pytest.approx(cf["group_profit"], abs=TOL)


def test_journal_counts_match_stated_decisions(cf):
    j = cf["journals"]
    assert (j["posted"], j["rejected"], j["held_for_review"]) == (14, 3, 3)
    assert set(j["details"]["rejected_ids"]) == REJECTED
    assert set(j["details"]["held_for_review_ids"]) == HELD