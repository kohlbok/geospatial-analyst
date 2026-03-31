import logging

import pandas as pd

from ..config import load_config

log = logging.getLogger(__name__)


def compare_costs(energy_mwh, head_m=None, distance_km=None, tunnel_km=None):
    config = load_config()
    cost_cfg = config.get("cost_benchmarks", config.get("cost", {}))

    battery_cost = cost_cfg.get("battery_usd_per_mwh", cost_cfg.get("battery_benchmark_usd_per_mwh", 300))
    psh_low = cost_cfg.get("psh_usd_per_mwh_low", cost_cfg.get("psh_benchmark_usd_per_mwh_low", 150))
    psh_high = cost_cfg.get("psh_usd_per_mwh_high", cost_cfg.get("psh_benchmark_usd_per_mwh_high", 250))
    depreciation = cost_cfg.get("depreciation_years", 40)

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

    cost_advantage = (battery_cost - psh_estimate) / battery_cost * 100

    return {
        "psh_cost_usd_per_mwh": round(psh_estimate, 0),
        "battery_cost_usd_per_mwh": round(battery_cost, 0),
        "cost_advantage_pct": round(cost_advantage, 1),
        "psh_cheaper": psh_estimate < battery_cost,
    }


def calculate_lcoe(pair):
    config = load_config()
    cm = config.get("cost_model", {})

    tunneling_per_km = cm.get("tunneling_eur_per_km", 6_500_000)
    grid_per_km = cm.get("grid_connection_usd_per_km", 1_000_000)
    facility_capex = cm.get("facility_capex_eur")
    depreciation = cm.get("depreciation_years", 40)
    annual_cycles = cm.get("annual_cycles", 300)
    eur_to_usd = cm.get("eur_to_usd", 1.08)

    distance_km = pair.get("distance_km")
    grid_km = pair.get("grid_distance_km")
    energy_mwh = pair.get("energy_mwh_standard")

    if energy_mwh is None or energy_mwh <= 0 or distance_km is None:
        return {}

    tunneling_eur = distance_km * tunneling_per_km
    grid_eur = (grid_km * grid_per_km / eur_to_usd) if grid_km is not None and not pd.isna(grid_km) else 0
    facility_eur = facility_capex if facility_capex else 0

    total_capex_eur = tunneling_eur + grid_eur + facility_eur
    lifetime_energy_mwh = energy_mwh * annual_cycles * depreciation
    lcoe = total_capex_eur / lifetime_energy_mwh if lifetime_energy_mwh > 0 else None

    return {
        "tunneling_cost_eur": round(tunneling_eur),
        "grid_connection_cost_eur": round(grid_eur),
        "facility_capex_eur": round(facility_eur),
        "total_capex_eur": round(total_capex_eur),
        "lcoe_eur_per_mwh": round(lcoe, 1) if lcoe else None,
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

        lcoe = calculate_lcoe(pair)
        row.update(lcoe)

        results.append(row)

    result = pd.DataFrame(results)
    cheaper = result["psh_cheaper"].sum() if "psh_cheaper" in result.columns else 0
    log.info(f"PSH cheaper than batteries: {cheaper}/{len(result)} pairs")
    if "lcoe_eur_per_mwh" in result.columns:
        valid_lcoe = result["lcoe_eur_per_mwh"].dropna()
        if len(valid_lcoe) > 0:
            log.info(f"LCOE range: {valid_lcoe.min():.0f} - {valid_lcoe.max():.0f} EUR/MWh")
    return result
