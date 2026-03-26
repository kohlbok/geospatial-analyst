import logging

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from ..config import OUTPUT_REPORTS

log = logging.getLogger(__name__)


def generate_terrain_profile_chart(pair, profile_data):
    if profile_data is None:
        return None

    distances = profile_data.get("distances_km", [])
    elevations = profile_data.get("elevations_m", [])

    if not distances or not elevations:
        return None

    valid_mask = [e is not None for e in elevations]
    plot_dist = [d for d, v in zip(distances, valid_mask) if v]
    plot_elev = [e for e, v in zip(elevations, valid_mask) if v]

    if not plot_dist:
        return None

    fig, ax = plt.subplots(figsize=(12, 5))

    ax.fill_between(plot_dist, plot_elev, alpha=0.3, color="saddlebrown")
    ax.plot(plot_dist, plot_elev, color="saddlebrown", linewidth=1.5)

    upper_elev = pair.get("upper_elevation_m")
    lower_elev = pair.get("lower_elevation_m")
    if upper_elev and lower_elev:
        ax.plot(
            [plot_dist[0], plot_dist[-1]],
            [upper_elev, lower_elev],
            color="blue",
            linewidth=2,
            linestyle="--",
            label="Direct line",
        )

        head = abs(upper_elev - lower_elev)
        mid_dist = (plot_dist[0] + plot_dist[-1]) / 2
        mid_elev = (upper_elev + lower_elev) / 2
        ax.annotate(
            f"Head: {head}m",
            xy=(mid_dist, mid_elev),
            fontsize=10,
            fontweight="bold",
            color="blue",
            ha="center",
        )

    for ridge in profile_data.get("ridges", []):
        ax.axvspan(
            ridge["start_km"], ridge["end_km"],
            alpha=0.2, color="red", label="Ridge" if ridge == profile_data["ridges"][0] else None,
        )

    for obs in profile_data.get("obstacles", []):
        dist = obs.get("distance_km", 0)
        ax.axvline(dist, color="orange", linewidth=1, linestyle=":", alpha=0.7)
        ax.annotate(
            obs.get("type", "obstacle"),
            xy=(dist, max(plot_elev) * 0.95),
            fontsize=7,
            rotation=45,
            color="orange",
        )

    upper_name = pair.get("upper_dam_name", "Upper")
    lower_name = pair.get("lower_dam_name", "Lower")
    rank = pair.get("rank", "")

    ax.set_title(
        f"Terrain Profile: {upper_name} to {lower_name} (Rank #{rank})",
        fontsize=14,
        fontweight="bold",
    )
    ax.set_xlabel("Distance (km)")
    ax.set_ylabel("Elevation (m)")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)

    info_text = (
        f"Distance: {pair.get('distance_km', 'N/A')} km | "
        f"Head: {pair.get('head_m', 'N/A')} m | "
        f"Difficulty: {pair.get('terrain_difficulty', 'N/A')} | "
        f"Tunnel: {pair.get('tunnel_length_km', 0)} km"
    )
    ax.text(0.5, -0.12, info_text, transform=ax.transAxes, ha="center", fontsize=9, style="italic")

    plt.tight_layout()

    filename = f"terrain_profile_{pair.get('upper_dam_id', 'x')}_{pair.get('lower_dam_id', 'y')}.png"
    output_path = OUTPUT_REPORTS / filename
    fig.savefig(str(output_path), dpi=150, bbox_inches="tight")
    plt.close(fig)

    log.info(f"Saved terrain profile: {output_path}")
    return str(output_path)


def generate_all_terrain_charts(scored_pairs_df, max_charts=20):
    top = scored_pairs_df.head(max_charts)
    paths = []

    for _, pair in top.iterrows():
        profile = pair.get("terrain_profile")
        if profile is None:
            continue
        path = generate_terrain_profile_chart(pair, profile)
        if path:
            paths.append(path)

    log.info(f"Generated {len(paths)} terrain profile charts")
    return paths
