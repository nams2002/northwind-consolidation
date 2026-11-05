"""Strict schema ingestion preserving string account codes and CSV line numbers."""
import json
import os
import pandas as pd
from typing import Dict, Any


def load_bundle(data_dir: str = "data", config_path: str = "policy_config.json") -> Dict[str, Any]:
    """Loads all 15 input files from data_dir and attaches 1-based source file line references."""
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    def read_csv_with_line(filename: str, dtype_spec=str) -> pd.DataFrame:
        path = os.path.join(data_dir, filename)
        df = pd.read_csv(path, dtype=dtype_spec, keep_default_na=False)
        # Line 1 is the CSV header; row index 0 is L2
        df["source_ref"] = [f"{filename}:L{i + 2}" for i in range(len(df))]
        return df

    entities = read_csv_with_line("entities.csv")
    group_coa = read_csv_with_line("group_coa.csv")
    map_uk = read_csv_with_line("map_uk.csv")
    map_in = read_csv_with_line("map_in.csv")
    tb_us = read_csv_with_line("tb_us.csv")
    tb_uk = read_csv_with_line("tb_uk.csv")
    tb_in = read_csv_with_line("tb_in.csv")
    in_pl_monthly = read_csv_with_line("in_pl_monthly.csv")
    intercompany = read_csv_with_line("intercompany.csv")
    subledger_controls = read_csv_with_line("subledger_controls.csv")
    fx_rates = read_csv_with_line("fx_rates.csv")
    prior_year_group = read_csv_with_line("prior_year_group.csv")

    adj_path = os.path.join(data_dir, "adjustments.json")
    with open(adj_path, "r", encoding="utf-8") as f:
        adjustments = json.load(f)

    with open(os.path.join(data_dir, "acquisition_note.md"), "r", encoding="utf-8") as f:
        acquisition_note = f.read()

    with open(os.path.join(data_dir, "group_policies.md"), "r", encoding="utf-8") as f:
        group_policies = f.read()

    return {
        "config": config,
        "entities": entities,
        "group_coa": group_coa,
        "map_uk": map_uk,
        "map_in": map_in,
        "tb_us": tb_us,
        "tb_uk": tb_uk,
        "tb_in": tb_in,
        "in_pl_monthly": in_pl_monthly,
        "intercompany": intercompany,
        "subledger_controls": subledger_controls,
        "fx_rates": fx_rates,
        "prior_year_group": prior_year_group,
        "adjustments": adjustments,
        "acquisition_note": acquisition_note,
        "group_policies": group_policies,
    }