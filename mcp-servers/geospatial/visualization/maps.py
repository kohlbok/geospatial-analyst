import json
import logging

import pandas as pd
import folium
from folium.plugins import MarkerCluster
import branca.colormap as cm

from ..config import OUTPUT_MAPS, load_config

log = logging.getLogger(__name__)


def generate_dam_registry_map(dam_registry, pairs_df=None):
    center_lat = dam_registry["lat"].mean()
    center_lon = dam_registry["lon"].mean()

    m = folium.Map(location=[center_lat, center_lon], zoom_start=6, tiles="OpenStreetMap")

    cluster = MarkerCluster(name="Dams")

    viable_dam_ids = set()
    borderline_dam_ids = set()
    if pairs_df is not None:
        viable = pairs_df[pairs_df.get("tier2_status", pairs_df.get("tier1_status", "")) == "pass"]
        borderline = pairs_df[pairs_df.get("tier2_status", pairs_df.get("tier1_status", "")) == "borderline"]
        for _, p in viable.iterrows():
            viable_dam_ids.add(p.get("upper_dam_id"))
            viable_dam_ids.add(p.get("lower_dam_id"))
        for _, p in borderline.iterrows():
            borderline_dam_ids.add(p.get("upper_dam_id"))
            borderline_dam_ids.add(p.get("lower_dam_id"))

    for _, dam in dam_registry.iterrows():
        if dam.get("lat") is None:
            continue

        dam_id = dam.get("id", "")
        if dam_id in viable_dam_ids:
            color = "green"
        elif dam_id in borderline_dam_ids:
            color = "orange"
        else:
            color = "red"

        popup_html = _dam_popup(dam)
        folium.CircleMarker(
            location=[dam["lat"], dam["lon"]],
            radius=6,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.7,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=dam.get("name", "Unknown"),
        ).add_to(cluster)

    cluster.add_to(m)

    _add_legend(m, {
        "Viable pair member": "green",
        "Borderline": "orange",
        "No viable pairs": "red",
    })

    output_path = OUTPUT_MAPS / "morocco_overview.html"
    m.save(str(output_path))
    log.info(f"Saved overview map to {output_path}")
    return str(output_path)


def generate_pairs_map(dam_registry, scored_pairs_df):
    config = load_config()
    top_n = config["output"]["top_n_detailed"]

    center_lat = dam_registry["lat"].mean()
    center_lon = dam_registry["lon"].mean()
    m = folium.Map(location=[center_lat, center_lon], zoom_start=6, tiles="OpenStreetMap")

    if len(scored_pairs_df) == 0:
        output_path = OUTPUT_MAPS / "top_pairs.html"
        m.save(str(output_path))
        return str(output_path)

    valid_scores = scored_pairs_df["composite_score"].dropna()
    if len(valid_scores) == 0:
        max_score = 1.0
        min_score = 0.0
    else:
        max_score = valid_scores.max()
        min_score = valid_scores.min()
    if max_score == min_score:
        max_score = min_score + 0.01

    colormap = cm.LinearColormap(
        colors=["red", "orange", "green"],
        vmin=min_score,
        vmax=max_score,
        caption="Composite Score",
    )
    colormap.add_to(m)

    dam_layer = folium.FeatureGroup(name="Dams")
    pair_layer = folium.FeatureGroup(name="All Pairs")
    top_layer = folium.FeatureGroup(name=f"Top {top_n} Pairs")

    dam_ids_in_pairs = set()
    for _, pair in scored_pairs_df.iterrows():
        dam_ids_in_pairs.add(pair.get("upper_dam_id"))
        dam_ids_in_pairs.add(pair.get("lower_dam_id"))

    for _, dam in dam_registry.iterrows():
        if dam.get("id") not in dam_ids_in_pairs:
            continue
        if dam.get("lat") is None:
            continue
        folium.CircleMarker(
            location=[dam["lat"], dam["lon"]],
            radius=5,
            color="blue",
            fill=True,
            fill_opacity=0.7,
            popup=folium.Popup(_dam_popup(dam), max_width=300),
            tooltip=dam.get("name", ""),
        ).add_to(dam_layer)

    for _, pair in scored_pairs_df.iterrows():
        score = pair.get("composite_score", 0)
        if score is None or (isinstance(score, float) and pd.isna(score)):
            score = min_score
        rank = pair.get("rank", 999)
        color = colormap(score)

        line = folium.PolyLine(
            locations=[
                [pair["upper_lat"], pair["upper_lon"]],
                [pair["lower_lat"], pair["lower_lon"]],
            ],
            color=color,
            weight=3 if rank <= top_n else 1,
            opacity=0.8 if rank <= top_n else 0.4,
            popup=folium.Popup(_pair_popup(pair), max_width=350),
            tooltip=f"#{rank}: {pair.get('upper_dam_name', '')} - {pair.get('lower_dam_name', '')}",
        )

        if rank <= top_n:
            line.add_to(top_layer)

            for loc, name in [
                ([pair["upper_lat"], pair["upper_lon"]], pair.get("upper_dam_name", "")),
                ([pair["lower_lat"], pair["lower_lon"]], pair.get("lower_dam_name", "")),
            ]:
                folium.Marker(
                    location=loc,
                    icon=folium.DivIcon(
                        html=f'<div style="font-size:10px;color:green;font-weight:bold">#{rank}</div>'
                    ),
                ).add_to(top_layer)
        else:
            line.add_to(pair_layer)

    dam_layer.add_to(m)
    pair_layer.add_to(m)
    top_layer.add_to(m)
    folium.LayerControl().add_to(m)

    output_path = OUTPUT_MAPS / "top_pairs.html"
    m.save(str(output_path))
    log.info(f"Saved pairs map to {output_path}")
    return str(output_path)


def generate_top_pairs_detail_map(scored_pairs_df, dam_registry):
    config = load_config()
    top_n = config["output"]["top_n_detailed"]
    top = scored_pairs_df.head(top_n)

    if len(top) == 0:
        return None

    center_lat = (top["upper_lat"].mean() + top["lower_lat"].mean()) / 2
    center_lon = (top["upper_lon"].mean() + top["lower_lon"].mean()) / 2
    m = folium.Map(location=[center_lat, center_lon], zoom_start=7, tiles="OpenStreetMap")

    for _, pair in top.iterrows():
        rank = pair.get("rank", "")
        color = "green" if pair.get("composite_score", 0) > 0.7 else "orange"

        folium.PolyLine(
            locations=[
                [pair["upper_lat"], pair["upper_lon"]],
                [pair["lower_lat"], pair["lower_lon"]],
            ],
            color=color,
            weight=4,
            opacity=0.9,
            popup=folium.Popup(_pair_popup(pair), max_width=350),
        ).add_to(m)

        for loc, name, role in [
            ([pair["upper_lat"], pair["upper_lon"]], pair.get("upper_dam_name", ""), "Upper"),
            ([pair["lower_lat"], pair["lower_lon"]], pair.get("lower_dam_name", ""), "Lower"),
        ]:
            folium.Marker(
                location=loc,
                popup=f"#{rank} {role}: {name}",
                icon=folium.Icon(color="green" if role == "Upper" else "blue", icon="tint"),
            ).add_to(m)

    output_path = OUTPUT_MAPS / "top_pairs_detail.html"
    m.save(str(output_path))
    log.info(f"Saved top pairs detail map to {output_path}")
    return str(output_path)


def _dam_popup(dam):
    fields = [
        ("ID", dam.get("id", "")),
        ("Name", dam.get("name", "")),
        ("Elevation", f"{dam.get('elevation_wall_m', 'N/A')}m"),
        ("Height", f"{dam.get('height_m', 'N/A')}m"),
        ("Capacity", f"{dam.get('capacity_mcm', 'N/A')} MCM"),
        ("Area", f"{dam.get('surface_area_km2', 'N/A')} km2"),
        ("Year", dam.get("year_built", "N/A")),
        ("Sources", ", ".join(dam["sources"]) if isinstance(dam.get("sources"), list) else dam.get("sources", "")),
    ]
    rows = "".join(f"<tr><td><b>{k}</b></td><td>{v}</td></tr>" for k, v in fields if v and v != "N/A")
    return f"<table>{rows}</table>"


def _pair_popup(pair):
    fields = [
        ("Rank", pair.get("rank", "")),
        ("Upper Dam", pair.get("upper_dam_name", "")),
        ("Lower Dam", pair.get("lower_dam_name", "")),
        ("Head", f"{pair.get('head_m', 'N/A')}m"),
        ("Distance", f"{pair.get('distance_km', 'N/A')} km"),
        ("Energy (std)", f"{pair.get('energy_mwh_standard', 'N/A')} MWh"),
        ("Power (8hr)", f"{pair.get('power_mw_8hr', 'N/A')} MW"),
        ("Score", f"{pair.get('composite_score', 'N/A'):.3f}" if pair.get("composite_score") else "N/A"),
        ("Terrain", pair.get("terrain_difficulty", "N/A")),
        ("Cost Adv.", f"{pair.get('cost_advantage_pct', 'N/A')}%"),
    ]
    rows = "".join(f"<tr><td><b>{k}</b></td><td>{v}</td></tr>" for k, v in fields)
    return f"<table>{rows}</table>"


def _add_legend(m, items):
    legend_html = '<div style="position:fixed;bottom:50px;left:50px;z-index:1000;background:white;padding:10px;border:2px solid grey;border-radius:5px">'
    legend_html += "<h4>Legend</h4>"
    for label, color in items.items():
        legend_html += f'<p><span style="color:{color}">&#9679;</span> {label}</p>'
    legend_html += "</div>"
    m.get_root().html.add_child(folium.Element(legend_html))
