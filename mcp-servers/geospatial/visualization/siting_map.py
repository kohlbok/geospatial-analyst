import logging
import math

import folium
import pandas as pd

from ..config import OUTPUT_DIR

log = logging.getLogger(__name__)

STATUS_COLORS = {
    "phase1_pair": "#1a6bcc",
    "has_candidate": "#16a34a",
    "killed_tier1": "#6b7280",
    "killed_scan": "#ea580c",
}


def generate_siting_map(dams_df, tier1_results, candidates, phase1_dam_ids, dam_scan_kills=None):
    center_lat = dams_df["lat"].dropna().mean()
    center_lon = dams_df["lon"].dropna().mean()

    m = folium.Map(location=[center_lat, center_lon], zoom_start=6, tiles=None)

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri", name="Satellite",
    ).add_to(m)
    folium.TileLayer(
        tiles="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        attr='&copy; OpenStreetMap &copy; CARTO',
        name="Street Map",
        subdomains="abcd",
    ).add_to(m)

    tier1_survivor_ids = {r["dam_id"] for r in tier1_results if r.get("viable_up") or r.get("viable_down")}
    candidate_dam_ids = {c["dam_id"] for c in candidates}
    t1_by_id = {r["dam_id"]: r for r in tier1_results}
    scan_kills = dam_scan_kills or {}

    def _dam_status(dam_id):
        if dam_id in phase1_dam_ids:
            return "phase1_pair"
        if dam_id in candidate_dam_ids:
            return "has_candidate"
        if dam_id in tier1_survivor_ids:
            return "killed_scan"
        return "killed_tier1"

    status_labels = {
        "phase1_pair": "Phase 1 Pair",
        "has_candidate": "Has Phase 2 Candidate",
        "killed_tier1": "Killed Tier 1 (flat / ratio)",
        "killed_scan": "Killed in scan (no viable basin)",
    }

    layers = {k: folium.FeatureGroup(name=status_labels[k]) for k in STATUS_COLORS}

    for _, dam in dams_df.iterrows():
        lat, lon = dam.get("lat"), dam.get("lon")
        if lat is None or pd.isna(lat) or pd.isna(lon):
            continue

        dam_id = dam.get("id", "")
        status = _dam_status(dam_id)
        color = STATUS_COLORS[status]

        kill_line = ""
        if status == "killed_tier1":
            from geospatial.visualization.siting_export import _t1_closest_attempt
            t1 = t1_by_id.get(dam_id, {})
            detail = _t1_closest_attempt(t1)
            if detail:
                kill_line = f"<br><span style='color:#6b7280'>Kill: {detail}</span>"
        elif status == "killed_scan":
            detail = scan_kills.get(dam_id, "")
            if detail:
                kill_line = f"<br><span style='color:#ea580c'>Kill: {detail}</span>"
        popup_html = (
            f"<b>{dam.get('name', '')}</b><br>"
            f"Elevation: {dam.get('elevation_m', dam.get('elevation_wall_m', 'N/A'))}m<br>"
            f"Status: {status_labels[status]}"
            f"{kill_line}"
        )

        folium.CircleMarker(
            location=[lat, lon],
            radius=6,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.8,
            popup=folium.Popup(popup_html, max_width=280),
            tooltip=f"{dam.get('name', '')} [{status_labels[status]}]",
        ).add_to(layers[status])

    for layer in layers.values():
        layer.add_to(m)

    candidate_layer = folium.FeatureGroup(name="Phase 2 Candidates")
    for rank, cand in enumerate(candidates, start=1):
        c_lat = cand.get("centroid_lat")
        c_lon = cand.get("centroid_lon")
        dam_lat = cand.get("dam_lat")
        dam_lon = cand.get("dam_lon")

        if c_lat is None or c_lon is None:
            continue

        capex_per_mwh = cand.get("capex_per_mwh_usd", 0) or 0
        passes = cand.get("passes_battery_test", False)
        marker_color = "#16a34a" if passes else "#f59e0b"
        score = cand.get("composite_score", 0) or 0
        footprint_area_m2 = cand.get("optimal_footprint_area_m2") or 0
        reservoir_radius_m = math.sqrt(footprint_area_m2 / math.pi) if footprint_area_m2 > 0 else 0

        dq = cand.get("data_quality", "complete")
        dq_label = "" if dq == "complete" else "<br><span style='color:#D97706;font-size:11px'>⚠ Partial data — existing dam capacity unknown</span><br>"
        existing_cap = cand.get("existing_capacity_mcm")
        binding = cand.get("binding_reservoir", "candidate")
        existing_cap_line = (
            f"Existing dam capacity: {existing_cap:.1f} MCM (binding: {binding})<br>"
            if existing_cap is not None else
            "Existing dam capacity: unknown (assumed >= candidate)<br>"
        )

        capped_note = (
            "<span style='color:#7c3aed;font-size:11px'>⬆ Basin capped — site may have higher potential</span><br>"
            if cand.get("basin_capped") else ""
        )
        popup_html = (
            f"<b>#{rank} — {cand.get('dam_name', '')}</b><br>"
            f"{dq_label}"
            f"{capped_note}"
            f"Score: {score:.3f}<br>"
            f"Role: Existing dam = {cand.get('existing_dam_role', '')}<br>"
            f"Head: {cand.get('head_m', 0):.0f}m | Distance: {cand.get('distance_km', 0):.1f}km<br>"
            f"Usable volume: {cand.get('usable_volume_mcm', 0):.2f} MCM<br>"
            f"{existing_cap_line}"
            f"Energy: {cand.get('energy_mwh', 0):,.0f} MWh<br>"
            f"CapEx/MWh: ${capex_per_mwh:,.0f} (battery: $100,000)<br>"
            f"Reservoir footprint: {footprint_area_m2:,.0f} m² (~{2 * reservoir_radius_m:.0f}m diameter)<br>"
            f"Saddle width: {cand.get('saddle_width_m', 0):.0f}m<br>"
            f"Grid distance: {cand.get('grid_distance_km', 'N/A')} km"
        )
        tooltip = f"#{rank} {cand.get('dam_name', '')} | Score: {score:.3f} | ${capex_per_mwh:,.0f}/MWh"

        polygon = cand.get("footprint_polygon")
        if polygon and len(polygon) >= 3:
            folium.Polygon(
                locations=polygon,
                color=marker_color,
                fill=True,
                fill_color=marker_color,
                fill_opacity=0.45,
                weight=2,
                popup=folium.Popup(popup_html, max_width=320),
                tooltip=tooltip,
            ).add_to(candidate_layer)
        elif reservoir_radius_m > 0:
            folium.Circle(
                location=[c_lat, c_lon],
                radius=reservoir_radius_m,
                color=marker_color,
                fill=True,
                fill_color=marker_color,
                fill_opacity=0.45,
                weight=2,
                popup=folium.Popup(popup_html, max_width=320),
                tooltip=tooltip,
            ).add_to(candidate_layer)

        if dam_lat is not None and dam_lon is not None:
            folium.PolyLine(
                locations=[[dam_lat, dam_lon], [c_lat, c_lon]],
                color=marker_color,
                weight=2,
                opacity=0.7,
                dash_array="6 4",
            ).add_to(candidate_layer)

        folium.CircleMarker(
            location=[c_lat, c_lon],
            radius=9,
            color=marker_color,
            fill=True,
            fill_color=marker_color,
            fill_opacity=0.9,
            popup=folium.Popup(popup_html, max_width=320),
            tooltip=tooltip,
        ).add_to(candidate_layer)

        if rank <= 20:
            folium.Marker(
                location=[c_lat, c_lon],
                icon=folium.DivIcon(
                    html=f'<div style="font-size:10px;font-weight:bold;color:white;pointer-events:none;'
                         f'background:{marker_color};border-radius:50%;width:18px;height:18px;'
                         f'display:flex;align-items:center;justify-content:center;'
                         f'margin-left:-9px;margin-top:-9px">{rank}</div>',
                    icon_size=(18, 18),
                    icon_anchor=(9, 9),
                ),
            ).add_to(candidate_layer)

    candidate_layer.add_to(m)

    legend_html = _build_legend()
    m.get_root().html.add_child(folium.Element(legend_html))

    folium.LayerControl().add_to(m)

    output_path = OUTPUT_DIR / "siting_map.html"
    m.save(str(output_path))
    log.info(f"Saved siting map to {output_path}")
    return output_path


def _build_legend():
    items = [
        ("#1a6bcc", "Existing dam — paired in Phase 1"),
        ("#16a34a", "Existing dam — has Phase 2 candidate"),
        ("#6b7280", "Existing dam — killed at Tier 1"),
        ("#ea580c", "Existing dam — scanned, no viable basin"),
        ("#16a34a", "Phase 2 candidate — beats battery"),
        ("#f59e0b", "Phase 2 candidate — marginal cost"),
    ]
    rows = "".join(
        f'<p style="margin:2px 0"><span style="color:{color}">&#9679;</span> {label}</p>'
        for color, label in items
    )
    return (
        '<div style="position:fixed;bottom:50px;left:50px;z-index:1000;background:white;'
        'padding:10px;border:2px solid grey;border-radius:5px;font-family:sans-serif">'
        f'{rows}</div>'
    )
