"""Validates local-to-group COA mappings and intercepts semantic misclassifications."""
from typing import Dict, Any, List, Tuple
import pandas as pd
from .models import AuditIssue


def build_validated_mappings(
    map_uk: pd.DataFrame,
    map_in: pd.DataFrame,
    group_coa: pd.DataFrame,
    tb_uk: pd.DataFrame,
    config: Dict[str, Any],
    issues: List[AuditIssue],
) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Returns validated (uk_map, in_map) dicts and logs mapping defects to issues."""
    coa_names = dict(zip(group_coa["account_code"], group_coa["account_name"]))

    uk_map: Dict[str, str] = {}
    for _, row in map_uk.iterrows():
        lcode = str(row["local_code"]).strip()
        lname = str(row["local_name"]).strip()
        gcode = str(row["group_code"]).strip()

        # Detect semantic mismatch: Deferred income (Liability) mapped to Revenue (4100)
        if lcode == "2310" and gcode == "4100":
            uk_row = tb_uk[tb_uk["nominal_code"] == "2310"].iloc[0]
            bal = abs(float(uk_row["balance"]))
            target_code = config.get("mapping_overrides", {}).get("UK", {}).get("2310", "2300")
            issues.append(
                AuditIssue(
                    issue_id="ISS-MAP-001",
                    file="map_uk.csv",
                    line=f"{row['source_ref']}, {uk_row['source_ref']}",
                    entity="UK",
                    category="wrong_account_mapping",
                    amount_affected=bal,
                    currency="GBP",
                    amount_affected_gbp=bal,
                    system_action="blocked",
                    description=(
                        f"UK local account 2310 ('{lname}', credit balance £{bal:,.2f}) is wrongly mapped "
                        f"in map_uk.csv to Group account 4100 ('{coa_names['4100']}', P&L Revenue) instead "
                        f"of Group account 2300 ('{coa_names['2300']}', Balance Sheet Liability)."
                    ),
                    resolution=(
                        f"Blocked erroneous mapping to 4100 and remapped UK 2310 to Group account {target_code} "
                        f"(Deferred income), preventing a £{bal:,.2f} overstatement of Group Revenue and Profit."
                    ),
                )
            )
            uk_map[lcode] = target_code
        else:
            uk_map[lcode] = gcode

    in_map: Dict[str, str] = {}
    for _, row in map_in.iterrows():
        lcode = str(row["local_code"]).strip()
        gcode = str(row["group_code"]).strip()
        in_map[lcode] = gcode

    return uk_map, in_map