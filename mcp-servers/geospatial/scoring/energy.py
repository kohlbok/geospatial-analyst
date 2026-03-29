import logging

import pandas as pd

from ..config import load_config

log = logging.getLogger(__name__)


def calculate_energy(head_m, volume_m3, efficiency=None):
    config = load_config()
    physics = config.get("physics", config.get("energy", {}))

    if efficiency is None:
        efficiency = physics.get("round_trip_efficiency", 0.78)

    density = physics.get("water_density_kg_m3", 1000)
    gravity = physics.get("gravity_m_s2", 9.81)

    energy_joules = head_m * volume_m3 * density * gravity * efficiency
    energy_mwh = energy_joules / 3_600_000_000
    return energy_mwh


def calculate_pair_energy(pair, fill_levels=None):
    if fill_levels is None:
        fill_levels = {"conservative": 0.3, "standard": 0.6, "optimistic": 0.9}

    upper_cap = pair.get("upper_capacity_mcm")
    lower_cap = pair.get("lower_capacity_mcm")
    head = pair.get("head_m")

    if head is None or pd.isna(head):
        return {f"energy_mwh_{level}": None for level in fill_levels}

    caps = [c for c in [upper_cap, lower_cap] if c is not None and not pd.isna(c)]
    if not caps:
        return {f"energy_mwh_{level}": None for level in fill_levels}

    usable_volume_mcm = min(caps)
    usable_volume_m3 = usable_volume_mcm * 1e6

    results = {}
    for level_name, fill_fraction in fill_levels.items():
        vol = usable_volume_m3 * fill_fraction
        mwh = calculate_energy(head, vol)
        results[f"energy_mwh_{level_name}"] = round(mwh, 1)

    power_mw = calculate_energy(head, usable_volume_m3 * fill_levels["standard"]) / 8
    results["power_mw_8hr"] = round(power_mw, 1)

    return results


def calculate_all_energies(pairs_df):
    log.info(f"Calculating energy for {len(pairs_df)} pairs")

    energy_rows = []
    for _, pair in pairs_df.iterrows():
        row = pair.to_dict()
        energy = calculate_pair_energy(pair)
        row.update(energy)
        energy_rows.append(row)

    result = pd.DataFrame(energy_rows)
    valid = result["energy_mwh_standard"].notna()
    log.info(f"Energy calculated for {valid.sum()} pairs")

    if valid.any():
        log.info(
            f"Energy range (standard): "
            f"{result.loc[valid, 'energy_mwh_standard'].min():.0f} - "
            f"{result.loc[valid, 'energy_mwh_standard'].max():.0f} MWh"
        )

    return result
