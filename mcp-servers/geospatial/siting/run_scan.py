"""Background worker for basin detection + per-candidate cost optimization. Launched by the siting_scan MCP tool."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import orjson
from geospatial.config import load_config, DATA_PROCESSED, DATA_DIR
from geospatial.terrain.dem import load_dem_patch
from geospatial.siting.scanner import scan_and_analyze
from geospatial.siting.scoring import score_candidates

if len(sys.argv) < 2:
    print("ERROR: run_scan.py requires an active registry filename as argv[1]", flush=True)
    sys.exit(1)

registry_path = DATA_DIR / sys.argv[1]
with open(registry_path, "rb") as f:
    dams = orjson.loads(f.read())

config = load_config()
siting = config.get("siting", {})
search_radius_km = siting.get("search_radius_km", 20)
resolution_m = siting.get("tier2_resolution_m", 30)

dam_lookup = {d.get("id"): d for d in dams}

with open(DATA_PROCESSED / "siting_tier1.json", "rb") as f:
    tier1_results = orjson.loads(f.read())

partial_path = DATA_PROCESSED / "siting_candidates_partial.json"
pid_path = DATA_PROCESSED / "siting_scan.pid"

all_candidates = []
done_ids: set = set()
if partial_path.exists():
    with open(partial_path, "rb") as f:
        saved = orjson.loads(f.read())
    all_candidates = saved.get("candidates", [])
    done_ids = set(saved.get("done_ids", []))
    print(f"Resuming: {len(done_ids)} dams already done, {len(all_candidates)} candidates so far", flush=True)

survivors = [r for r in tier1_results if r.get("viable_up") or r.get("viable_down")]
total = len(survivors)
all_kill_reasons: dict = {}

for i, t1 in enumerate(survivors):
    dam_id = t1.get("dam_id")
    if dam_id in done_ids:
        continue
    dam = dam_lookup.get(dam_id)
    if dam is None:
        done_ids.add(dam_id)
        continue

    print(f"[{i+1}/{total}] {dam.get('name', dam_id)}", flush=True)
    patch = load_dem_patch(float(dam["lat"]), float(dam["lon"]), search_radius_km, resolution_m=resolution_m)
    if patch is None:
        all_kill_reasons["no_dem"] = all_kill_reasons.get("no_dem", 0) + 1
        done_ids.add(dam_id)
        continue

    candidates, kill_reasons = scan_and_analyze(dam, patch, t1, config)
    for k, v in kill_reasons.items():
        all_kill_reasons[k] = all_kill_reasons.get(k, 0) + v

    if candidates:
        all_candidates.extend(candidates)
        print(f"  -> {len(candidates)} candidates", flush=True)

    done_ids.add(dam_id)
    with open(partial_path, "wb") as f:
        f.write(orjson.dumps(
            {"candidates": all_candidates, "done_ids": list(done_ids)},
            option=orjson.OPT_SERIALIZE_NUMPY,
        ))

print(f"Dedupe + score ({len(all_candidates)} candidates before)...", flush=True)
all_candidates = score_candidates(all_candidates, config)
print(f"After cross-dam dedup: {len(all_candidates)} candidates", flush=True)

with open(DATA_PROCESSED / "siting_candidates.json", "wb") as f:
    f.write(orjson.dumps(
        all_candidates,
        option=orjson.OPT_INDENT_2 | orjson.OPT_SERIALIZE_NUMPY,
    ))

if partial_path.exists():
    partial_path.unlink()
if pid_path.exists():
    pid_path.unlink()

beats = sum(1 for c in all_candidates if c.get("passes_battery_test"))
marginal = sum(1 for c in all_candidates if c.get("marginal_flag") and not c.get("passes_battery_test"))
print(f"DONE: {len(all_candidates)} candidates, {beats} beat battery, {marginal} marginal", flush=True)
print(f"Kill reasons: {all_kill_reasons}", flush=True)
