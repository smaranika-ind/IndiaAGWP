# India Water Productivity & Water Footprint Atlas

A lightweight, no-database web app that visually matches IWMI's official India
Water Productivity Atlas (https://indiawpatlas.shinyapps.io/wpatlas/), covering
its **Trends** and **Comparison** tabs at **country, state, and district** scale.
Built for training sessions and presentations.

## What's inside

```
wpatlas_webapp/
├── app.py                     # entrypoint: page setup, shared sidebar, wires up the two tabs
├── atlas_view.py              # the shared "Analysis Options" sidebar + map/stats panels
├── tab_trends.py              # Trends tab (thin wrapper: header says "Temporal Variation")
├── tab_comparisons.py         # Comparison tab (thin wrapper: header says "Spatial Variation")
├── common.py                  # data loading, CSS/navbar styling, quantile map classification
├── indicators.py              # indicator names, units, short codes shown in the sidebar/legend
├── requirements.txt           # the only 4 packages needed to run it
├── app_data/                  # pre-processed data the app reads directly (no DB!)
│   ├── district_data.parquet
│   ├── state_data.parquet
│   ├── state_data_for_map.parquet
│   ├── national_data.parquet
│   ├── districts.geojson
│   ├── states.geojson
│   └── state_crosswalk.json
├── data_prep/
│   └── build_datasets.py      # the script that PRODUCED app_data/ (only needed if you get new raw data later)
└── README.md
```

There is **no database** and **no separate backend server**. Streamlit is both the
backend and frontend: it reads the `app_data/` files straight off disk each time
the app starts, and everything is cached in memory after that. This is why it's
"light" — nothing to install, configure, or keep running except the app itself.

## Does it calculate indicators dynamically?

**Not from raw formulas — but yes, dynamically in the sense that matters.**
Every indicator (PWP, water footprints, etc.) was calculated **once**, ahead of
time, using the exact same logic as your `calculations_updated_tcwu.py`
(`run_all_calculations`, `indicator_calculations`), via `data_prep/build_datasets.py`.
The app does not re-run those formulas on every click — that would be pointless,
since the math is deterministic and only the raw inputs matter.

What the app **does** do live, on every "Update" click, is filter and re-aggregate
those precomputed numbers based on your sidebar choices — the map, the quantile
color classes, the box plot, and both trend charts are all built fresh each time
from whatever Level / State / Indicator / Crop / Year you pick. So: static
calculation engine, dynamic exploration.

True live recalculation (e.g. "what if groundwater share were 10% higher") only
becomes relevant for a future **Scenarios** tab — see "Extending it later" below.

## Matching the official Atlas's interface

The sidebar controls are named to match the official app exactly:

| Control | What it does here |
|---|---|
| Primary unit of analysis | Fixed to "Administrative level" (River basin needs a boundary file you haven't provided yet) |
| Secondary unit of analysis | "All India" or a specific state — zooms the district map, and sets the scope for the two trend charts on the right |
| Tertiary unit of analysis | "Country wise" / "State wise" / "District wise" — this is the map's resolution |
| Indicator | All 22 indicators from your calculation scripts, in one flat dropdown |
| Production system | Fixed to "Crop" (no cropping-system or livestock data available) |
| Crop(s) | Any of the 78 crops, or "All crops" (a true recomputed aggregate, not an average of ratios) |
| Year(s) | Any year 1999–2022 |

The map uses the same **4-class quantile legend with red→orange→light green→dark
green** colors and a gray "Data not available/reliable" class as the reference
screenshots (computed live from whatever's currently selected, via
`common.classify_quantile`). The three right-hand panels — **Statistical Analysis**
(box plot), **Effect of Other Factors** (indicator vs. Yield over time), and
**Additional Insights** (Area vs. Crop Water Use over time) — are also reproduced.

One thing intentionally left out: the actual IWMI/CGIAR/NEXUS Gains logo images
in the top-left of the reference screenshots. I don't have those image files, so
the navbar currently shows a text title instead. If you drop logo image files into
the repo, they're easy to add into the `.wpatlas-navbar` HTML block in `common.py`.

## Why not PostgreSQL/PostGIS?

Your original prototype (`backend_1.py`) used PostgreSQL + PostGIS. That's the
right tool if data changes constantly and many apps need to query it live, but
for a training/presentation tool where the underlying data is basically fixed,
it's unnecessary weight:
- you'd need a database server running *somewhere* around the clock
- free hosts for a live Postgres+PostGIS instance are limited and can be flaky
- you'd have two things to deploy and keep in sync (DB + app) instead of one

Instead, all the calculations your scripts did (`run_all_calculations`,
`indicator_calculations`, etc. from `calculations_updated_tcwu.py`) were run
**once**, ahead of time, by `data_prep/build_datasets.py`, and the results were
saved as compact files. The app just reads those files. If you get new raw data
in the future, you re-run that one script and replace the files in `app_data/`.

## Data notes

- Source: `crop_data_calculated_final_3.csv` (district × crop × year, 1999–2022,
  622 districts, 78 crops, already carrying all the indicator columns from your
  calculation scripts).
- An **"ALL CROPS"** option is included at every scale — it is *not* an average
  of the per-crop ratios, it's recomputed from summed production/water volumes
  (same approach as `indicator_calculations()` in your script), so it's a valid
  aggregate, not a misleading mean-of-means.
- District boundaries matched to the data by (state, district) name: **595/603
  district pairs matched automatically (98.7%)**. A handful of rows in the
  original raw CSV have mismatched state/district labels (e.g. a "Dantewada"
  filed under Karnataka instead of Chhattisgarh) — these still show up in the
  data table but won't appear on the map since we can't be sure of their location.
- State boundaries: a few states in the underlying shapefile are merged
  differently than in the data (Dadra & Nagar Haveli + Daman & Diu are one
  polygon; the two "Jammu and Kashmir" rows in the raw data are combined).
  `build_datasets.py` handles this merge automatically for the map only — the
  state data table still shows them separately.

## Running it locally (optional, to preview before deploying)

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open the local URL it prints (usually `http://localhost:8501`).

## Comparison tab: how it decides what to compare

The Comparison sidebar lets you multi-select **State(s)** and **Crop(s)** (unlike
Trends, which is single-select). The logic:

- **2+ states selected, 1 crop** -> compares **states**: one district-level map per
  state (fixed crop), a box per state, and 2 trend lines per state (indicator+Yield,
  Area+CWU) - matches picking e.g. Assam + Bihar with Rice.
- **2+ crops selected** (regardless of state count) -> compares **crops**: one map
  per crop (district-level, zoomed to the single state if one is picked, or
  nationwide if "All India" is picked), a box per crop, 2 trend lines per crop.
- **1 state, 1 crop** -> falls back to a single view (no real comparison, but still
  under the "Spatial Variation" header/layout).
- More than 4 selections are truncated to the first 4, to keep the stacked maps and
  multi-line charts legible - a note appears on screen when this happens.

Trends and Comparison use a mode-selector (styled to look like tabs) instead of
Streamlit's native tabs, because they need genuinely different sidebars - with
native tabs, every tab's code runs on every script pass regardless of which is
visually selected, so two different sidebar forms would both render into the
sidebar at once. A radio button only executes the branch that's actually chosen.

## A real bug this fixed: crop names with inconsistent casing across years

The raw `crop_data_calculated_final_3.csv` labels several crops inconsistently
across years - most obviously **"Rice"** in 1999 only, then **"rice"** (lowercase)
for 2000-2022, and **"Sugar"** in 1999 vs **"Sugarcane"** for 2000-2022 - with
**zero year overlap** between the two spellings in every case, confirming these
are the same crop renamed partway through, not genuinely different crops.
Left unmerged, whichever spelling "won" the post-1999 years effectively had no
data for almost the entire time range - which is exactly what made Rice (and
Sugarcane, and others) look broken: blank map, a degenerate single-point trend
chart.

`data_prep/build_datasets.py` fixes this in two steps:
1. Title-cases every crop name (merges pure-casing splits: Rice/rice, Other
   Cereals/cereals).
2. Applies an explicit `CROP_MERGE_MAP` for the remaining spelling/wording
   variants confirmed to have zero year overlap: Arhar->Arhar/Tur, Dry
   Chilli->Dry Chillies, Grams->Gram, Ground Nut->Groundnut, Sesseme->Sesamum,
   Soya->Soyabean, Sugar->Sugarcane, Urd->Urad.

This brought the crop count from 78 raw labels down to 69 real, distinct crops,
each with the full 1999-2022 range. If you load new raw data later and a crop
looks "broken for most years but fine for one," check for this exact pattern
first - group by crop name and look at each one's min/max year and row count,
the way this fix was diagnosed.

## Deploying for free — Streamlit Community Cloud

This is the easiest free option and needs no server knowledge.

1. **Create a free GitHub account** (skip if you have one) at github.com.
2. **Create a new repository** (e.g. `wpatlas-webapp`) and upload this whole
   `wpatlas_webapp` folder into it (drag-and-drop works fine on github.com, or
   use GitHub Desktop if you prefer a GUI over the command line).
3. Go to **share.streamlit.io** and sign in with your GitHub account.
4. Click **"New app"**, pick your repository, set:
   - Branch: `main`
   - Main file path: `app.py`
5. Click **Deploy**. After a minute or two you'll get a public link like
   `https://your-app-name.streamlit.app` — share that link for training sessions.

That's it — no server to manage, no credit card, no database. Every time you
push a change to the GitHub repo, the deployed app updates automatically.

### A note on repo size
`app_data/` is about 38 MB total, well within GitHub's free limits (and
Streamlit Cloud's). If you later swap in a much bigger raw dataset, re-run
`build_datasets.py`, don't upload the raw multi-hundred-MB CSV itself.

## Extending it later
- To add a new indicator: add one line to `INDICATORS` in `indicators.py`.
- To refresh with new yearly data: replace the raw CSV path in
  `data_prep/build_datasets.py`, re-run it, and commit the updated `app_data/` files.
- To add **river-basin scale**: you'll need a river-basin/sub-basin boundary
  shapefile plus a district→basin lookup table, then a `RiverBasin` branch
  alongside `District`/`State`/`National` in `common.py` and both tab files.
- To add the **Scenarios** and **Nexus** components (matching
  `scenario_output_calculations()` / `nexus_calculations()` in your original
  `calculations_updated_tcwu.py`), you'll need district-level: `POPULATION`,
  `PER_CAP` (consumption), `GWAVAILABILITY`, `NGWIRA` (groundwater irrigation
  share), `DH_M` (pumping head), and `WT_EFF` (pump efficiency). Once available,
  add them to `data_prep/build_datasets.py` and create `tab_scenarios.py` /
  `tab_nexus.py` following the same pattern as `tab_comparisons.py`.
