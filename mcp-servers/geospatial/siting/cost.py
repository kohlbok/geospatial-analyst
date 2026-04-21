import logging
import math

import numpy as np

log = logging.getLogger(__name__)


def optimize_candidate(basin, dam_elev, existing_capacity_mcm, params):
    p2 = params.get("siting", {})
    cm = params.get("cost_model", {})
    physics = params.get("physics", {})

    target_power_mw = p2.get("target_power_mw", 250)
    min_energy_mwh = p2.get("min_energy_mwh", 600)
    battery_capex = p2.get("battery_capex_usd_per_mwh", 100_000)
    marginal_mult = p2.get("marginal_threshold_multiplier", 1.5)
    max_capex = p2.get("max_total_capex_usd", 120_000_000)
    abdel_flag_ratio = p2.get("abdelmoumen_ratio_flag", 4.0)
    max_friction_frac = p2.get("max_friction_fraction", 0.10)
    darcy_f = p2.get("darcy_friction_factor", 0.012)
    base_rate = p2.get("penstock_base_rate_usd_per_km_per_m_dia", 9_630_000)
    d_range = p2.get("penstock_diameter_range_m", [1.0, 10.0])
    d_samples = p2.get("penstock_diameter_samples", 20)
    efficiency = physics.get("round_trip_efficiency", 0.78)
    usable_fraction = physics.get("usable_volume_fraction", 0.6)

    powerhouse_per_mw = cm.get("powerhouse_usd_per_mw", 467_967)
    substation_per_mw = cm.get("substation_usd_per_mw", 92_565)
    roads_fixed = cm.get("roads_usd_fixed", 10_800_000)
    other_per_mw = cm.get("other_usd_per_mw", 66_852)
    upper_res_per_mcm = cm.get("reservoir_upper_usd_per_mcm", 15_230_000)
    lower_res_per_mcm = cm.get("reservoir_lower_usd_per_mcm", 38_770_000)

    direction = basin["direction"]
    dam_role = basin.get("existing_dam_role", "lower" if direction == "up" else "upper")
    reservoir_per_mcm = upper_res_per_mcm if dam_role == "lower" else lower_res_per_mcm

    penstock_length_m = float(basin["distance_km"]) * 1000.0
    curve = basin.get("area_fill_curve", [])
    if not curve or penstock_length_m <= 0:
        return None

    existing_valid = existing_capacity_mcm is not None and existing_capacity_mcm > 0
    existing_usable_m3 = existing_capacity_mcm * 1e6 * usable_fraction if existing_valid else None
    data_quality = "complete" if existing_valid else "partial"

    rho = 1000.0
    g = 9.81

    powerhouse_usd = target_power_mw * powerhouse_per_mw
    substation_usd = target_power_mw * substation_per_mw
    other_usd = target_power_mw * other_per_mw + roads_fixed
    fixed_infra = powerhouse_usd + substation_usd + other_usd

    diameters = np.linspace(d_range[0], d_range[1], d_samples)

    best = None
    for sample in curve:
        fill_m = float(sample["fill_m"])
        gross_volume_m3 = float(sample["volume_m3"])
        candidate_usable_m3 = gross_volume_m3 * usable_fraction
        if candidate_usable_m3 <= 0:
            continue
        usable_volume_m3 = min(candidate_usable_m3, existing_usable_m3) if existing_valid else candidate_usable_m3
        head_gross = (fill_m - dam_elev) if direction == "up" else (dam_elev - fill_m)
        if head_gross <= 0:
            continue

        flow = (target_power_mw * 1e6) / (rho * g * head_gross * efficiency)
        reservoir_usd = (usable_volume_m3 / 1e6) * reservoir_per_mcm

        for D in diameters:
            friction_loss = darcy_f * penstock_length_m * 8 * (flow ** 2) / (g * (math.pi ** 2) * (D ** 5))
            if friction_loss >= max_friction_frac * head_gross:
                continue
            net_head = head_gross - friction_loss
            energy_mwh = rho * g * net_head * usable_volume_m3 * efficiency / 3_600_000_000
            if energy_mwh < min_energy_mwh:
                continue
            penstock_usd = base_rate * (penstock_length_m / 1000.0) * D
            total_capex = penstock_usd + fixed_infra + reservoir_usd
            capex_per_mwh = total_capex / energy_mwh

            if best is None or capex_per_mwh < best["capex_per_mwh_usd"]:
                best = {
                    "optimal_fill_m": fill_m,
                    "optimal_diameter_m": float(D),
                    "optimal_footprint_area_m2": float(sample.get("area_m2", 0.0)),
                    "candidate_volume_mcm": round(candidate_usable_m3 / 1e6, 3),
                    "existing_capacity_mcm": existing_capacity_mcm if existing_valid else None,
                    "usable_volume_m3": usable_volume_m3,
                    "usable_volume_mcm": round(usable_volume_m3 / 1e6, 3),
                    "binding_reservoir": "existing" if existing_valid and existing_usable_m3 < candidate_usable_m3 else "candidate",
                    "data_quality": data_quality,
                    "head_m": head_gross,
                    "net_head_m": net_head,
                    "friction_pct": 100.0 * friction_loss / head_gross,
                    "flow_rate_m3s": flow,
                    "energy_mwh": energy_mwh,
                    "penstock_cost_usd": penstock_usd,
                    "powerhouse_cost_usd": powerhouse_usd,
                    "substation_cost_usd": substation_usd,
                    "other_cost_usd": other_usd,
                    "reservoir_cost_usd": reservoir_usd,
                    "total_capex_usd": total_capex,
                    "capex_per_mwh_usd": capex_per_mwh,
                }

    if best is None:
        return None

    dh_ratio = penstock_length_m / best["head_m"] if best["head_m"] > 0 else float("inf")
    best["penstock_length_m"] = penstock_length_m
    best["distance_head_ratio"] = dh_ratio
    best["battery_ratio"] = best["capex_per_mwh_usd"] / battery_capex if battery_capex > 0 else None
    best["passes_battery_test"] = best["capex_per_mwh_usd"] < battery_capex
    best["marginal_flag"] = best["capex_per_mwh_usd"] < battery_capex * marginal_mult
    best["abdelmoumen_flag"] = dh_ratio > abdel_flag_ratio

    best["max_discharge_hours"] = best["energy_mwh"] / target_power_mw if target_power_mw > 0 else 0
    best["energy_mwh_3hr"] = min(best["energy_mwh"], target_power_mw * 3)
    best["energy_mwh_5hr"] = min(best["energy_mwh"], target_power_mw * 5)
    best["energy_mwh_8hr"] = min(best["energy_mwh"], target_power_mw * 8)

    if best["total_capex_usd"] > max_capex and not best["marginal_flag"]:
        return None

    for k in [
        "optimal_fill_m", "optimal_diameter_m", "head_m", "net_head_m",
        "friction_pct", "flow_rate_m3s", "energy_mwh",
        "energy_mwh_3hr", "energy_mwh_5hr", "energy_mwh_8hr", "max_discharge_hours",
        "penstock_length_m", "distance_head_ratio", "battery_ratio",
    ]:
        if best.get(k) is not None:
            best[k] = round(best[k], 3)
    for k in [
        "penstock_cost_usd", "powerhouse_cost_usd", "substation_cost_usd",
        "other_cost_usd", "reservoir_cost_usd", "total_capex_usd",
        "capex_per_mwh_usd", "usable_volume_m3", "optimal_footprint_area_m2",
    ]:
        if best.get(k) is not None:
            best[k] = round(best[k])
    return best
