import logging

import numpy as np
import pandas as pd

from ..config import load_config

log = logging.getLogger(__name__)


def compare_costs(energy_mwh, head_m=None, distance_km=None, tunnel_km=None):
    config = load_config()
    cost_cfg = config["cost"]

    battery_cost = cost_cfg["battery_benchmark_usd_per_mwh"]
    psh_low = cost_cfg["psh_benchmark_usd_per_mwh_low"]
    psh_high = cost_cfg["psh_benchmark_usd_per_mwh_high"]
    depreciation = cost_cfg["depreciation_years"]

    if head_m and head_m > 300:
        psh_estimate = psh_low
    elif head_m and head_m > 200:
        psh_estimate = (psh_low + psh_high) / 2
    else:
        psh_estimate = psh_high

    if tunnel_km and tunnel_km > 3:
        psh_estimate *= 1.0 + (tunnel_km - 3) * 0.05

    if distance_km and distance_km > 20:
        psh_estimate *= 1.0 + (distance_km - 20) * 0.01

    battery_lcoe = battery_cost / depreciation
    psh_lcoe = psh_estimate

    cost_advantage = (battery_lcoe - psh_lcoe) / battery_lcoe * 100

    return {
        "psh_cost_usd_per_mwh": round(psh_estimate, 0),
        "battery_cost_usd_per_mwh": round(battery_lcoe, 0),
        "cost_advantage_pct": round(cost_advantage, 1),
        "psh_cheaper": psh_lcoe < battery_lcoe,
    }


def calculate_all_costs(pairs_df):
    log.info(f"Calculating cost comparison for {len(pairs_df)} pairs")

    results = []
    for _, pair in pairs_df.iterrows():
        row = pair.to_dict()
        energy = pair.get("energy_mwh_standard")
        if energy is None or energy <= 0:
            row["psh_cost_usd_per_mwh"] = None
            row["battery_cost_usd_per_mwh"] = None
            row["cost_advantage_pct"] = None
            row["psh_cheaper"] = None
        else:
            costs = compare_costs(
                energy,
                head_m=pair.get("head_m"),
                distance_km=pair.get("distance_km"),
                tunnel_km=pair.get("tunnel_length_km"),
            )
            row.update(costs)
        results.append(row)

    result = pd.DataFrame(results)
    cheaper = result["psh_cheaper"].sum() if "psh_cheaper" in result.columns else 0
    log.info(f"PSH cheaper than batteries: {cheaper}/{len(result)} pairs")
    return result
