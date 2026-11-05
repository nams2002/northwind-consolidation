"""Self-Correction & Verification Loop: asserts mathematical and accounting invariants before output."""
from typing import Dict, Any
from .fx_engine import FXEngine


def verify_consolidation(cons_result: Dict[str, Any], fx: FXEngine) -> Dict[str, Any]:
    """
    Runs 5 independent mathematical assertions on the consolidated output:
    1. Consolidated Trial Balance sum(Debits - Credits) == 0.00
    2. Balance Sheet equation: Total Assets - Total Liabilities - Total Equity == 0.00
    3. Profit split: Group Profit == Profit (Owners) + Profit (NCI)
    4. Elimination entries balance: sum(Debit) == sum(Credit) for every Elimination ID
    5. Independent Direct Proof of Translation Reserve Movement (reconciles within £0.01 ERP rounding)
    """
    cons_tb = cons_result["cons_tb"]
    m = cons_result["metrics"]
    elims = cons_result["eliminations"]

    # Check 1: Trial Balance zero-sum check
    tb_net = sum(b.amount_gbp for b in cons_tb.values())
    assert abs(tb_net) < 1e-6, f"Consolidated TB out of balance by £{tb_net:.6f}"

    # Check 2: Balance Sheet accounting identity (A = L + E)
    bs_diff = m["total_assets"] - (m["total_liabilities"] + m["total_equity"])
    assert abs(bs_diff) < 1e-6, f"Balance Sheet out of balance by £{bs_diff:.6f}"

    # Check 3: Profit attribution check
    pl_split_diff = m["group_profit"] - (m["profit_owners"] + m["profit_nci"])
    assert abs(pl_split_diff) < 1e-6, f"Profit split mismatch: £{pl_split_diff:.6f}"

    # Check 4: Every elimination entry balances
    by_id: Dict[str, float] = {}
    for e in elims:
        by_id[e.elim_id] = by_id.get(e.elim_id, 0.0) + (e.debit_gbp - e.credit_gbp)
    for eid, net in by_id.items():
        assert abs(net) < 1e-6, f"Elimination {eid} out of balance by £{net:.6f}"

    # Check 5: Independent Direct Recomputation of Translation Reserve Movement
    fx_us_rem_open = 6_525_000.0 * (1.0 / fx.gbp_usd["closing"] - 1.0 / fx.gbp_usd["opening"])
    fx_us_acq_cash = 8_274_373.43 * (1.0 / fx.gbp_usd["spot"] - 1.0 / fx.gbp_usd["opening"])
    fx_us_profit = m["us_profit_usd"] * (1.0 / fx.gbp_usd["closing"] - 1.0 / fx.gbp_usd["average"])
    fx_in_acq_na = (0.80 * 678_000_000.0) * (1.0 / fx.gbp_inr["closing"] - 1.0 / fx.gbp_inr["spot"])
    fx_in_h2_profit = (0.80 * m["in_h2_profit_inr"]) * (
        1.0 / fx.gbp_inr["closing"] - 1.0 / fx.gbp_inr["h2_average"]
    )
    fx_goodwill = 147_600_000.0 * (1.0 / fx.gbp_inr["closing"] - 1.0 / fx.gbp_inr["spot"])

    direct_tr_movement = (
        fx_us_rem_open + fx_us_acq_cash + fx_us_profit + fx_in_acq_na + fx_in_h2_profit + fx_goodwill
    )
    tr_reconcile_diff = abs(direct_tr_movement - m["translation_reserve_movement"])
    assert tr_reconcile_diff < 0.01, (
        f"Translation Reserve direct proof (£{direct_tr_movement:.4f}) diverged from BS bridge "
        f"(£{m['translation_reserve_movement']:.4f}) by £{tr_reconcile_diff:.4f}"
    )

    return {
        "tb_net_diff_gbp": round(tb_net, 8),
        "bs_identity_diff_gbp": round(bs_diff, 8),
        "direct_tr_movement_gbp": round(direct_tr_movement, 2),
        "bridge_tr_movement_gbp": round(m["translation_reserve_movement"], 2),
        "tr_components_gbp": {
            "us_remaining_opening_net_assets": round(fx_us_rem_open, 2),
            "us_acquisition_cash_to_1_jul": round(fx_us_acq_cash, 2),
            "us_fy24_profit_avg_to_close": round(fx_us_profit, 2),
            "in_80pct_acq_net_assets_spot_to_close": round(fx_in_acq_na, 2),
            "in_80pct_h2_profit_avg_to_close": round(fx_in_h2_profit, 2),
            "in_goodwill_spot_to_close": round(fx_goodwill, 2),
        },
    }