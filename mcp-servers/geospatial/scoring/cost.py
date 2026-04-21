import logging

import pandas as pd

from ..config import load_config

log = logging.getLogger(__name__)


def calculate_costs(pair):
    config = load_config()
    cm = config.get("cost_model", {})
    benchmarks = config.get("cost_benchmarks", {})
    physics = config.get("physics", {})

    phase = cm.get("phase", 1)
    penstock_per_km = cm.get("penstock_usd_per_km", 46_960_000)
    powerhouse_per_mw = cm.get("powerhouse_usd_per_mw", 467_967)
    upper_res_per_mcm = cm.get("reservoir_upper_usd_per_mcm", 15_230_000)
    lower_res_per_mcm = cm.get("reservoir_lower_usd_per_mcm", 38_770_000)
    substation_per_mw = cm.get("substation_usd_per_mw", 92_565)
    roads_fixed = cm.get("roads_usd_fixed", 10_800_000)
    other_per_mw = cm.get("other_usd_per_mw", 66_852)
    tunneling_per_km = cm.get("tunneling_usd_per_km", 0)
    depreciation = cm.get("depreciation_years", 40)
    annual_cycles = cm.get("annual_cycles", 300)
    battery_capex = benchmarks.get("battery_capex_usd_per_mwh", 100_000)
    duration_hours = physics.get("power_duration_hours", 3)

    distance_km = pair.get("distance_km")
    energy_mwh = pair.get("energy_mwh_standard")
    upper_cap = pair.get("upper_capacity_mcm")
    lower_cap = pair.get("lower_capacity_mcm")
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

    penstock_usd = _val(distance_km) * penstock_per_km
    powerhouse_usd = _val(power_mw) * powerhouse_per_mw
    total_capex_usd = penstock_usd + powerhouse_usd

    upper_usd = lower_usd = substation_usd = other_usd = tunneling_usd = 0
    if phase >= 2:
        upper_usd = _val(upper_cap) * upper_res_per_mcm
        lower_usd = _val(lower_cap) * lower_res_per_mcm
        substation_usd = _val(power_mw) * substation_per_mw
        other_usd = _val(power_mw) * other_per_mw + roads_fixed
        tunneling_usd = _val(distance_km) * tunneling_per_km
        total_capex_usd += upper_usd + lower_usd + substation_usd + other_usd + tunneling_usd

    lifetime_energy_mwh = energy_mwh * annual_cycles * depreciation
    lcoe = total_capex_usd / lifetime_energy_mwh if lifetime_energy_mwh > 0 else None
    capex_per_mwh_usd = total_capex_usd / energy_mwh if energy_mwh > 0 else None
    capex_advantage = (battery_capex - capex_per_mwh_usd) / battery_capex * 100 if capex_per_mwh_usd is not None else None

    return {
        "penstock_cost_usd": round(penstock_usd),
        "powerhouse_cost_usd": round(powerhouse_usd),
        "reservoir_cost_usd": round(upper_usd + lower_usd),
        "substation_cost_usd": round(substation_usd),
        "other_cost_usd": round(other_usd),
        "tunneling_cost_usd": round(tunneling_usd),
        "total_capex_usd": round(total_capex_usd),
        "lcoe_usd_per_mwh": round(lcoe, 1) if lcoe else None,
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
    if "lcoe_usd_per_mwh" in result.columns:
        valid_lcoe = result["lcoe_usd_per_mwh"].dropna()
        if len(valid_lcoe) > 0:
            log.info(f"LCOE range: ${valid_lcoe.min():.0f} - ${valid_lcoe.max():.0f}/MWh")
    if "capex_per_mwh_usd" in result.columns:
        valid_capex = result["capex_per_mwh_usd"].dropna()
        if len(valid_capex) > 0:
            log.info(f"CAPEX/MWh range: ${valid_capex.min():,.0f} - ${valid_capex.max():,.0f}/MWh")
    return result
