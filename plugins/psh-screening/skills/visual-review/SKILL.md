# Visual Review

Protocol for verifying dam registry entries using satellite imagery. Applied after merge and enrichment, before screening.

Three goals:
1. **Verify** -- is this a real dam, a false positive, or a natural water body?
2. **Name** -- unnamed entries can be identified from map labels
3. **Deduplicate** -- catch when two entries point to the same physical structure

## Satellite Imagery

Fetch an Esri World Imagery tile for each dam:
```
https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?bbox={lon-0.02},{lat-0.02},{lon+0.02},{lat+0.02}&bboxSR=4326&size=800,600&format=png&f=image
```

For closer inspection (dam wall confirmation), narrow the bbox to 0.005 degrees.

## Decision Tree

Work through in order. Stop at first definitive answer.

**Guiding principle**: only remove if it is a true duplicate, outside the country, or there is literally nothing there. Natural water bodies are valid PSH lower reservoirs -- reclassify them, do not remove them.

```
Is the coordinate outside the target country?
  YES --> remove | wrong_country

Is there a dam/barrage label visible on the map?
  YES --> Can you confirm a dam wall in the imagery?
            YES --> real_dam | rename: [label]
            NO  --> real_dam | structure_not_visible

Is there water visible?
  NO --> Is a dam wall, embankment, or spillway visible?
           YES --> real_dam (dry reservoir -- drought or seasonal drawdown)
           NO  --> remove | false_positive (no water, no structure)

  YES --> Is the water body clearly natural (circular lake, wetland, salt flat, coastal lagoon)?
            YES --> natural_reservoir
            NO or UNSURE -->
              Is there a dam wall or embankment visible?
                YES --> real_dam
                NO  --> natural_reservoir (water present, no dam wall)
```

## Coordinate Correction

The registry coordinate is used to extract elevation from the DEM. A coordinate in the middle of a reservoir returns the water surface elevation, not the dam wall elevation -- this produces wrong head calculations.

**When to fix**: the marker is clearly floating in open water, more than ~300m from the visible dam wall. Common causes: HydroLAKES uses polygon centroids, GeoDAR uses water extent centroids.

**How to fix**: find the dam wall -- the straight bar, embankment, or spillway crossing the valley. Aim for the crest centreline (midpoint along the top of the wall). Record as `fix_coord | lat, lon`.

**When NOT to fix**: coordinate is within 200m of the wall crest (within DEM pixel size).

## Dam Wall Identification

| Feature | What to look for |
|---------|-----------------|
| Concrete gravity dam | Straight grey/white bar across canyon |
| Earthen embankment | Wide flat-topped mound across valley, trapezoidal cross-section |
| Spillway | Stepped or channeled outlet on one side, often white-stained |
| Crest access road | Road running bank-to-bank along dam top |
| Dendritic reservoir | Branching arms following flooded tributary valleys (not seen in natural lakes) |

## Natural Water Body Identification

| Type | Visual indicators |
|------|------------------|
| Natural lake | Circular/elliptical shape, smooth consistent shoreline, no straight embankment |
| Seasonal salt flat | Large flat white/grey surface, irregular amorphous boundary, flat terrain |
| Wetland / lagoon | Adjacent to coast or river mouth, water across flat terrain, no confining structure |

## Near-Duplicate Detection

| Distance | Interpretation |
|----------|---------------|
| <500m | Almost certainly same dam |
| 500m--1.5km, same reservoir body | Near-duplicate -- keep the one with better wall coordinates |
| >1.5km | May be separate dams on same river -- verify individually |

Two markers inside the same reservoir at different positions (one near the wall, one in the center) are a common merge artifact. The proximity merge misses them when sources have coordinates >500m apart. Visual review is the only place to catch this.

## Drought Considerations

Many countries experience drought periods where reservoirs appear empty in satellite imagery. An empty reservoir is NOT a reason to remove an entry. Check for dam wall or embankment structure before classifying.

## Verdict Codes

| Code | Action | Meaning |
|------|--------|---------|
| `real_dam` | Keep | Reservoir or wall visible |
| `real_dam \| rename: X` | Keep + rename | Confirmed; update name |
| `real_dam \| structure_not_visible` | Keep | Confirmed via label/sources but wall not resolvable in imagery |
| `real_dam \| coord_spread_ok` | Keep | Coord spread acceptable, dam wall confirmed |
| `natural_reservoir` | Reclassify | Natural water body, no dam wall, but may be valid PSH reservoir |
| `fix_coord \| lat, lon` | Keep + fix | Dam confirmed but coordinate is wrong |
| `remove \| false_positive` | Remove | No water, no structure -- dry land, farmland, urban area |
| `remove \| wrong_country` | Remove | Outside target country |
| `remove \| near_duplicate` | Remove | Same physical structure as another entry |

## coord_spread

When multiple databases merge into one entry, coord_spread is the distance in meters between the furthest-apart source coordinates.

| Spread | Interpretation |
|--------|---------------|
| <500m | Normal -- one source at wall, another in reservoir body |
| 500m--2000m | Acceptable if dam wall confirmed |
| >2000m | Requires full visual review |
| >5000m | Likely a merge error or two separate dams |
