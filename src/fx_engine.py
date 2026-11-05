"""FX Rate Engine: computes cross-rates per Policy 2 and audits missing closing rates."""
from typing import Dict, Any, List
import pandas as pd
from .models import AuditIssue


class FXEngine:
    def __init__(self, fx_df: pd.DataFrame, config: Dict[str, Any], issues: List[AuditIssue]):
        self.raw_rates: Dict[tuple, float] = {}
        self.sources: Dict[tuple, str] = {}
        self.config = config
        self.issues = issues

        for _, row in fx_df.iterrows():
            pair = (row["base_currency"].strip(), row["quote_currency"].strip(), row["rate_type"].strip())
            self.raw_rates[pair] = float(row["rate"])
            self.sources[pair] = row["source_ref"]

        # Policy 2: Where a GBP rate is not given directly, use the product of the two given rates of the same type
        self.gbp_usd: Dict[str, float] = {}
        self.gbp_inr: Dict[str, float] = {}
        for rtype in ["opening", "average", "h2_average", "spot", "closing"]:
            u = self.raw_rates[("GBP", "USD", rtype)]
            i = self.raw_rates[("USD", "INR", rtype)]
            self.gbp_usd[rtype] = u
            self.gbp_inr[rtype] = u * i

    def check_sgd_closing_rate(self, tb_uk: pd.DataFrame) -> Dict[str, Any]:
        """Checks if GBP/SGD closing rate exists for UK account 1210 (SGD 40,000)."""
        override_rate = self.config.get("missing_fx_policy", {}).get("UK_1210_SGD_closing_rate")
        if ("GBP", "SGD", "closing") in self.raw_rates:
            rate = self.raw_rates[("GBP", "SGD", "closing")]
            return {"value": round(40000.0 / rate, 2), "rate": rate, "reason": None}
        if override_rate is not None:
            rate = float(override_rate)
            return {"value": round(40000.0 / rate, 2), "rate": rate, "reason": "Computed from policy_config override"}

        # Log missing rate defect in issues.json
        sgd_row = tb_uk[tb_uk["nominal_code"] == "1210"].iloc[0]
        booked_gbp = float(sgd_row["balance"])
        self.issues.append(
            AuditIssue(
                issue_id="ISS-FX-001",
                file="fx_rates.csv",
                line="fx_rates.csv:L12-L13, tb_uk.csv:L3",
                entity="UK",
                category="missing_fx_rate",
                amount_affected=booked_gbp,
                currency="GBP",
                amount_affected_gbp=booked_gbp,
                system_action="assumed",
                description=(
                    "Missing 2024-12-31 closing exchange rate for GBP/SGD in fx_rates.csv "
                    "(only opening 1.6830 and FY2024 average 1.7120 are present). UK nominal account 1210 "
                    "(Bank - DBS SGD) holds SGD 40,000.00 recorded at £23,010.00 GBP."
                ),
                resolution=(
                    "Reported sgd_bank_gbp as null in control_figures per Appendix instructions "
                    "(never estimate an external rate). Retained carrying book balance of £23,010.00 GBP "
                    "in Group account 1100 (Cash and cash equivalents) so Total Assets remains traceable to TB."
                ),
            )
        )
        return {
            "value": None,
            "rate": None,
            "reason": (
                "Closing GBP/SGD exchange rate as of 2024-12-31 is missing from fx_rates.csv "
                "(only opening 1.6830 and FY2024 average 1.7120 are provided). Under Group Policy 3, "
                "foreign currency monetary items must be retranslated at the closing rate; therefore "
                "the closing GBP value of UK nominal account 1210 (SGD 40,000.00, carrying book value "
                "£23,010.00) cannot be determined without estimating an external rate."
            ),
        }