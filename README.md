# India Water Productivity & Water Footprint Atlas

A lightweight, no-database web app that visually matches IWMI's official India
Water Productivity Atlas (https://indiawpatlas.shinyapps.io/wpatlas/), covering
**Trends**, **Comparison**, and **Scenarios** at country/state/district scale.
Built for training sessions and presentations.

## What's inside

```
wpatlas_webapp/               (deploy this folder's CONTENTS at your repo root - see Deploying below)
├── app.py                     # entrypoint: page setup, mode-selector, wires up all three sections
├── atlas_view.py              # Trends + Comparison: sidebar, map/stats panels
├── tab_trends.py              # thin wrapper around atlas_view (Trends mode)
├── tab_comparisons.py         # thin wrapper around atlas_view (Comparison mode)
├── tab_scenarios.py           # Scenarios: sidebar, baseline/alternative editable tables, Output panel
├── common.py                  # data loading, CSS/navbar styling, quantile map classification
├── indicators.py              # indicator names, units, short codes shown in the sidebar/legend
├── requirements.txt           # the packages needed to run it
├── .streamlit/config.toml     # forces a light theme (Streamlit Cloud can otherwise default to dark)
├── app_data/                  # pre-processed data the app reads directly (no DB!)
│   ├── district_data.parquet / state_data.parquet / state_data_for_map.parquet / national_data.parquet
│   ├── districts.geojson / states.geojson / state_crosswalk.json
│   └── scenario_baseline.parquet / scenario_drivers.parquet
├── data_prep/
│   ├── build_datasets.py         # produces the Trends/Comparison app_data files
│   └── build_scenario_data.py    # produces the Scenario app_data files
└── README.md
```

There is **no database** and **no separate backend server**. Streamlit is both the
backend and frontend: it reads the `app_data/` files straight off disk each time
the app starts, and everything is cached in memory after that.

**Important:** `app.py` and everything next to it must sit at your GitHub repo's
ROOT (not inside a subfolder). Streamlit Cloud resolves `.streamlit/config.toml`
and the working directory relative to the repo root, and putting the app in a
subfolder caused real bugs earlier (`ModuleNotFoundError`, the theme not applying).

## Does it calculate indicators dynamically?

**Not from raw formulas — but yes, dynamically in the sense that matters.**
Every Trends/Comparison indicator was calculated **once**, ahead of time, using
the same logic as `calculations_updated_tcwu.py`, via `data_prep/build_datasets.py`.
The Scenarios tab is different: baseline values are precomputed the same way, but
editing any cell in the "Alternative scenario" table **does** re-run the water/
productivity formulas live, right there in your browser session (see below).

## Trends & Comparison

The sidebar controls are named to match the official app:

| Control | What it does here |
|---|---|
| Primary unit of analysis | Fixed to "Administrative level" (River basin needs a boundary file not yet provided) |
| Secondary unit of analysis | "All India" or a specific state — zooms the district map, sets scope for the trend charts |
| Tertiary unit of analysis | "Country wise" / "State wise" / "District wise" — the map's resolution |
| Indicator | All 22 indicators from the calculation scripts, in one flat dropdown |
| Crop(s) | Any of the crops, or "All crops" (a true recomputed aggregate, not an average of ratios) |
| Year(s) | Any year 1999-2022 |

The map uses a 4-class quantile legend (red -> orange -> light green -> dark
green) plus gray "Data not available/reliable", matching the reference app.

**Comparison** lets you multi-select **State(s)** and **Crop(s)** (Trends is
single-select):
- 2+ states, 1 crop -> compares **states**: one map per state, a box per state,
  2 trend lines per state (matches e.g. Assam + Bihar with Rice).
- 2+ crops -> compares **crops** the same way (matches e.g. Rice vs Wheat).
- 1 state, 1 crop -> falls back to a single view.
- More than 4 selections truncate to 4, with an on-screen note.

Trends/Comparison/Scenarios use a mode-selector (styled like tabs, not
Streamlit's native `st.tabs`) because each needs a genuinely different sidebar.
With native tabs, every tab's code runs on every script pass regardless of which
is visually selected, so different sidebar forms would all render at once. A
radio button only executes the branch that's actually chosen.

## Scenarios

Pick a State and District (a mini map highlights it), and you get:
- **Baseline data (2018-2020)**: the district's top 5-6 crops by area, one row
  per crop-season (Kharif/Rabi/Zaid), with SFIRA/GWIRA/RFA/IRYLD/RFYLD/
  efficiencies/Price/PWP.
- **Alternative scenario**: the same table, editable - change any cell to test
  a what-if. **Crop Diversification** in the sidebar adds a minor crop not in
  the top 5-6 as an extra row.
- **Other drivers**: Population and GW availability, editable.
- **Output**: five metrics, Baseline vs your edited Alternative, recomputed live.

**What's validated vs. not**, checked numerically against the reference
screenshot's Adilabad example:

| Output metric | This app | Reference | Status |
|---|---|---|---|
| PWP (per crop-season) | 0.48 / 0.77 | 0.46 / 0.76 | close match |
| Groundwater WFP % of extractable resources | 12.5% | 14% | close match |
| Groundwater withdrawals % of extractable resources | 19.2% | 22% | close match |
| Irrigation WFP % of total | 42.6% | 19% | **not matched - see below** |
| Calorie / Protein supply % of consumption | -99.9% / -99.7% | -49% / -31% | **not matched - see below** |

The water-related rows were nailed down by numerically back-solving the correct
volume-formula unit constant (the original script's literal `SFIRA*10000*
IRCWU_MM/1e9` turned out to be right for MCM-scale comparisons against GW
availability - a `/1e6` version matched PWP by what turned out to be
coincidence, and was 1000x wrong once compared against GW availability instead).

**Irrigation WFP %** is off because the season-level rainfed water depth
(`RFCWU_MM`) had to be *derived* as `TCWU_MM - IRCWU_MM` — no directly-provided
rainfed depth column exists in `crop_data_integrated_final_1__2_.csv` — and that
derivation likely doesn't exactly match whatever the reference app used.

**Calorie/Protein supply** couldn't be reconciled: the -49% and -31% targets
needed *different* correction factors when back-solving (1706x vs 5068x using
just the top-6 crops, still inconsistent at ~4072x vs ~7038x using the district's
full crop list) — a single wrong unit constant can't explain that, which points
to `CAL` and `PRO` in `crop_data_integrated_final_1__2_.csv` using different
unit conventions than assumed. These two Output rows are shown with an
on-screen `*` caveat rather than hidden, since the formula structure is at
least correct even if the scale isn't verified.

**If you can get a small worked example** from whoever built the original tool —
their own baseline/alternative table for one more district, with intermediate
SIRWFP/GWIRWFP/RFWFP/CONS_CAL/CONS_PRO values (not just final rounded
percentages) — that would let the remaining two rows be properly calibrated.

Also: the exact top-6 crop list for a district may not match the reference
app's (e.g. its Adilabad example includes Cotton; this dataset's doesn't) -
likely a difference in administrative-boundary vintage (undivided Andhra
Pradesh vs. present-day Telangana-split boundaries) or exact averaging method.

Nexus (the 4th component of the reference app) still needs `DH_M` (pumping
head) and `WT_EFF` (pump efficiency) for its energy-cost calculation - not in
any file provided yet.

## Why not PostgreSQL/PostGIS?

A training/presentation tool with fixed underlying data doesn't need a live
database server running around the clock, or a second thing to deploy and keep
in sync. All the calculations were run **once**, ahead of time, by the two
`data_prep/` scripts, and saved as compact files the app just reads.

## Data notes

- Main Trends/Comparison source: `crop_data_calculated_final_3.csv` (district x
  crop x year, 1999-2022).
- An **"ALL CROPS"** option is a true recomputed aggregate (summed volumes,
  ratios recalculated), not a misleading average-of-ratios.
- District boundaries matched to the data by (state, district) name: 595/603
  pairs matched automatically (98.7%); a handful of rows in the raw CSV have
  mismatched state/district labels and won't appear on the map.
- State boundaries: Dadra & Nagar Haveli + Daman & Diu share one polygon; the
  two "Jammu and Kashmir" rows in the raw data are merged for the map only.
- **Crop-name bug fixed**: several crops were labeled inconsistently across
  years with zero year-overlap between spellings (e.g. "Rice" only in 1999,
  "rice" for 2000-2022; "Sugar" vs "Sugarcane"; 8 pairs total) - left unmerged,
  the "losing" spelling had almost no data. `build_datasets.py` title-cases
  crop names and applies an explicit `CROP_MERGE_MAP` to fix this. Brought the
  crop count from 78 raw labels to 69 real, distinct crops. If new raw data
  looks "broken for most years but fine for one," check for this pattern first.

## Running it locally (optional, to preview before deploying)

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploying for free — Streamlit Community Cloud

1. Create a free GitHub account/repo if you don't have one.
2. Upload every file and folder from inside `wpatlas_webapp/` directly to your
   repo's ROOT (not into a subfolder — see the note above).
3. Go to **share.streamlit.io**, sign in with GitHub, click **New app**, pick
   your repo, set Main file path to `app.py`, click Deploy.
4. Every future `git push` auto-redeploys.

## Extending it later
- New indicator: add one line to `INDICATORS` in `indicators.py`.
- New yearly data: replace the raw CSV path in `data_prep/build_datasets.py`,
  re-run it, commit the updated `app_data/` files.
- River-basin scale: needs a basin boundary shapefile + district->basin lookup,
  then a `RiverBasin` branch alongside `District`/`State`/`National`.
- Nexus tab: needs `DH_M` and `WT_EFF` (see above), then follow the pattern in
  `tab_scenarios.py`.
