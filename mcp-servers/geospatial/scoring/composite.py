import logging

import numpy as np
import pandas as pd

from ..config import load_config, get_scoring_weights, get_screening_params

log = logging.getLogger(__name__)


def score_pairs(pairs_df, weight_variant="default"):
    weights = get_scoring_weights(weight_variant)
    log.info(f"Scoring {len(pairs_df)} pairs with {weight_variant} weights: {weights}")

    df = pairs_df.copy()

    df["score_cost"] = _safe_normalize(df, "cost_advantage_pct", higher_better=True)
    df["score_energy"] = _safe_normalize(df, "energy_mwh_standard", higher_better=True)
    df["score_grid"] = _safe_normalize(df, "grid_distance_km", higher_better=False)
    df["score_reservoir"] = _score_reservoir_suitability(df)
    df["score_regulatory"] = _score_regulatory_risk(df)

    df["composite_score"] = (
        df["score_cost"] * weights["cost_competitiveness"]
        + df["score_energy"] * weights["energy_potential"]
        + df["score_grid"] * weights["grid_proximity"]
        + df["score_reservoir"] * weights["reservoir_suitability"]
        + df["score_regulatory"] * weights["regulatory_risk"]
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


def _score_reservoir_suitability(df):
    scores = pd.Series(0.5, index=df.index)

    upper_cap = df.get("upper_capacity_mcm")
    lower_cap = df.get("lower_capacity_mcm")
    if upper_cap is not None and lower_cap is not None:
        min_cap = pd.concat([upper_cap, lower_cap], axis=1).min(axis=1)
        cap_score = _normalize_column(min_cap, higher_better=True)
        scores = cap_score

    num_sources = df.get("num_sources_upper", df.get("num_sources"))
    if num_sources is not None:
        source_bonus = (num_sources.fillna(1) - 1) * 0.1
        scores = scores + source_bonus.clip(0, 0.3)

    return scores.clip(0, 1)


def _score_regulatory_risk(df):
    scores = pd.Series(0.7, index=df.index)

    if "tier2_reasons" in df.columns:
        protected = df["tier2_reasons"].str.contains("protected", case=False, na=False)
        scores[protected] = 0.2

    if "terrain_difficulty" in df.columns:
        infeasible = df["terrain_difficulty"] == "infeasible"
        challenging = df["terrain_difficulty"] == "challenging"
        scores[infeasible] = 0.1
        scores[challenging] = scores[challenging] * 0.8

    return scores.clip(0, 1)


def run_sensitivity(pairs_df):
    config = load_config()
    sensitivity_configs = config.get("sensitivity", {})
    weight_variants = ["default", "cost_focused", "energy_focused"]

    results = {}

    for param_name, param_overrides in sensitivity_configs.items():
        log.info(f"Sensitivity run: {param_name} parameters")
        from ..screening.filters import apply_tier1_filters
        filtered = apply_tier1_filters(pairs_df, params={
            **get_screening_params(),
            **param_overrides,
        })
        viable = filtered[filtered["tier1_status"].isin(["pass", "borderline"])]
        results[f"params_{param_name}"] = {
            "viable_count": len(viable),
            "param_overrides": param_overrides,
        }

    for variant in weight_variants:
        try:
            scored = score_pairs(pairs_df, weight_variant=variant)
            top_10 = scored.head(10)[["rank", "upper_dam_name", "lower_dam_name", "composite_score"]].to_dict("records")
            results[f"weights_{variant}"] = {
                "top_10": top_10,
                "weight_variant": variant,
            }
        except Exception as e:
            log.warning(f"Sensitivity scoring with {variant} weights failed: {e}")

    return results
