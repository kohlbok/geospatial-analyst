import logging

import pandas as pd

from ..config import load_config

log = logging.getLogger(__name__)


def score_pairs(pairs_df, weight_variant="default"):
    cfg = load_config()
    raw_weights = cfg.get("scoring_weights", {})
    weights = {
        "energy_potential": raw_weights.get("energy_potential", 0.40),
        "cost_advantage": raw_weights.get("cost_advantage", 0.35),
        "grid_proximity": raw_weights.get("proximity_to_grid", 0.25),
    }
    log.info(f"Scoring {len(pairs_df)} pairs with {weight_variant} weights: {weights}")

    df = pairs_df.copy()

    df["score_cost"] = _safe_normalize(df, "capex_advantage_pct", higher_better=True)
    df["score_energy"] = _safe_normalize(df, "energy_mwh_standard", higher_better=True)
    df["score_grid"] = _safe_normalize(df, "grid_distance_km", higher_better=False)

    df["composite_score"] = (
        df["score_cost"] * weights["cost_advantage"]
        + df["score_energy"] * weights["energy_potential"]
        + df["score_grid"] * weights["grid_proximity"]
    )

    df = df.sort_values("composite_score", ascending=False).reset_index(drop=True)
    df["rank"] = range(1, len(df) + 1)

    log.info(
        f"Scoring complete. Top score: {df['composite_score'].iloc[0]:.3f}, "
        f"Bottom score: {df['composite_score'].iloc[-1]:.3f}"
    )
    return df


def _safe_normalize(df, column_name, higher_better=True):
    if column_name not in df.columns:
        return pd.Series(0.5, index=df.index)
    return _normalize_column(df[column_name], higher_better=higher_better)


def _normalize_column(series, higher_better=True):
    if series is None or series.isna().all():
        return pd.Series(0.5, index=series.index if series is not None else [])

    valid = series.dropna()
    if len(valid) == 0 or valid.max() == valid.min():
        return series.fillna(0.5)

    if higher_better:
        normalized = (series - valid.min()) / (valid.max() - valid.min())
    else:
        normalized = 1 - (series - valid.min()) / (valid.max() - valid.min())

    return normalized.fillna(0.5)
