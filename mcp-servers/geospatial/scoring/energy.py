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


def calculate_pair_energy(pair):
    config = load_config()
    physics = config.get("physics", {})

    fill_fraction = physics.get("usable_volume_fraction", 0.6)
    duration_hours = physics.get("power_duration_hours", 8)

    upper_cap = pair.get("upper_capacity_mcm")
    lower_cap = pair.get("lower_capacity_mcm")
    head = pair.get("head_m")

    if head is None or pd.isna(head):
        return {"energy_mwh_standard": None}

    upper_valid = upper_cap is not None and not pd.isna(upper_cap)
    lower_valid = lower_cap is not None and not pd.isna(lower_cap)

    if upper_valid and lower_valid:
        data_quality = "complete"
    elif upper_valid or lower_valid:
        data_quality = "partial"
    else:
        return {"energy_mwh_standard": None, "data_quality": "missing"}

    caps = [c for c in [upper_cap, lower_cap] if c is not None and not pd.isna(c)]
    usable_volume_mcm = min(caps)
    usable_volume_m3 = usable_volume_mcm * 1e6
    vol = usable_volume_m3 * fill_fraction

    energy_mwh = calculate_energy(head, vol)
    power_mw = energy_mwh / duration_hours

    return {
        "energy_mwh_standard": round(energy_mwh, 1),
        f"power_mw_{duration_hours}hr": round(power_mw, 1),
        "data_quality": data_quality,
    }


def calculate_all_energies(pairs_df):
    log.info(f"Calculating energy for {len(pairs_df)} pairs")

    from ..config import scrub_nan

    energy_rows = []
    for _, pair in pairs_df.iterrows():
        row = scrub_nan(pair.to_dict())
        energy = calculate_pair_energy(row)
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
