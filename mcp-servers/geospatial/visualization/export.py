import json
import logging
from datetime import datetime

import pandas as pd
import simplekml

from ..config import OUTPUT_EXPORTS, OUTPUT_MAPS, load_config

log = logging.getLogger(__name__)

EXCLUDE_COLUMNS = ["terrain_profile"]


def _clean_for_export(df):
    df = df.copy()
    for col in EXCLUDE_COLUMNS:
        if col in df.columns:
            df = df.drop(columns=[col])
    for col in df.columns:
        if df[col].apply(lambda x: isinstance(x, (list, dict))).any():
            df[col] = df[col].apply(lambda x: json.dumps(x) if isinstance(x, (list, dict)) else x)
    return df


def export_excel(dam_registry, all_pairs_df, scored_pairs_df, sensitivity_results=None):
    config = load_config()
    output_path = OUTPUT_EXPORTS / "psh_screening_results.xlsx"

    with pd.ExcelWriter(str(output_path), engine="openpyxl") as writer:
        registry_export = _clean_for_export(dam_registry)
        registry_export.to_excel(writer, sheet_name="Dam Registry", index=False)

        if all_pairs_df is not None and len(all_pairs_df) > 0:
            pairs_export = _clean_for_export(all_pairs_df)
            cols_to_show = [c for c in pairs_export.columns if not c.startswith("score_")]
            pairs_export[cols_to_show].to_excel(writer, sheet_name="All Pairs", index=False)

        if scored_pairs_df is not None and len(scored_pairs_df) > 0:
            scored_export = _clean_for_export(scored_pairs_df)
            scored_export.to_excel(writer, sheet_name="Viable Pairs (Ranked)", index=False)

            top_n = config["output"]["top_n_detailed"]
            top = scored_export.head(top_n)
            top.to_excel(writer, sheet_name=f"Top {top_n} Deep Dive", index=False)

        if sensitivity_results:
            sens_rows = []
            for key, val in sensitivity_results.items():
                if isinstance(val, dict):
                    row = {"scenario": key}
                    row.update({k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in val.items()})
                    sens_rows.append(row)
            if sens_rows:
                pd.DataFrame(sens_rows).to_excel(writer, sheet_name="Sensitivity Analysis", index=False)

        config_df = pd.DataFrame([
            {"parameter": k, "value": json.dumps(v) if isinstance(v, (list, dict)) else v}
            for k, v in _flatten_config(config).items()
        ])
        config_df.to_excel(writer, sheet_name="Configuration", index=False)

    log.info(f"Saved Excel workbook to {output_path}")
    return str(output_path)


def export_json(dam_registry, scored_pairs_df, sensitivity_results=None):
    config = load_config()
    top_n = config["output"]["top_n_detailed"]

    ranked_list = []
    if scored_pairs_df is not None and len(scored_pairs_df) > 0:
        for _, pair in scored_pairs_df.iterrows():
            entry = {}
            for col in pair.index:
                if col in EXCLUDE_COLUMNS:
                    continue
                val = pair[col]
                if pd.isna(val) if isinstance(val, (int, float)) else val is None:
                    entry[col] = None
                elif isinstance(val, (list, dict)):
                    entry[col] = val
                else:
                    try:
                        entry[col] = float(val) if isinstance(val, (int, float, complex)) else str(val)
                    except (ValueError, TypeError):
                        entry[col] = str(val)
            ranked_list.append(entry)

    output = {
        "metadata": {
            "run_date": datetime.now().strftime("%Y-%m-%d"),
            "parameters": config,
            "total_dams": len(dam_registry),
            "pairs_viable": len(scored_pairs_df) if scored_pairs_df is not None else 0,
            "top_n_pairs": ranked_list[:top_n],
        },
        "ranked_pairs": ranked_list,
    }

    if sensitivity_results:
        output["sensitivity"] = sensitivity_results

    output_path = OUTPUT_EXPORTS / "psh_screening_results.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)

    log.info(f"Saved JSON export to {output_path}")
    return str(output_path)


def export_kml(dam_registry, scored_pairs_df=None):
    kml = simplekml.Kml(name="Morocco PSH Screening")

    dam_folder = kml.newfolder(name="Dam Registry")
    for _, dam in dam_registry.iterrows():
        if dam.get("lat") is None:
            continue
        pnt = dam_folder.newpoint(
            name=dam.get("name", "Unknown"),
            coords=[(dam["lon"], dam["lat"])],
        )
        pnt.description = (
            f"ID: {dam.get('id', '')}\n"
            f"Elevation: {dam.get('elevation_wall_m', 'N/A')}m\n"
            f"Capacity: {dam.get('capacity_mcm', 'N/A')} MCM\n"
            f"Height: {dam.get('height_m', 'N/A')}m\n"
            f"Year: {dam.get('year_built', 'N/A')}"
        )
        pnt.style.iconstyle.icon.href = "http://maps.google.com/mapfiles/kml/shapes/water.png"

    if scored_pairs_df is not None and len(scored_pairs_df) > 0:
        pair_folder = kml.newfolder(name="Viable Pairs")
        for _, pair in scored_pairs_df.iterrows():
            rank = pair.get("rank", "")
            line = pair_folder.newlinestring(
                name=f"#{rank}: {pair.get('upper_dam_name', '')} - {pair.get('lower_dam_name', '')}",
                coords=[
                    (pair["upper_lon"], pair["upper_lat"]),
                    (pair["lower_lon"], pair["lower_lat"]),
                ],
            )
            score = pair.get("composite_score", 0)
            if score > 0.7:
                color = simplekml.Color.green
            elif score > 0.4:
                color = simplekml.Color.orange
            else:
                color = simplekml.Color.red

            line.style.linestyle.color = color
            line.style.linestyle.width = 3
            line.description = (
                f"Rank: {rank}\n"
                f"Head: {pair.get('head_m', 'N/A')}m\n"
                f"Distance: {pair.get('distance_km', 'N/A')} km\n"
                f"Energy: {pair.get('energy_mwh_standard', 'N/A')} MWh\n"
                f"Score: {score:.3f}" if score else "N/A"
            )

    kml_path = OUTPUT_MAPS / "morocco_dams.kml"
    kml.save(str(kml_path))

    try:
        kmz_path = OUTPUT_MAPS / "morocco_dams.kmz"
        kml.savekmz(str(kmz_path))
        log.info(f"Saved KMZ to {kmz_path}")
    except Exception:
        pass

    log.info(f"Saved KML to {kml_path}")
    return str(kml_path)


def export_geojson(dam_registry, scored_pairs_df=None):
    features = []

    for _, dam in dam_registry.iterrows():
        if dam.get("lat") is None:
            continue
        props = {}
        for col in dam.index:
            val = dam[col]
            if isinstance(val, (list, dict)):
                props[col] = val
            elif pd.isna(val) if isinstance(val, (int, float)) else val is None:
                props[col] = None
            else:
                props[col] = val

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(dam["lon"]), float(dam["lat"])],
            },
            "properties": props,
        })

    if scored_pairs_df is not None:
        for _, pair in scored_pairs_df.iterrows():
            props = {}
            for col in pair.index:
                if col in EXCLUDE_COLUMNS:
                    continue
                val = pair[col]
                if isinstance(val, (list, dict)):
                    props[col] = json.dumps(val)
                elif pd.isna(val) if isinstance(val, (int, float)) else val is None:
                    props[col] = None
                else:
                    try:
                        props[col] = float(val) if isinstance(val, (int, float)) else str(val)
                    except (ValueError, TypeError):
                        props[col] = str(val)

            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [float(pair["upper_lon"]), float(pair["upper_lat"])],
                        [float(pair["lower_lon"]), float(pair["lower_lat"])],
                    ],
                },
                "properties": props,
            })

    geojson = {
        "type": "FeatureCollection",
        "features": features,
    }

    output_path = OUTPUT_MAPS / "morocco_pairs.geojson"
    with open(output_path, "w") as f:
        json.dump(geojson, f, indent=2, default=str)

    log.info(f"Saved GeoJSON to {output_path}")
    return str(output_path)


def generate_all_outputs(dam_registry, all_pairs_df, scored_pairs_df, sensitivity_results=None):
    paths = {}
    paths["excel"] = export_excel(dam_registry, all_pairs_df, scored_pairs_df, sensitivity_results)
    paths["json"] = export_json(dam_registry, scored_pairs_df, sensitivity_results)
    paths["kml"] = export_kml(dam_registry, scored_pairs_df)
    paths["geojson"] = export_geojson(dam_registry, scored_pairs_df)
    log.info(f"Generated all export files: {list(paths.keys())}")
    return paths


def _flatten_config(d, prefix=""):
    items = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            items.update(_flatten_config(v, key))
        else:
            items[key] = v
    return items
