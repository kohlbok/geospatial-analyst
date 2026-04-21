import logging

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.backends.backend_pdf as pdf_backend

from ..config import OUTPUT_DIR
from ..terrain.profiles import extract_terrain_profile

log = logging.getLogger(__name__)


def generate_siting_profiles(candidates, dams_df, top_n=15):
    sorted_candidates = sorted(
        candidates,
        key=lambda c: -(c.get("composite_score") or 0),
    )[:top_n]

    if not sorted_candidates:
        log.warning("No candidates to profile")
        return None

    dam_lookup = {}
    for _, dam in dams_df.iterrows():
        dam_lookup[dam.get("id", "")] = dam.to_dict()

    output_path = OUTPUT_DIR / "siting_profiles.pdf"
    with pdf_backend.PdfPages(str(output_path)) as pdf:
        for rank, cand in enumerate(sorted_candidates, 1):
            try:
                fig = _plot_candidate_profile(rank, cand, dam_lookup)
                pdf.savefig(fig, bbox_inches="tight")
                plt.close(fig)
            except Exception as e:
                log.warning(f"Failed to plot candidate {rank}: {e}")
                plt.close("all")

    log.info(f"Saved Phase 2 profiles to {output_path}")
    return output_path


def _plot_candidate_profile(rank, cand, dam_lookup):
    dam_id = cand.get("dam_id", "")
    dam = dam_lookup.get(dam_id, {})

    dam_lat = cand.get("dam_lat") or dam.get("lat")
    dam_lon = cand.get("dam_lon") or dam.get("lon")
    dam_elev = cand.get("dam_elevation_m") or dam.get("elevation_m") or dam.get("elevation_wall_m")
    c_lat = cand.get("centroid_lat")
    c_lon = cand.get("centroid_lon")
    c_elev = cand.get("optimal_fill_m")

    direction = cand.get("direction", "up")
    if direction == "up":
        upper_lat, upper_lon, upper_elev = c_lat, c_lon, c_elev
        lower_lat, lower_lon, lower_elev = dam_lat, dam_lon, dam_elev
        upper_label = "Candidate Site (Upper)"
        lower_label = f"{cand.get('dam_name', 'Existing Dam')} (Lower)"
    else:
        upper_lat, upper_lon, upper_elev = dam_lat, dam_lon, dam_elev
        lower_lat, lower_lon, lower_elev = c_lat, c_lon, c_elev
        upper_label = f"{cand.get('dam_name', 'Existing Dam')} (Upper)"
        lower_label = "Candidate Site (Lower)"

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle(
        f"#{rank} — {cand.get('dam_name', '')} | Head: {cand.get('head_m', 0):.0f}m | "
        f"CapEx/MWh: ${cand.get('capex_per_mwh_usd', 0):,.0f}",
        fontsize=12, fontweight="bold",
    )

    ax_profile = axes[0]

    if all(v is not None for v in [upper_lat, upper_lon, lower_lat, lower_lon, upper_elev, lower_elev]):
        try:
            profile = extract_terrain_profile(
                upper_lat, upper_lon, lower_lat, lower_lon, upper_elev, lower_elev
            )
            distances = profile.get("distances_km", [])
            elevations = profile.get("elevations_m", [])

            if distances and elevations:
                valid = [(d, e) for d, e in zip(distances, elevations) if e is not None]
                if valid:
                    ds, es = zip(*valid)
                    ax_profile.fill_between(ds, min(es) - 20, es, alpha=0.3, color="#8B6914", label="Terrain")
                    ax_profile.plot(ds, es, color="#5C4A1A", linewidth=1.5)

            ax_profile.axhline(y=upper_elev, color="#1a6bcc", linestyle="--", linewidth=1.5, label=upper_label)
            ax_profile.axhline(y=lower_elev, color="#16a34a", linestyle="--", linewidth=1.5, label=lower_label)

            if distances:
                ax_profile.axvline(x=0, color="#1a6bcc", linewidth=2, alpha=0.7)
                ax_profile.axvline(x=max(distances), color="#16a34a", linewidth=2, alpha=0.7)

        except Exception as e:
            log.debug(f"Profile extraction failed: {e}")
            ax_profile.text(0.5, 0.5, "Profile data unavailable", transform=ax_profile.transAxes,
                           ha="center", va="center", color="gray")

    ax_profile.set_xlabel("Distance (km)")
    ax_profile.set_ylabel("Elevation (m)")
    ax_profile.set_title("Terrain Profile")
    ax_profile.legend(loc="best", fontsize=8)
    ax_profile.grid(True, alpha=0.3)

    ax_stats = axes[1]
    ax_stats.axis("off")

    existing_cap = cand.get("existing_capacity_mcm")
    existing_cap_str = f"{existing_cap:.1f} MCM" if existing_cap is not None else "unknown"
    binding = cand.get("binding_reservoir", "candidate")

    stats_data = [
        ["Parameter", "Value"],
        ["Existing dam role", cand.get("existing_dam_role", "")],
        ["Existing dam capacity", existing_cap_str],
        ["Binding reservoir", binding],
        ["Data quality", cand.get("data_quality", "complete")],
        ["Head", f"{cand.get('head_m', 0):.0f} m"],
        ["Distance", f"{cand.get('distance_km', 0):.2f} km"],
        ["D/H Ratio", f"{cand.get('distance_head_ratio', 0):.2f}"],
        ["Usable volume", f"{cand.get('usable_volume_m3', 0):,.0f} m³"],
        ["Energy", f"{cand.get('energy_mwh', 0):,.0f} MWh"],
        ["Max discharge", f"{cand.get('max_discharge_hours', 0):.1f} h"],
        ["Energy at 3h", f"{cand.get('energy_mwh_3hr', 0):,.0f} MWh"],
        ["Energy at 8h", f"{cand.get('energy_mwh_8hr', 0):,.0f} MWh"],
        ["Penstock diam.", f"{cand.get('optimal_diameter_m', 0):.2f} m"],
        ["Friction", f"{cand.get('friction_pct', 0):.1f}%"],
        ["Saddle width", f"{cand.get('saddle_width_m', 0):.0f} m"],
        ["Total CapEx", f"${cand.get('total_capex_usd', 0)/1e6:,.1f}M"],
        ["CapEx/MWh", f"${cand.get('capex_per_mwh_usd', 0):,.0f}"],
        ["Battery ratio", f"{cand.get('battery_ratio', 0):.2f}x"],
        ["Abdelmoumen flag", "Yes" if cand.get("abdelmoumen_flag") else "No"],
        ["Beats battery", "Yes" if cand.get("passes_battery_test") else "No"],
    ]

    table = ax_stats.table(
        cellText=stats_data[1:],
        colLabels=stats_data[0],
        loc="center",
        cellLoc="left",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1.2, 1.4)

    for (row, col), cell in table.get_celld().items():
        if row == 0:
            cell.set_facecolor("#115E59")
            cell.set_text_props(color="white", fontweight="bold")
        elif row % 2 == 0:
            cell.set_facecolor("#F7F7F5")

    plt.tight_layout()
    return fig
