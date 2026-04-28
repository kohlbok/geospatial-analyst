"""Direct CLI for the geospatial tools. Used as a fallback when the MCP server cannot run reliably (e.g. on Windows). Each subcommand mirrors an MCP tool exactly. Output JSON matches the MCP response."""
import argparse
import os
import sys
import traceback
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUNBUFFERED", "1")

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server as _server
from geospatial.config import safe_dumps


def _resolve_fn(name):
    obj = getattr(_server, name)
    return obj.fn if hasattr(obj, "fn") else obj


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="geospatial-cli",
        description="Direct CLI for the geospatial tools (Windows fallback when the MCP server cannot run).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("cleanup")
    p.add_argument("--targets", default="screen")

    p = sub.add_parser("load_dam_registry")
    p.add_argument("--file", default="")

    sub.add_parser("generate_pairs")
    sub.add_parser("screen_pairs")
    sub.add_parser("generate_map")
    sub.add_parser("generate_overview_map")
    sub.add_parser("generate_results")

    p = sub.add_parser("generate_executive_summary")
    p.add_argument("--expert_review", required=True)

    p = sub.add_parser("download_file")
    p.add_argument("--url", required=True)
    p.add_argument("--filename", required=True)
    p.add_argument("--subfolder", default="")

    p = sub.add_parser("inspect_file")
    p.add_argument("--path", required=True)
    p.add_argument("--max_rows", type=int, default=20)

    p = sub.add_parser("parse_tabular")
    p.add_argument("--path", required=True)
    p.add_argument("--column_mapping", required=True)
    p.add_argument("--filters", default="[]")
    p.add_argument("--output_name", default="parsed")

    p = sub.add_parser("merge_sources")
    p.add_argument("--proximity_threshold_m", type=int, default=0)
    p.add_argument("--output_name", default="dams")

    sub.add_parser("enrich_names")

    p = sub.add_parser("enrich_grid_distance")
    p.add_argument("--max_workers", type=int, default=3)

    sub.add_parser("enrich_elevation")
    sub.add_parser("enrich_coordinates")
    sub.add_parser("fetch_under_construction")

    sub.add_parser("tier1_elevation_screen")
    sub.add_parser("generate_tier1_results")
    sub.add_parser("siting_scan")
    sub.add_parser("siting_scan_status")
    sub.add_parser("generate_siting_results")

    return parser


def main():
    parser = _build_parser()
    args = vars(parser.parse_args())
    cmd = args.pop("cmd")
    fn = _resolve_fn(cmd)
    try:
        result = fn(**args)
        if result is None:
            print(safe_dumps({"status": "ok"}))
        else:
            print(result)
    except SystemExit:
        raise
    except Exception as e:
        sys.stderr.write(traceback.format_exc())
        print(safe_dumps({"error": str(e), "command": cmd}))
        sys.exit(1)


if __name__ == "__main__":
    main()
