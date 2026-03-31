import json
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
import simplekml
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from ..config import OUTPUT_DIR, load_config

log = logging.getLogger(__name__)

FONT = "Calibri"
ACCENT_DARK = "1E3A5F"
ACCENT = "2563EB"
GREEN = "059669"
AMBER = "D97706"
RED = "DC2626"
TEXT = "1A1A1A"
MUTED = "6B7280"
STRIPE = "F0F4FA"
WHITE = "FFFFFF"
BORDER_COLOR = "DAE0E8"

HEADER_FONT = Font(name=FONT, bold=True, color=WHITE, size=10)
HEADER_FILL = PatternFill(start_color=ACCENT_DARK, end_color=ACCENT_DARK, fill_type="solid")
HEADER_BORDER = Border(bottom=Side(style="medium", color=ACCENT))
BODY_FONT = Font(name=FONT, size=10, color=TEXT)
BODY_BORDER = Border(bottom=Side(style="hair", color=BORDER_COLOR))
STRIPE_FILL = PatternFill(start_color=STRIPE, end_color=STRIPE, fill_type="solid")
WHITE_FILL = PatternFill(start_color=WHITE, end_color=WHITE, fill_type="solid")

TITLE_FONT = Font(name=FONT, bold=True, size=18, color=ACCENT_DARK)
SUBTITLE_FONT = Font(name=FONT, size=11, color=MUTED)
SECTION_FONT = Font(name=FONT, bold=True, size=11, color=ACCENT_DARK)
LABEL_FONT = Font(name=FONT, size=10, color=MUTED)
VALUE_FONT = Font(name=FONT, bold=True, size=10, color=TEXT)
STAT_VALUE_FONT = Font(name=FONT, bold=True, size=22, color=ACCENT_DARK)
STAT_LABEL_FONT = Font(name=FONT, size=9, color=MUTED)

DAM_COLUMNS = [
    ("id", "ID", 14, "left"),
    ("name", "Dam Name", 32, "left"),
    ("lat", "Latitude", 12, "right"),
    ("lon", "Longitude", 12, "right"),
    ("elevation_m", "Elevation (m)", 15, "right"),
    ("height_m", "Height (m)", 13, "right"),
    ("capacity_mcm", "Capacity (MCM)", 16, "right"),
    ("surface_area_km2", "Area (km\u00b2)", 13, "right"),
    ("year_built", "Year Built", 12, "center"),
    ("river", "River", 22, "left"),
    ("grid_distance_km", "Grid Distance (km)", 18, "right"),
    ("nearest_substation", "Nearest Substation", 36, "left"),
]

PAIR_COLUMNS = [
    ("rank", "Rank", 8, "center"),
    ("upper_dam_name", "Upper Dam", 28, "left"),
    ("lower_dam_name", "Lower Dam", 34, "left"),
    ("head_m", "Head (m)", 12, "right"),
    ("distance_km", "Distance (km)", 14, "right"),
    ("distance_head_ratio", "Dist/Head Ratio", 15, "right"),
    ("energy_mwh_standard", "Energy (MWh)", 15, "right"),
    ("composite_score", "Score", 10, "center"),
    ("psh_cost_usd_per_mwh", "PSH Cost ($/MWh)", 17, "right"),
    ("cost_advantage_pct", "Cost Advantage", 15, "right"),
    ("lcoe_eur_per_mwh", "LCOE (EUR/MWh)", 16, "right"),
    ("tunneling_cost_eur", "Tunneling (EUR)", 17, "right"),
    ("grid_connection_cost_eur", "Grid Connect (EUR)", 17, "right"),
    ("grid_distance_km", "Grid Distance (km)", 17, "right"),
    ("upper_capacity_mcm", "Upper Capacity (MCM)", 19, "right"),
    ("lower_capacity_mcm", "Lower Capacity (MCM)", 19, "right"),
]

NUMBER_FORMATS = {
    "lat": "0.000",
    "lon": "0.000",
    "elevation_m": "#,##0",
    "height_m": "0.0",
    "capacity_mcm": "#,##0",
    "surface_area_km2": "0.0",
    "year_built": "0",
    "grid_distance_km": "0.0",
    "head_m": "#,##0",
    "distance_km": "0.0",
    "distance_head_ratio": "0.0",
    "energy_mwh_standard": "#,##0",
    "composite_score": "0.000",
    "psh_cost_usd_per_mwh": "$#,##0",
    "cost_advantage_pct": "0.0%",
    "lcoe_eur_per_mwh": "#,##0",
    "tunneling_cost_eur": "#,##0",
    "grid_connection_cost_eur": "#,##0",
    "upper_capacity_mcm": "#,##0",
    "lower_capacity_mcm": "#,##0",
    "rank": "0",
}


def generate_clean_outputs(dam_registry, scored_pairs):
    paths = {}
    paths["excel"] = _export_excel(dam_registry, scored_pairs)
    paths["json"] = _export_json(dam_registry, scored_pairs)
    paths["kml_3d"] = _export_3d_kml(dam_registry, scored_pairs)
    paths["geojson"] = _export_geojson(dam_registry, scored_pairs)
    log.info(f"Generated all outputs: {list(paths.keys())}")
    return paths


def _style_data_sheet(ws, col_defs, score_col=None):
    col_aligns = {i: align for i, (key, label, width, align) in enumerate(col_defs, 1)}

    for col_idx, cell in enumerate(ws[1], 1):
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = HEADER_BORDER
    ws.row_dimensions[1].height = 36

    for row_idx, row in enumerate(ws.iter_rows(min_row=2), 2):
        fill = STRIPE_FILL if row_idx % 2 == 0 else WHITE_FILL
        for col_idx, cell in enumerate(row, 1):
            cell.font = BODY_FONT
            cell.fill = fill
            cell.border = BODY_BORDER
            h_align = col_aligns.get(col_idx, "left")
            cell.alignment = Alignment(horizontal=h_align, vertical="center")
        ws.row_dimensions[row_idx].height = 22

    for i, (key, label, width, align) in enumerate(col_defs, 1):
        col_letter = get_column_letter(i)
        ws.column_dimensions[col_letter].width = width
        fmt = NUMBER_FORMATS.get(key)
        if fmt:
            for row_idx in range(2, ws.max_row + 1):
                cell = ws.cell(row=row_idx, column=i)
                if cell.value is not None:
                    if key == "cost_advantage_pct":
                        try:
                            cell.value = float(cell.value) / 100
                        except (ValueError, TypeError):
                            pass
                    cell.number_format = fmt

    if score_col:
        for row_idx in range(2, ws.max_row + 1):
            cell = ws.cell(row=row_idx, column=score_col)
            if cell.value is None:
                continue
            try:
                v = float(cell.value)
            except (ValueError, TypeError):
                continue
            if v >= 0.7:
                cell.font = Font(name=FONT, size=10, bold=True, color=GREEN)
            elif v >= 0.5:
                cell.font = Font(name=FONT, size=10, bold=True, color=AMBER)
            else:
                cell.font = Font(name=FONT, size=10, bold=True, color=RED)

    ws.auto_filter.ref = ws.dimensions
    ws.freeze_panes = "A2"


def _build_summary_sheet(wb, dam_registry, scored_pairs):
    ws = wb.create_sheet("Summary", 0)
    config = load_config()
    country = config.get("country", "Unknown")
    total_dams = len(dam_registry)
    total_pairs = total_dams * (total_dams - 1) // 2
    viable = len(scored_pairs)
    top_energy = scored_pairs["energy_mwh_standard"].max() if "energy_mwh_standard" in scored_pairs.columns and len(scored_pairs) > 0 else 0

    ws.sheet_properties.tabColor = ACCENT

    ws.column_dimensions["A"].width = 3
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["C"].width = 18
    ws.column_dimensions["D"].width = 22
    ws.column_dimensions["E"].width = 18
    ws.column_dimensions["F"].width = 22
    ws.column_dimensions["G"].width = 18

    row = 2
    ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=7)
    c = ws.cell(row=row, column=2, value=f"PSH Screening Results: {country}")
    c.font = TITLE_FONT
    c.alignment = Alignment(vertical="center")

    row = 3
    ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=7)
    c = ws.cell(row=row, column=2, value=f"Generated {datetime.now().strftime('%B %d, %Y')}")
    c.font = SUBTITLE_FONT

    row = 5
    stats = [
        (str(total_dams), "Dams Evaluated"),
        (f"{total_pairs:,}", "Pairs Generated"),
        (str(viable), "Viable Pairs"),
        (f"{top_energy:,.0f}", "Top Energy (MWh)"),
    ]
    stat_cols = [2, 3, 4, 5]
    for i, (value, label) in enumerate(stats):
        col = stat_cols[i]
        c = ws.cell(row=row, column=col, value=value)
        c.font = STAT_VALUE_FONT
        c.alignment = Alignment(horizontal="center")
        c = ws.cell(row=row + 1, column=col, value=label)
        c.font = STAT_LABEL_FONT
        c.alignment = Alignment(horizontal="center")
    ws.row_dimensions[row].height = 34
    ws.row_dimensions[row + 1].height = 18

    row = 8
    divider_fill = PatternFill(start_color=BORDER_COLOR, end_color=BORDER_COLOR, fill_type="solid")
    for col in range(2, 8):
        ws.cell(row=row, column=col).fill = divider_fill
    ws.row_dimensions[row].height = 2

    row = 10
    ws.cell(row=row, column=2, value="Screening Parameters").font = SECTION_FONT
    ws.cell(row=row, column=5, value="Cost Benchmarks").font = SECTION_FONT
    row += 1
    left_params = [
        ("Minimum head", f"{config['filters']['min_head_m']} m"),
        ("Maximum distance", f"{config['filters']['max_distance_km']} km"),
        ("Max dist/head ratio", f"{config['filters'].get('max_distance_head_ratio', 50)}"),
        ("Minimum capacity", f"{config['filters']['min_capacity_mcm']} MCM"),
        ("Round-trip efficiency", f"{int(config['physics']['round_trip_efficiency'] * 100)}%"),
    ]
    cm = config.get("cost_model", {})
    right_params = [
        ("Battery storage", f"${config['cost_benchmarks']['battery_usd_per_mwh']}/MWh"),
        ("PSH low estimate", f"${config['cost_benchmarks']['psh_usd_per_mwh_low']}/MWh"),
        ("PSH high estimate", f"${config['cost_benchmarks']['psh_usd_per_mwh_high']}/MWh"),
        ("Tunneling cost", f"EUR {cm.get('tunneling_eur_per_km', 6_500_000):,.0f}/km"),
        ("Grid connection", f"${cm.get('grid_connection_usd_per_km', 1_000_000):,.0f}/km"),
    ]
    for i, (label, value) in enumerate(left_params):
        ws.cell(row=row + i, column=2, value=label).font = LABEL_FONT
        ws.cell(row=row + i, column=3, value=value).font = VALUE_FONT
    for i, (label, value) in enumerate(right_params):
        ws.cell(row=row + i, column=5, value=label).font = LABEL_FONT
        ws.cell(row=row + i, column=6, value=value).font = VALUE_FONT

    row += max(len(left_params), len(right_params)) + 1
    ws.cell(row=row, column=2, value="Scoring Weights").font = SECTION_FONT
    row += 1
    for key, weight in config["scoring_weights"].items():
        label = key.replace("_", " ").title()
        ws.cell(row=row, column=2, value=label).font = LABEL_FONT
        c = ws.cell(row=row, column=3, value=f"{int(weight * 100)}%")
        c.font = VALUE_FONT
        row += 1

    row += 1
    for col in range(2, 8):
        ws.cell(row=row, column=col).fill = divider_fill
    ws.row_dimensions[row].height = 2

    row += 2
    ws.cell(row=row, column=2, value="Top 5 Pairs").font = SECTION_FONT
    row += 1

    top5_headers = ["Rank", "Upper Dam", "Lower Dam", "Head (m)", "Energy (MWh)", "Score"]
    top5_aligns = ["center", "left", "left", "right", "right", "center"]
    top5_widths_needed = [8, 22, 22, 13, 15, 10]
    for i, header in enumerate(top5_headers):
        col = 2 + i
        c = ws.cell(row=row, column=col, value=header)
        c.font = Font(name=FONT, bold=True, size=9, color=WHITE)
        c.fill = HEADER_FILL
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = HEADER_BORDER
    ws.row_dimensions[row].height = 28
    row += 1

    for _, pair in scored_pairs.head(5).iterrows():
        values = [
            int(pair.get("rank", 0)),
            pair.get("upper_dam_name", ""),
            pair.get("lower_dam_name", ""),
            pair.get("head_m", 0),
            pair.get("energy_mwh_standard", 0),
            pair.get("composite_score", 0),
        ]
        fmts = ["0", None, None, "#,##0", "#,##0", "0.000"]
        for i, (val, fmt) in enumerate(zip(values, fmts)):
            col = 2 + i
            c = ws.cell(row=row, column=col, value=val)
            c.font = BODY_FONT
            c.border = BODY_BORDER
            c.alignment = Alignment(horizontal=top5_aligns[i], vertical="center")
            if fmt:
                c.number_format = fmt
            if i == 5:
                try:
                    v = float(val)
                    if v >= 0.7:
                        c.font = Font(name=FONT, size=10, bold=True, color=GREEN)
                    elif v >= 0.5:
                        c.font = Font(name=FONT, size=10, bold=True, color=AMBER)
                    else:
                        c.font = Font(name=FONT, size=10, bold=True, color=RED)
                except (ValueError, TypeError):
                    pass
        if row % 2 == 0:
            for i in range(6):
                ws.cell(row=row, column=2 + i).fill = STRIPE_FILL
        ws.row_dimensions[row].height = 22
        row += 1

    row += 1
    for col in range(2, 8):
        ws.cell(row=row, column=col).fill = divider_fill
    ws.row_dimensions[row].height = 2

    row += 2
    ws.cell(row=row, column=2, value="Methodology").font = SECTION_FONT
    row += 1
    methodology = (
        "All dam pairs within the configured distance and head thresholds were evaluated. "
        "Each viable pair was scored on energy potential, cost competitiveness vs battery storage, "
        "grid proximity, and reservoir suitability. The composite score (0-1) ranks pairs by "
        "overall PSH viability."
    )
    ws.merge_cells(start_row=row, start_column=2, end_row=row + 2, end_column=7)
    c = ws.cell(row=row, column=2, value=methodology)
    c.font = Font(name=FONT, size=9, color=MUTED)
    c.alignment = Alignment(wrap_text=True, vertical="top")

    ws.sheet_view.showGridLines = False

    return ws


def _export_excel(dam_registry, scored_pairs):
    output_path = OUTPUT_DIR / "results.xlsx"

    dam_col_defs = [(k, l, w, a) for k, l, w, a in DAM_COLUMNS if k in dam_registry.columns]
    pair_col_defs = [(k, l, w, a) for k, l, w, a in PAIR_COLUMNS if k in scored_pairs.columns]

    with pd.ExcelWriter(str(output_path), engine="openpyxl") as writer:
        dam_df = dam_registry[[k for k, l, w, a in dam_col_defs]].copy()
        dam_df.columns = [l for k, l, w, a in dam_col_defs]
        dam_df.to_excel(writer, sheet_name="Dam Registry", index=False)

        pair_df = scored_pairs[[k for k, l, w, a in pair_col_defs]].copy()
        for col in ["energy_mwh_standard"]:
            if col in pair_df.columns:
                pair_df[col] = pd.to_numeric(pair_df[col], errors="coerce").round(0)
        if "composite_score" in pair_df.columns:
            pair_df["composite_score"] = pair_df["composite_score"].round(3)
        pair_df.columns = [l for k, l, w, a in pair_col_defs]
        pair_df.to_excel(writer, sheet_name="Pairs Ranked", index=False)

        wb = writer.book

        _build_summary_sheet(wb, dam_registry, scored_pairs)

        ws_dam = wb["Dam Registry"]
        _style_data_sheet(ws_dam, dam_col_defs)

        ws_pair = wb["Pairs Ranked"]
        score_col_idx = next((i for i, (k, l, w, a) in enumerate(pair_col_defs, 1) if k == "composite_score"), None)
        _style_data_sheet(ws_pair, pair_col_defs, score_col=score_col_idx)

    log.info(f"Saved Excel to {output_path}")
    return str(output_path)


def _export_json(dam_registry, scored_pairs):
    output_path = OUTPUT_DIR / "results.json"
    pairs_list = []
    for _, row in scored_pairs.iterrows():
        entry = {
            "rank": int(row.get("rank", 0)),
            "upper_dam": row.get("upper_dam_name"),
            "lower_dam": row.get("lower_dam_name"),
            "head_m": round(row.get("head_m", 0)),
            "distance_km": round(row.get("distance_km", 0), 1),
            "distance_head_ratio": row.get("distance_head_ratio"),
            "energy_mwh_standard": round(row.get("energy_mwh_standard", 0)),
            "composite_score": round(row.get("composite_score", 0), 4),
            "psh_cost_usd_per_mwh": row.get("psh_cost_usd_per_mwh"),
            "cost_advantage_pct": row.get("cost_advantage_pct"),
            "lcoe_eur_per_mwh": row.get("lcoe_eur_per_mwh"),
            "tunneling_cost_eur": row.get("tunneling_cost_eur"),
            "grid_connection_cost_eur": row.get("grid_connection_cost_eur"),
            "grid_distance_km": row.get("grid_distance_km"),
        }
        pairs_list.append(entry)

    result = {
        "generated": datetime.now().isoformat(),
        "config": load_config(),
        "total_dams": len(dam_registry),
        "total_pairs_scored": len(scored_pairs),
        "pairs": pairs_list,
    }

    with open(output_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    log.info(f"Saved JSON to {output_path}")
    return str(output_path)


def _export_3d_kml(dam_registry, scored_pairs):
    dams = {d["name"]: d for _, d in dam_registry.iterrows()} if hasattr(dam_registry, "iterrows") else {}

    kml = simplekml.Kml(name="PSH Screening - Top Pairs 3D")

    for _, pair in scored_pairs.head(20).iterrows():
        rank = int(pair.get("rank", 0))
        upper_name = pair.get("upper_dam_name", "?")
        lower_name = pair.get("lower_dam_name", "?")
        head = pair.get("head_m", 0)
        dist = pair.get("distance_km", 0)
        energy = pair.get("energy_mwh_standard", 0)
        score = pair.get("composite_score", 0)

        folder = kml.newfolder(name=f"#{rank}: {upper_name} - {lower_name}")
        folder.description = f"Head: {head:.0f}m | Distance: {dist:.1f}km | Energy: {energy:,.0f} MWh | Score: {score:.3f}"

        upper_dam = dams.get(upper_name, {})
        lower_dam = dams.get(lower_name, {})
        upper_elev = pair.get("upper_elevation_m", 0)
        lower_elev = pair.get("lower_elevation_m", 0)

        for name, lat, lon, elev, dam_data, color, role in [
            (upper_name, pair["upper_lat"], pair["upper_lon"], upper_elev, upper_dam, simplekml.Color.red, "UPPER"),
            (lower_name, pair["lower_lat"], pair["lower_lon"], lower_elev, lower_dam, simplekml.Color.blue, "LOWER"),
        ]:
            pt = folder.newpoint(name=f"{role}: {name}")
            pt.coords = [(lon, lat)]
            pt.altitudemode = simplekml.AltitudeMode.clamptoground
            pt.style.iconstyle.color = color
            pt.style.iconstyle.scale = 1.5
            cap = dam_data.get("capacity_mcm", "?") if isinstance(dam_data, dict) else "?"
            grid = dam_data.get("grid_distance_km", "?") if isinstance(dam_data, dict) else "?"
            pt.description = f"Elevation: {elev:.0f}m\nCapacity: {cap} MCM\nGrid: {grid}km"

        line = folder.newlinestring(name=f"{head:.0f}m head, {dist:.1f}km")
        line.coords = [(pair["upper_lon"], pair["upper_lat"]), (pair["lower_lon"], pair["lower_lat"])]
        line.altitudemode = simplekml.AltitudeMode.clamptoground
        line.style.linestyle.width = 4
        if score > 0.7:
            line.style.linestyle.color = simplekml.Color.green
        elif score > 0.5:
            line.style.linestyle.color = simplekml.Color.orange
        else:
            line.style.linestyle.color = simplekml.Color.red

        center_lat = (pair["upper_lat"] + pair["lower_lat"]) / 2
        center_lon = (pair["upper_lon"] + pair["lower_lon"]) / 2
        lookat = simplekml.LookAt()
        lookat.latitude = center_lat
        lookat.longitude = center_lon
        lookat.range = dist * 1500
        lookat.tilt = 60
        folder.lookat = lookat

    kml_path = OUTPUT_DIR / "top_pairs_3d.kml"
    kml.save(str(kml_path))
    log.info(f"Saved 3D KML to {kml_path}")
    return str(kml_path)


def _export_geojson(dam_registry, scored_pairs):
    features = []
    for _, pair in scored_pairs.iterrows():
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [pair["upper_lon"], pair["upper_lat"]],
                    [pair["lower_lon"], pair["lower_lat"]],
                ],
            },
            "properties": {
                "rank": int(pair.get("rank", 0)),
                "upper_dam": pair.get("upper_dam_name"),
                "lower_dam": pair.get("lower_dam_name"),
                "head_m": round(pair.get("head_m", 0)),
                "distance_km": round(pair.get("distance_km", 0), 1),
                "distance_head_ratio": pair.get("distance_head_ratio"),
                "energy_mwh": round(pair.get("energy_mwh_standard", 0)),
                "score": round(pair.get("composite_score", 0), 3),
                "lcoe_eur_per_mwh": pair.get("lcoe_eur_per_mwh"),
            },
        })

    geojson = {"type": "FeatureCollection", "features": features}
    geojson_path = OUTPUT_DIR / "pairs.geojson"
    with open(geojson_path, "w") as f:
        json.dump(geojson, f, indent=2)
    log.info(f"Saved GeoJSON to {geojson_path}")
    return str(geojson_path)


def generate_all_outputs(dam_registry, all_pairs_df, scored_pairs_df, sensitivity_results=None):
    return generate_clean_outputs(dam_registry, scored_pairs_df)
