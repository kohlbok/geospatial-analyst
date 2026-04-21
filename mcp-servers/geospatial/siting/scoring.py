import numpy as np
from sklearn.neighbors import BallTree

EARTH_RADIUS_M = 6_371_000.0


def dedupe_candidates(candidates, merge_distance_m=500):
    if len(candidates) < 2:
        return candidates
    coords = np.radians([
        [c.get("sink_lat") or c.get("centroid_lat"), c.get("sink_lon") or c.get("centroid_lon")]
        for c in candidates
    ])
    tree = BallTree(coords, metric="haversine")
    threshold_rad = merge_distance_m / EARTH_RADIUS_M
    neighbors = tree.query_radius(coords, r=threshold_rad)

    parent = list(range(len(candidates)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i, nbs in enumerate(neighbors):
        for j in nbs:
            if i != j:
                union(i, j)

    clusters = {}
    for i in range(len(candidates)):
        clusters.setdefault(find(i), []).append(i)

    keepers = []
    for cluster in clusters.values():
        best_idx = min(cluster, key=lambda i: candidates[i].get("capex_per_mwh_usd") or float("inf"))
        keepers.append(candidates[best_idx])
    return keepers


def score_candidates(candidates, params):
    if not candidates:
        return candidates

    merge_distance = params.get("siting", {}).get("candidate_merge_distance_m", 500)
    candidates = dedupe_candidates(candidates, merge_distance_m=merge_distance)

    weights = params.get("siting_scoring_weights", {})
    w_cost = weights.get("capex_per_mwh", 0.40)
    w_dh = weights.get("distance_head_ratio", 0.40)
    w_grid = weights.get("grid_distance", 0.20)

    costs = [c.get("capex_per_mwh_usd") or float("inf") for c in candidates]
    dh_ratios = [c.get("distance_head_ratio") or float("inf") for c in candidates]
    grids = [c.get("grid_distance_km") or float("inf") for c in candidates]

    def norm_lower(values):
        finite = [v for v in values if v != float("inf")]
        if not finite:
            return [0.0] * len(values)
        lo, hi = min(finite), max(finite)
        if hi == lo:
            return [1.0] * len(values)
        return [1.0 - (v - lo) / (hi - lo) if v != float("inf") else 0.0 for v in values]

    nc = norm_lower(costs)
    ndh = norm_lower(dh_ratios)
    ng = norm_lower(grids)

    for i, c in enumerate(candidates):
        c["composite_score"] = round(
            w_cost * nc[i] + w_dh * ndh[i] + w_grid * ng[i],
            4,
        )

    return sorted(candidates, key=lambda c: -(c.get("composite_score") or 0))
