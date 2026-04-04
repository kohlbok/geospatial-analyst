import logging

import pandas as pd
import folium
from folium.plugins import MarkerCluster, Search
import branca.colormap as cm

from ..config import OUTPUT_DIR, DATA_DIR, load_config

log = logging.getLogger(__name__)


def generate_combined_map(dam_registry, scored_pairs_df=None):
    center_lat = dam_registry["lat"].dropna().mean()
    center_lon = dam_registry["lon"].dropna().mean()

    m = folium.Map(location=[center_lat, center_lon], zoom_start=6, tiles=None)

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri", name="Satellite",
    ).add_to(m)
    folium.TileLayer(
        tiles="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>',
        name="Street Map",
        subdomains="abcd",
    ).add_to(m)

    pair_dam_ids = set()
    if scored_pairs_df is not None and len(scored_pairs_df) > 0:
        for _, p in scored_pairs_df.iterrows():
            pair_dam_ids.add(p.get("upper_dam_id"))
            pair_dam_ids.add(p.get("lower_dam_id"))

    dam_layer = folium.FeatureGroup(name="All Dams")
    for _, dam in dam_registry.iterrows():
        lat, lon = dam.get("lat"), dam.get("lon")
        if lat is None or pd.isna(lat) or pd.isna(lon):
            continue

        in_pair = dam.get("id", "") in pair_dam_ids
        color = "green" if in_pair else "gray"
        radius = 8 if in_pair else 5

        popup_html = _dam_popup(dam)
        folium.CircleMarker(
            location=[lat, lon],
            radius=radius,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.7,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"{dam.get('name', '')} ({dam.get('elevation_m', '?')}m, {dam.get('capacity_mcm', '?')} MCM)",
        ).add_to(dam_layer)
    dam_layer.add_to(m)

    if scored_pairs_df is not None and len(scored_pairs_df) > 0:
        scores = scored_pairs_df["composite_score"].dropna()
        min_score = scores.min() if len(scores) > 0 else 0
        max_score = scores.max() if len(scores) > 0 else 1
        if max_score == min_score:
            max_score = min_score + 0.01

        colormap = cm.LinearColormap(
            colors=["#ff4444", "#ffaa00", "#44bb44"],
            vmin=min_score, vmax=max_score,
            caption="PSH Viability Score",
        )
        colormap.add_to(m)

        top_layer = folium.FeatureGroup(name="Top 10 Pairs")
        other_layer = folium.FeatureGroup(name="Other Viable Pairs")

        for _, pair in scored_pairs_df.iterrows():
            score = pair.get("composite_score", 0)
            if pd.isna(score):
                continue
            rank = int(pair.get("rank", 999))
            color = colormap(score)
            is_top = rank <= 10

            line = folium.PolyLine(
                locations=[
                    [pair["upper_lat"], pair["upper_lon"]],
                    [pair["lower_lat"], pair["lower_lon"]],
                ],
                color=color,
                weight=5 if is_top else 2,
                opacity=0.9 if is_top else 0.4,
                popup=folium.Popup(_pair_popup(pair), max_width=350),
                tooltip=f"#{rank}: {pair.get('upper_dam_name', '')} - {pair.get('lower_dam_name', '')} (score: {score:.2f})",
            )

            if is_top:
                line.add_to(top_layer)
                for loc, name, role in [
                    ([pair["upper_lat"], pair["upper_lon"]], pair.get("upper_dam_name", ""), "Upper"),
                    ([pair["lower_lat"], pair["lower_lon"]], pair.get("lower_dam_name", ""), "Lower"),
                ]:
                    folium.Marker(
                        location=loc,
                        popup=f"#{rank} {role}: {name}",
                        icon=folium.Icon(
                            color="green" if role == "Upper" else "blue",
                            icon="arrow-up" if role == "Upper" else "arrow-down",
                            prefix="fa",
                        ),
                    ).add_to(top_layer)
            else:
                line.add_to(other_layer)

        other_layer.add_to(m)
        top_layer.add_to(m)

    folium.LayerControl().add_to(m)

    output_path = OUTPUT_DIR / "map.html"
    m.save(str(output_path))
    log.info(f"Saved combined map to {output_path}")
    return str(output_path)


def _dam_popup(dam):
    fields = [
        ("Name", dam.get("name", "")),
        ("Elevation", f"{dam.get('elevation_m', dam.get('elevation_wall_m', 'N/A'))}m"),
        ("Height", f"{dam.get('height_m', 'N/A')}m"),
        ("Capacity", f"{dam.get('capacity_mcm', 'N/A')} MCM"),
        ("Year", dam.get("year_built", "N/A")),
        ("River", dam.get("river", "N/A")),
    ]
    rows = "".join(f"<tr><td><b>{k}</b></td><td>{v}</td></tr>" for k, v in fields if str(v) not in ("N/A", "None", "nan", ""))
    return f"<table style='font-size:12px'>{rows}</table>"


def _pair_popup(pair):
    fields = [
        ("Rank", f"#{int(pair.get('rank', 0))}"),
        ("Upper Dam", pair.get("upper_dam_name", "")),
        ("Lower Dam", pair.get("lower_dam_name", "")),
        ("Head", f"{pair.get('head_m', 0):.0f}m"),
        ("Distance", f"{pair.get('distance_km', 0):.1f} km"),
        ("Energy", f"{pair.get('energy_mwh_standard', 0):,.0f} MWh"),
        ("Score", f"{pair.get('composite_score', 0):.3f}"),
    ]
    rows = "".join(f"<tr><td><b>{k}</b></td><td>{v}</td></tr>" for k, v in fields)
    return f"<table style='font-size:12px'>{rows}</table>"


def generate_overview_map(dam_registry):
    config = load_config()
    status_colors = config.get("overview_map", {}).get("status_colors", {})
    default_color = status_colors.get("unknown", "#666666")

    center_lat = dam_registry["lat"].dropna().mean()
    center_lon = dam_registry["lon"].dropna().mean()

    m = folium.Map(location=[center_lat, center_lon], zoom_start=6, tiles=None)

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri", name="Satellite",
    ).add_to(m)
    folium.TileLayer(
        tiles="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>',
        name="Street Map", subdomains="abcd",
    ).add_to(m)
    folium.TileLayer(
        tiles="https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png",
        attr="CARTO", name="Labels", subdomains="abcd", overlay=True,
    ).add_to(m)

    def _normalize_status(s):
        if not s or pd.isna(s):
            return "unknown"
        return str(s).strip().lower().replace(" ", "_")

    dam_registry = dam_registry.copy()
    dam_registry["_status_key"] = dam_registry.get("status", pd.Series(dtype=str)).apply(_normalize_status)

    present_statuses = sorted(dam_registry["_status_key"].unique())
    layers = {}
    for status_key in present_statuses:
        label = status_key.replace("_", " ").title()
        layers[status_key] = folium.FeatureGroup(name=label)

    search_layer = folium.FeatureGroup(name="__search", show=False)
    search_features = []

    for _, dam in dam_registry.iterrows():
        lat, lon = dam.get("lat"), dam.get("lon")
        if lat is None or pd.isna(lat) or pd.isna(lon):
            continue

        status_key = dam["_status_key"]
        color = status_colors.get(status_key, default_color)

        popup_html = _overview_popup(dam)
        name = dam.get("name", "")
        dam_id = dam.get("id", "")
        tooltip = f"{name} ({dam_id})" if dam_id else name

        folium.CircleMarker(
            location=[lat, lon], radius=7,
            color=color, fill=True, fill_color=color, fill_opacity=0.7,
            popup=folium.Popup(popup_html, max_width=320),
            tooltip=tooltip,
        ).add_to(layers[status_key])

        search_features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {"name": name, "id": dam_id},
        })

    for layer in layers.values():
        layer.add_to(m)

    if search_features:
        geojson = folium.GeoJson(
            {"type": "FeatureCollection", "features": search_features},
            name="__search", show=False,
            style_function=lambda _: {"opacity": 0, "fillOpacity": 0},
        )
        geojson.add_to(search_layer)
        search_layer.add_to(m)
        Search(layer=geojson, search_label="name", placeholder="Search dams...", collapsed=False).add_to(m)

    legend_items = "".join(
        f'<p><span style="color:{status_colors.get(s, default_color)}">&#9679;</span> {s.replace("_", " ").title()}</p>'
        for s in present_statuses if s != "unknown"
    )
    legend_html = (
        '<div style="position:fixed;bottom:50px;left:50px;z-index:1000;background:white;'
        'padding:10px;border:2px solid grey;border-radius:5px">'
        f'<h4>Legend</h4>{legend_items}</div>'
    )
    m.get_root().html.add_child(folium.Element(legend_html))

    folium.LayerControl().add_to(m)

    output_path = DATA_DIR / "overview.html"
    m.save(str(output_path))
    log.info(f"Saved overview map to {output_path}")
    return str(output_path)


def _overview_popup(dam):
    lat, lon = dam.get("lat", ""), dam.get("lon", "")
    sat_link = f'<a href="https://www.google.com/maps/@{lat},{lon},15z/data=!3m1!1e3" target="_blank">View satellite</a>' if lat and lon else ""

    sources = dam.get("sources", "")
    if isinstance(sources, list):
        sources = ", ".join(str(s) for s in sources)

    fields = [
        ("ID", dam.get("id", "")),
        ("Name", dam.get("name", "")),
        ("Status", dam.get("status", "")),
        ("Elevation", f"{dam.get('elevation_m', dam.get('elevation_wall_m', 'N/A'))}m"),
        ("Height", f"{dam.get('height_m', 'N/A')}m"),
        ("Capacity", f"{dam.get('capacity_mcm', 'N/A')} MCM"),
        ("Area", f"{dam.get('surface_area_km2', 'N/A')} km2"),
        ("Year", dam.get("year_built", "N/A")),
        ("Sources", sources),
        ("Location", sat_link),
    ]
    rows = "".join(f"<tr><td><b>{k}</b></td><td>{v}</td></tr>" for k, v in fields if str(v) not in ("N/A", "None", "nan", "", "N/Am", "N/A km2"))
    return f"<table style='font-size:12px'>{rows}</table>"
