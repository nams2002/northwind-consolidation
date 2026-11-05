"""CLI Entry Point: Runs the Northwind Group FY2024 consolidation end to end."""
import argparse
import sys
from typing import List
from .models import AuditIssue
from .ingestion import load_bundle
from .fx_engine import FXEngine
from .mapping_guard import build_validated_mappings
from .journal_gatekeeper import evaluate_journals
from .entity_close import close_entity_books
from .consolidator import run_group_consolidation
from .verifier import verify_consolidation
from .reporter import write_outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="Northwind Group FY2024 Consolidation Engine")
    parser.add_argument("--data-dir", default="data", help="Directory containing raw input files")
    parser.add_argument("--output-dir", default="output", help="Directory to write consolidated outputs")
    parser.add_argument("--config", default="policy_config.json", help="Path to policy_config.json")
    args = parser.parse_args()

    issues: List[AuditIssue] = []

    # 1. Load bundle with strict string schemas & source line numbers
    bundle = load_bundle(data_dir=args.data_dir, config_path=args.config)
    config = bundle["config"]

    # 2. Initialize FX Engine & check missing closing rates (UK 1210 SGD bank account)
    fx = FXEngine(bundle["fx_rates"], config, issues)
    sgd_info = fx.check_sgd_closing_rate(bundle["tb_uk"])

    # 3. Validate Local-to-Group COA Mappings (intercepts UK 2310 Deferred income -> 4100 trap)
    uk_map, in_map = build_validated_mappings(
        bundle["map_uk"], bundle["map_in"], bundle["group_coa"], bundle["tb_uk"], config, issues
    )

    # 4. Evaluate 20 Manual Journal Entries (Policy 6 gatekeeper & prompt-injection sandbox)
    posted_journals, journal_summary = evaluate_journals(
        bundle["adjustments"],
        bundle["group_coa"],
        uk_map,
        in_map,
        bundle["tb_uk"],
        bundle["in_pl_monthly"],
        fx,
        config,
        issues,
        data_dir=args.data_dir,
    )

    # 5. Close Standalone Entity Books (Subledger checks, UK IC in-transit & Policy 3 FX, IN Q1 cut-off)
    us_accts, uk_accts, in_accts, ic_reconciliation = close_entity_books(
        bundle["tb_us"],
        bundle["tb_uk"],
        bundle["tb_in"],
        bundle["in_pl_monthly"],
        bundle["intercompany"],
        bundle["subledger_controls"],
        uk_map,
        in_map,
        posted_journals,
        fx,
        config,
        issues,
    )

    # 6. Run Group Consolidation (Eliminations ELIM-01..05, Goodwill, NCI, Equity Bridge)
    cons_result = run_group_consolidation(
        us_accts, uk_accts, in_accts, bundle["group_coa"], bundle["prior_year_group"], fx
    )

    # 7. Run Self-Correction & Verification Assertions before writing outputs
    verification_report = verify_consolidation(cons_result, fx)

    # 8. Write all required deliverables to /output
    write_outputs(
        args.output_dir,
        bundle["group_coa"],
        cons_result,
        ic_reconciliation,
        sgd_info,
        journal_summary,
        issues,
        verification_report,
        config,
    )

    m = cons_result["metrics"]
    print(f"[SUCCESS] Northwind Group FY2024 Consolidation complete (Bundle {config.get('bundle_id')}).")
    print(f"  Group Revenue               : £{m['group_revenue']:14,.2f}")
    print(f"  Group Profit                : £{m['group_profit']:14,.2f}")
    print(f"    - Attributable to Owners  : £{m['profit_owners']:14,.2f}")
    print(f"    - Attributable to NCI     : £{m['profit_nci']:14,.2f}")
    print(f"  Closing Goodwill (1700)     : £{m['goodwill_closing']:14,.2f}")
    print(f"  Closing NCI (3400)          : £{m['nci_closing']:14,.2f}")
    print(f"  Translation Reserve Mov.    : £{m['translation_reserve_movement']:14,.2f}")
    print(f"  Total Assets                : £{m['total_assets']:14,.2f}")
    print(f"  Total Liabilities           : £{m['total_liabilities']:14,.2f}")
    print(f"  Total Equity                : £{m['total_equity']:14,.2f}")
    print(f"  Journals (Post/Rej/Hold)    : {journal_summary['posted']} / {journal_summary['rejected']} / {journal_summary['held_for_review']}")
    print(f"  Issues Logged               : {len(issues)} -> {args.output_dir}/issues.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())