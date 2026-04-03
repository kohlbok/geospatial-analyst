import logging

import pandas as pd

from ..config import load_config

log = logging.getLogger(__name__)


def calculate_costs(pair):
    config = load_config()
    cm = config.get("cost_model", {})
    benchmarks = config.get("cost_benchmarks", {})

    penstock_per_km = cm.get("penstock_eur_per_km", 43_000_000)
    upper_res_per_mcm = cm.get("reservoir_upper_eur_per_mcm", 14_000_000)
    lower_res_per_mcm = cm.get("reservoir_lower_eur_per_mcm", 36_000_000)
    powerhouse_per_mw = cm.get("powerhouse_eur_per_mw", 490_000)
    fixed_costs = cm.get("fixed_costs_eur", 42_000_000)
    grid_per_km = cm.get("grid_connection_usd_per_km", 1_000_000)
    depreciation = cm.get("depreciation_years", 40)
    annual_cycles = cm.get("annual_cycles", 300)
    eur_to_usd = cm.get("eur_to_usd", 1.08)
    battery_capex = benchmarks.get("battery_capex_usd_per_mwh", 100_000)

    distance_km = pair.get("distance_km")
    energy_mwh = pair.get("energy_mwh_standard")
    grid_km = pair.get("grid_distance_km")
    upper_cap = pair.get("upper_capacity_mcm")
    lower_cap = pair.get("lower_capacity_mcm")
    config_physics = config.get("physics", {})
    duration_hours = config_physics.get("power_duration_hours", 8)
    power_mw = pair.get(f"power_mw_{duration_hours}hr")

    if energy_mwh is None or energy_mwh <= 0 or distance_km is None:
        return {}

    def _val(v):
        if v is None:
            return 0
        try:
            f = float(v)
            return 0 if pd.isna(f) else f
        except (ValueError, TypeError):
            return 0

    penstock_eur = _val(distance_km) * penstock_per_km
    upper_eur = _val(upper_cap) * upper_res_per_mcm
    lower_eur = _val(lower_cap) * lower_res_per_mcm
    powerhouse_eur = _val(power_mw) * powerhouse_per_mw
    grid_eur = _val(grid_km) * grid_per_km / eur_to_usd

    total_capex_eur = penstock_eur + upper_eur + lower_eur + powerhouse_eur + fixed_costs + grid_eur
    lifetime_energy_mwh = energy_mwh * annual_cycles * depreciation
    lcoe = total_capex_eur / lifetime_energy_mwh if lifetime_energy_mwh > 0 else None

    capex_per_mwh_eur = total_capex_eur / energy_mwh if energy_mwh > 0 else None
    capex_per_mwh_usd = capex_per_mwh_eur * eur_to_usd if capex_per_mwh_eur is not None else None
    capex_advantage = (battery_capex - capex_per_mwh_usd) / battery_capex * 100 if capex_per_mwh_usd is not None else None

    return {
        "penstock_cost_eur": round(penstock_eur),
        "reservoir_cost_eur": round(upper_eur + lower_eur),
        "powerhouse_cost_eur": round(powerhouse_eur),
        "grid_connection_cost_eur": round(grid_eur),
        "total_capex_eur": round(total_capex_eur),
        "lcoe_eur_per_mwh": round(lcoe, 1) if lcoe else None,
        "capex_per_mwh_eur": round(capex_per_mwh_eur) if capex_per_mwh_eur is not None else None,
        "capex_per_mwh_usd": round(capex_per_mwh_usd) if capex_per_mwh_usd is not None else None,
        "battery_capex_usd_per_mwh": battery_capex,
        "capex_advantage_pct": round(capex_advantage, 1) if capex_advantage is not None else None,
        "psh_cheaper": capex_per_mwh_usd < battery_capex if capex_per_mwh_usd is not None else None,
    }


def calculate_all_costs(pairs_df):
    log.info(f"Calculating costs for {len(pairs_df)} pairs")

    from ..config import scrub_nan

    results = []
    for _, pair in pairs_df.iterrows():
        row = scrub_nan(pair.to_dict())
        costs = calculate_costs(row)
        row.update(costs)
        results.append(row)

    result = pd.DataFrame(results)
    if "psh_cheaper" in result.columns:
        cheaper = result["psh_cheaper"].sum()
        log.info(f"PSH cheaper than batteries: {cheaper}/{len(result)} pairs")
    if "lcoe_eur_per_mwh" in result.columns:
        valid_lcoe = result["lcoe_eur_per_mwh"].dropna()
        if len(valid_lcoe) > 0:
            log.info(f"LCOE range: {valid_lcoe.min():.0f} - {valid_lcoe.max():.0f} EUR/MWh")
    if "capex_per_mwh_usd" in result.columns:
        valid_capex = result["capex_per_mwh_usd"].dropna()
        if len(valid_capex) > 0:
            log.info(f"CAPEX/MWh range: ${valid_capex.min():,.0f} - ${valid_capex.max():,.0f}/MWh")
    return result
