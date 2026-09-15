"""
One-time data preparation pipeline for the WP Atlas Streamlit app.
Reads the raw crop-district-year indicator CSV + shapefiles, builds:
  - district_data.parquet   (district x crop x year, + 'ALL CROPS' aggregate)
  - state_data.parquet      (state x crop x year, + 'ALL CROPS' aggregate)
  - national_data.parquet   (national x crop x year, + 'ALL CROPS' aggregate)
  - districts.geojson       (simplified, WGS84, joined key = STATE_KEY/DIST_KEY)
  - states.geojson          (simplified, WGS84, joined key = STATE_KEY)
Run once; outputs go to /home/claude/wpatlas/app_data/
"""
import re
import pandas as pd
import numpy as np
import geopandas as gpd

RAW_CSV = "/mnt/user-data/uploads/crop_data_calculated_final_3.csv"
DIST_SHP = "/mnt/user-data/uploads/districts_shapefile_2.shp"
STATE_SHP = "/mnt/user-data/uploads/india_states.shp"
OUT_DIR = "/home/claude/wpatlas/app_data"

VOL_COLS = ["THA_TOL","IRHA_TOL","RFHA_TOL","PROD_TOL","TCWU_TOL","IRCWU_TOL","RFCWU_TOL",
            "USD_TOL","NCFP_TOL","NPFP_TOL","NFFP_TOL"]

def key(s):
    return re.sub(r"\s+", " ", str(s).strip().upper())

def recompute_ratios(df):
    """Recompute all ratio-based indicators from summed volume columns."""
    df = df.copy()
    THA, PROD, TCWU, IRCWU, RFCWU = df["THA_TOL"], df["PROD_TOL"], df["TCWU_TOL"], df["IRCWU_TOL"], df["RFCWU_TOL"]
    USD, NCFP, NPFP, NFFP = df["USD_TOL"], df["NCFP_TOL"], df["NPFP_TOL"], df["NFFP_TOL"]

    df["TYLD_TOL"] = np.where(THA > 0, PROD / THA, 0)
    df["PWP_TOL"]  = np.where(TCWU > 0, (PROD / TCWU) / 1000.0, 0)
    df["EWP_TOL"]  = np.where(TCWU > 0, USD / TCWU, 0)
    df["NCWP_TOL"] = np.where(TCWU > 0, NCFP / TCWU, 0)
    df["NPWP_TOL"] = np.where(TCWU > 0, NPFP / TCWU, 0)
    df["NFWP_TOL"] = np.where(TCWU > 0, NFFP / TCWU, 0)

    df["TWFP_TOL"]   = np.where(PROD > 0, TCWU  * 1e6 / PROD, 0)
    df["TBLWFP_TOL"] = np.where(PROD > 0, IRCWU * 1e6 / PROD, 0)
    df["TGRWFP_TOL"] = np.where(PROD > 0, RFCWU * 1e6 / PROD, 0)

    df["TCWFP_TOL"] = np.where(df["NCWP_TOL"] > 0, 1 / df["NCWP_TOL"], 0)
    df["TPWFP_TOL"] = np.where(df["NPWP_TOL"] > 0, 1 / df["NPWP_TOL"], 0)
    df["TFWFP_TOL"] = np.where(df["NFWP_TOL"] > 0, 1 / df["NFWP_TOL"], 0)

    twfp = df["TWFP_TOL"]
    df["TBLCWFP_TOL"] = np.where(twfp > 0, df["TCWFP_TOL"] * (df["TBLWFP_TOL"] / twfp), 0)
    df["TGRCWFP_TOL"] = np.where(twfp > 0, df["TCWFP_TOL"] * (df["TGRWFP_TOL"] / twfp), 0)
    df["TBLPWFP_TOL"] = np.where(twfp > 0, df["TPWFP_TOL"] * (df["TBLWFP_TOL"] / twfp), 0)
    df["TGRPWFP_TOL"] = np.where(twfp > 0, df["TPWFP_TOL"] * (df["TGRWFP_TOL"] / twfp), 0)
    df["TBLFWFP_TOL"] = np.where(twfp > 0, df["TFWFP_TOL"] * (df["TBLWFP_TOL"] / twfp), 0)
    df["TGRFWFP_TOL"] = np.where(twfp > 0, df["TFWFP_TOL"] * (df["TGRWFP_TOL"] / twfp), 0)

    df = df.replace([np.inf, -np.inf], 0).fillna(0)
    return df

FINAL_COLS = VOL_COLS + ["TYLD_TOL","PWP_TOL","EWP_TOL","NCWP_TOL","NPWP_TOL","NFWP_TOL",
    "TWFP_TOL","TBLWFP_TOL","TGRWFP_TOL","TCWFP_TOL","TPWFP_TOL","TFWFP_TOL",
    "TBLCWFP_TOL","TGRCWFP_TOL","TBLPWFP_TOL","TGRPWFP_TOL","TBLFWFP_TOL","TGRFWFP_TOL"]

def add_all_crops(df, group_cols):
    """Given a detail df (has CROP col) at some geo level, append an 'ALL CROPS' aggregate row per group."""
    summed = df.groupby(group_cols, as_index=False)[VOL_COLS].sum()
    summed = recompute_ratios(summed)
    summed["CROP"] = "ALL CROPS"
    summed = summed[group_cols + ["CROP"] + FINAL_COLS]
    out = pd.concat([df[group_cols + ["CROP"] + FINAL_COLS], summed], ignore_index=True)
    for c in FINAL_COLS:
        out[c] = out[c].astype("float32")
    return out

def main():
    print("Loading raw CSV...")
    df = pd.read_csv(RAW_CSV, low_memory=False)
    df.columns = [c.strip() for c in df.columns]
    df["STATE"] = df["state"].astype(str).str.strip()
    df["DISTRICT"] = df["district"].astype(str).str.strip()
    df["CROP"] = df["crop"].astype(str).str.strip()
    df["YEAR"] = df["year"].astype(int)
    df["STATE_KEY"] = df["STATE"].map(key)
    df["DISTRICT_KEY"] = df["DISTRICT"].map(key)

    keep = ["STATE","DISTRICT","CROP","YEAR","STATE_KEY","DISTRICT_KEY"] + FINAL_COLS
    df = df[keep]
    for c in FINAL_COLS:
        df[c] = df[c].astype("float32")

    # ---------- DISTRICT LEVEL ----------
    print("Building district-level dataset...")
    dist_detail = df.copy()
    dist_all = add_all_crops(dist_detail, ["STATE","DISTRICT","STATE_KEY","DISTRICT_KEY","YEAR"])
    dist_all.to_parquet(f"{OUT_DIR}/district_data.parquet", index=False)
    print("  district rows:", len(dist_all))

    # ---------- STATE LEVEL ----------
    print("Building state-level dataset...")
    state_detail = df.groupby(["STATE","STATE_KEY","CROP","YEAR"], as_index=False)[VOL_COLS].sum()
    state_detail = recompute_ratios(state_detail)
    state_all = add_all_crops(state_detail, ["STATE","STATE_KEY","YEAR"])
    state_all.to_parquet(f"{OUT_DIR}/state_data.parquet", index=False)
    print("  state rows:", len(state_all))

    # ---------- NATIONAL LEVEL ----------
    print("Building national-level dataset...")
    nat_detail = df.groupby(["CROP","YEAR"], as_index=False)[VOL_COLS].sum()
    nat_detail = recompute_ratios(nat_detail)
    nat_all = add_all_crops(nat_detail, ["YEAR"])
    nat_all.to_parquet(f"{OUT_DIR}/national_data.parquet", index=False)
    print("  national rows:", len(nat_all))

    # ---------- GEOMETRIES ----------
    print("Processing district shapefile...")
    gdist = gpd.read_file(DIST_SHP)
    gdist = gdist.dropna(subset=["District","State"])
    gdist["STATE_KEY"] = gdist["State"].map(key)
    gdist["DISTRICT_KEY"] = gdist["District"].map(key)
    gdist = gdist[["STATE_KEY","DISTRICT_KEY","State","District","geometry"]]
    gdist = gdist.to_crs(4326)
    gdist["geometry"] = gdist["geometry"].simplify(0.01, preserve_topology=True)
    gdist = gdist[gdist.is_valid | gdist.geometry.notna()]
    gdist.to_file(f"{OUT_DIR}/districts.geojson", driver="GeoJSON")
    print("  district features:", len(gdist))

    print("Processing state shapefile...")
    gstate = gpd.read_file(STATE_SHP)
    gstate = gstate.dropna(subset=["State_Name"])
    gstate["STATE_KEY_SHP"] = gstate["State_Name"].map(key)
    # crosswalk data STATE_KEY -> shapefile STATE_KEY_SHP
    crosswalk = {
        "ANDAMAN AND NICOBAR ISLANDS": "ANDAMAN & NICOBAR",
        "CHHATTISGARH": "CHHATTISHGARH",
        "DADRA AND NAGAR HAVELI": "DAMAN AND DIU AND DADRA AND NAGAR HAVELI",
        "DAMAN AND DIU": "DAMAN AND DIU AND DADRA AND NAGAR HAVELI",
        "JAMMU AND KASHMIR1": "JAMMU AND KASHMIR",
        "TAMIL NADU": "TAMILNADU",
        "UTTARANCHAL": "UTTARAKHAND",
    }
    gstate = gstate.to_crs(4326)
    gstate["geometry"] = gstate["geometry"].simplify(0.01, preserve_topology=True)
    gstate = gstate[["STATE_KEY_SHP","State_Name","geometry"]]
    gstate.to_file(f"{OUT_DIR}/states.geojson", driver="GeoJSON")

    import json
    with open(f"{OUT_DIR}/state_crosswalk.json","w") as f:
        json.dump(crosswalk, f, indent=2)
    print("  state features:", len(gstate))

    # ---------- STATE DATA RE-KEYED TO SHAPEFILE GEOMETRY (merges split UTs) ----------
    print("Building state-for-map dataset (merged to shapefile geometry keys)...")
    state_all["STATE_KEY_SHP"] = state_all["STATE_KEY"].map(lambda k: crosswalk.get(k, k))
    map_group_cols = ["STATE_KEY_SHP", "CROP", "YEAR"]
    state_map = state_all.groupby(map_group_cols, as_index=False)[VOL_COLS].sum()
    state_map = recompute_ratios(state_map)
    for c in FINAL_COLS:
        state_map[c] = state_map[c].astype("float32")
    state_map.to_parquet(f"{OUT_DIR}/state_data_for_map.parquet", index=False)
    print("  state-for-map rows:", len(state_map))

    print("DONE")

if __name__ == "__main__":
    main()
