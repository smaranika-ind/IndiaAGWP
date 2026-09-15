"""
Builds app_data/scenario_baseline.parquet - the crop x season x district dataset
that powers the Scenario tab, matching the reference IWMI atlas's
"Baseline data (2018-2020)" table (SFIRA/GWIRA/RFA/IRYLD/RFYLD/efficiencies/Price/PWP
per crop-season), plus district-level driver values (NGWIRA, GW availability,
population, RFEff by season) from scenario_data_2.csv.

Formulas replicate scenario_output_calculations() in calculations_updated_tcwu.py
as closely as possible given the inputs actually available. Per-capita consumption
(Con.pc) is not available in any provided file, so the Calorie/Protein-supply
output rows from the reference app are intentionally NOT built here - see README.
"""
import re
import numpy as np
import pandas as pd

INTEGRATED_CSV = "/mnt/user-data/uploads/crop_data_integrated_final_1__2_.csv"
SCENARIO_CSV = "/mnt/user-data/uploads/scenario_data_2.csv"
PER_CAPITA_CSV = "/mnt/user-data/uploads/per_capita_data_2.csv"
OUT_DIR = "/home/claude/wpatlas/app_data"

BASELINE_YEARS = (2018, 2020)
SEASON_LABELS = {1: "Kharif", 2: "Rabi", 3: "Zaid"}
SFIREFF = 40.0   # surface-irrigation efficiency (%), constant per original script
GWIREFF = 65.0   # groundwater-irrigation efficiency (%), constant per original script
TOP_N_CROPS = 6  # "top 5-6 crops with major area" per district, shown by default


def key(s):
    return re.sub(r"\s+", " ", str(s).strip().upper())


def load_per_capita():
    """Reshapes the wide per-capita consumption file (one column per crop) into
    long format (state, district, crop, CONPC), normalizing crop names the same
    way as the main pipeline so they join cleanly."""
    pc = pd.read_csv(PER_CAPITA_CSV)
    pc.columns = [c.strip() for c in pc.columns]
    id_cols = ["state", "district"]
    crop_cols = [c for c in pc.columns if c not in id_cols]
    long_pc = pc.melt(id_vars=id_cols, value_vars=crop_cols, var_name="crop_raw", value_name="CONPC")
    long_pc["state"] = long_pc["state"].astype(str).str.strip()
    long_pc["district"] = long_pc["district"].astype(str).str.strip()
    long_pc["crop"] = long_pc["crop_raw"].str.replace("_", " ", regex=False).str.strip().str.title()
    CROP_MERGE_MAP = {
        "Arhar": "Arhar/Tur", "Dry Chilli": "Dry Chillies", "Grams": "Gram",
        "Ground Nut": "Groundnut", "Sesseme": "Sesamum", "Soya": "Soyabean",
        "Sugar": "Sugarcane", "Urd": "Urad",
    }
    long_pc["crop"] = long_pc["crop"].replace(CROP_MERGE_MAP)
    long_pc["CONPC"] = pd.to_numeric(long_pc["CONPC"], errors="coerce").fillna(0)
    long_pc = long_pc.rename(columns={"state": "STATE", "district": "DISTRICT", "crop": "CROP"})
    # a few crops (e.g. "Rice-Wheat") never appear in per_capita_data_2.csv - fine, they just get 0
    return long_pc.groupby(["STATE", "DISTRICT", "CROP"], as_index=False)["CONPC"].first()


def main():
    print("Loading integrated (season-level) crop data...")
    df = pd.read_csv(INTEGRATED_CSV, low_memory=False)
    df.columns = [c.strip().lower() for c in df.columns]
    df["state"] = df["state"].astype(str).str.strip()
    df["district"] = df["district"].astype(str).str.strip()
    df["crop"] = df["crop"].astype(str).str.strip().str.title()
    # same crop-name cleanup as the main pipeline
    CROP_MERGE_MAP = {
        "Arhar": "Arhar/Tur", "Dry Chilli": "Dry Chillies", "Grams": "Gram",
        "Ground Nut": "Groundnut", "Sesseme": "Sesamum", "Soya": "Soyabean",
        "Sugar": "Sugarcane", "Urd": "Urad",
    }
    df["crop"] = df["crop"].replace(CROP_MERGE_MAP)

    base = df[df["year"].between(*BASELINE_YEARS)].copy()
    print(f"  rows in {BASELINE_YEARS[0]}-{BASELINE_YEARS[1]}: {len(base)}")

    # Average the 3-year baseline window per state/district/crop
    avg_cols = [
        "irha_ssn1", "irha_ssn2", "irha_ssn3", "rfha_ssn1", "rfha_ssn2", "rfha_ssn3",
        "iryld_ssn1", "iryld_ssn2", "iryld_ssn3", "rfyld_ssn1", "rfyld_ssn2", "rfyld_ssn3",
        "ircwu_mm_ssn1", "ircwu_mm_ssn2", "ircwu_mm_ssn3",
        "tcwu_mm_ssn1", "tcwu_mm_ssn2", "tcwu_mm_ssn3",
        "price_st", "cal", "pro", "fat",
    ]
    grp = base.groupby(["state", "district", "crop"], as_index=False)[avg_cols].mean()

    # ---- reshape wide (per-season columns) -> long (one row per crop-season) ----
    rows = []
    for ssn in (1, 2, 3):
        sub = grp[[
            "state", "district", "crop",
            f"irha_ssn{ssn}", f"rfha_ssn{ssn}", f"iryld_ssn{ssn}", f"rfyld_ssn{ssn}",
            f"ircwu_mm_ssn{ssn}", f"tcwu_mm_ssn{ssn}", "price_st", "cal", "pro", "fat",
        ]].copy()
        sub.columns = [
            "STATE", "DISTRICT", "CROP", "IRHA", "RFHA", "IRYLD", "RFYLD",
            "IRCWU_MM", "TCWU_MM", "PRICE_ST", "CAL", "PRO", "FAT",
        ]
        sub["SEASON"] = SEASON_LABELS[ssn]
        rows.append(sub)
    long_df = pd.concat(rows, ignore_index=True)
    long_df = long_df.fillna(0)
    # keep only crop-seasons that actually have some area (matches reference app
    # only showing e.g. Cotton-Kharif, not Cotton-Rabi, when Cotton isn't grown in Rabi)
    long_df = long_df[(long_df["IRHA"] > 0) | (long_df["RFHA"] > 0)].copy()
    long_df["RFCWU_MM"] = (long_df["TCWU_MM"] - long_df["IRCWU_MM"]).clip(lower=0)

    print(f"  crop-season rows with area > 0: {len(long_df)}")

    # ---- district-level scenario drivers (NGWIRA, GW availability, population, RFEff) ----
    print("Loading district-level scenario drivers...")
    scen = pd.read_csv(SCENARIO_CSV).drop_duplicates(subset=["state", "district"])
    scen["state"] = scen["state"].astype(str).str.strip()
    scen["district"] = scen["district"].astype(str).str.strip()
    scen = scen.rename(columns={
        "state": "STATE", "district": "DISTRICT", "ngwira": "NGWIRA",
        "gwavailability": "GWAVAILABILITY_RAW", "population": "POPULATION",
        "rf_use_ssn1": "RFEFF_KHARIF_FRAC", "rf_use_ssn2": "RFEFF_RABI_FRAC",
        "gwcwu": "GWCWU",
    })
    # matches the original script's `GWAVAILABILITY = df['GWAVAILABILITY'].unique()/100`
    scen["GWAVAILABILITY_MCM"] = scen["GWAVAILABILITY_RAW"] / 100.0

    long_df = long_df.merge(
        scen[["STATE", "DISTRICT", "NGWIRA", "GWAVAILABILITY_MCM", "POPULATION",
              "RFEFF_KHARIF_FRAC", "RFEFF_RABI_FRAC", "GWCWU"]],
        on=["STATE", "DISTRICT"], how="left",
    )
    missing_drivers = long_df["NGWIRA"].isna().sum()
    if missing_drivers:
        print(f"  WARNING: {missing_drivers} crop-season rows have no matching district driver data")
    long_df[["NGWIRA", "GWAVAILABILITY_MCM", "POPULATION", "RFEFF_KHARIF_FRAC",
              "RFEFF_RABI_FRAC", "GWCWU"]] = long_df[[
        "NGWIRA", "GWAVAILABILITY_MCM", "POPULATION", "RFEFF_KHARIF_FRAC",
        "RFEFF_RABI_FRAC", "GWCWU"]].fillna(0)

    long_df["RFEFF"] = np.select(
        [long_df["SEASON"] == "Kharif", long_df["SEASON"] == "Rabi"],
        [long_df["RFEFF_KHARIF_FRAC"] * 100, long_df["RFEFF_RABI_FRAC"] * 100],
        default=long_df["RFEFF_RABI_FRAC"] * 100,  # Zaid: reuse Rabi's RFEff (rare crops)
    )
    long_df["SFIREFF"] = SFIREFF
    long_df["GWIREFF"] = GWIREFF

    # ---- area split (matches original scenario_baseline_calculations logic) ----
    long_df["GWIRA"] = long_df["IRHA"] * long_df["NGWIRA"]
    long_df["SFIRA"] = long_df["IRHA"] - long_df["GWIRA"]

    print("Loading per-capita consumption data...")
    per_capita = load_per_capita()
    long_df = long_df.merge(per_capita, on=["STATE", "DISTRICT", "CROP"], how="left")
    long_df["CONPC"] = long_df["CONPC"].fillna(0)

    long_df = compute_row_outputs(long_df)

    long_df["STATE_KEY"] = long_df["STATE"].map(key)
    long_df["DISTRICT_KEY"] = long_df["DISTRICT"].map(key)

    for c in ["IRHA", "RFHA", "IRYLD", "RFYLD", "IRCWU_MM", "TCWU_MM", "RFCWU_MM",
              "PRICE_ST", "CAL", "PRO", "FAT", "NGWIRA", "GWAVAILABILITY_MCM",
              "POPULATION", "RFEFF", "SFIREFF", "GWIREFF", "GWIRA", "SFIRA",
              "SIRWFP", "GWIRWFP", "RFWFP", "TCWU_VOL_MCM", "GW_WITHDRAWALS",
              "PROD_KG", "USD", "PWP", "EWP", "CONPC", "PROD_CAL", "PROD_PRO"]:
        long_df[c] = long_df[c].astype("float32")

    out_cols = ["STATE", "DISTRICT", "STATE_KEY", "DISTRICT_KEY", "CROP", "SEASON",
                "SFIRA", "GWIRA", "RFHA", "IRYLD", "RFYLD", "SFIREFF", "GWIREFF", "RFEFF",
                "PRICE_ST", "PWP", "IRHA", "IRCWU_MM", "TCWU_MM", "RFCWU_MM",
                "NGWIRA", "GWAVAILABILITY_MCM", "POPULATION", "CONPC", "CAL", "PRO",
                "SIRWFP", "GWIRWFP", "RFWFP", "TCWU_VOL_MCM", "GW_WITHDRAWALS",
                "PROD_KG", "USD", "EWP", "PROD_CAL", "PROD_PRO"]
    long_df = long_df[out_cols]

    # rank crops by total area within each district, for the "top N" default view
    area_rank = (
        long_df.groupby(["STATE", "DISTRICT", "CROP"])
        .apply(lambda g: (g["SFIRA"] + g["GWIRA"] + g["RFHA"]).sum())
        .rename("TOTAL_AREA").reset_index()
    )
    area_rank["RANK"] = area_rank.groupby(["STATE", "DISTRICT"])["TOTAL_AREA"] \
        .rank(method="first", ascending=False)
    long_df = long_df.merge(area_rank[["STATE", "DISTRICT", "CROP", "RANK"]],
                             on=["STATE", "DISTRICT", "CROP"], how="left")

    long_df.to_parquet(f"{OUT_DIR}/scenario_baseline.parquet", index=False)
    print(f"  scenario_baseline rows: {len(long_df)}")

    # district-level driver reference table (population, GW availability - shown
    # in the "Other drivers" panel, one row per district)
    drivers = scen[["STATE", "DISTRICT", "NGWIRA", "GWAVAILABILITY_MCM", "POPULATION", "GWCWU"]].copy()
    drivers["STATE_KEY"] = drivers["STATE"].map(key)
    drivers["DISTRICT_KEY"] = drivers["DISTRICT"].map(key)
    drivers.to_parquet(f"{OUT_DIR}/scenario_drivers.parquet", index=False)
    print(f"  scenario_drivers rows: {len(drivers)}")
    print("DONE")


def compute_row_outputs(df):
    """Per crop-season row: replicate scenario_output_calculations()'s volume/PWP
    formulas. SIRWFP/GWIRWFP/RFWFP use the literal /1e9 divisor from the original
    script, which (validated numerically against the reference screenshot) gives
    genuine MCM-scale volumes - matching GWAVAILABILITY_MCM for the groundwater
    stress metrics. PWP then converts MCM->m3 properly (x1e6) rather than the
    original script's confusing "/1000", which only worked by coincidence for
    plain PWP and gave wildly wrong (1000x) results once compared against
    GW availability."""
    df = df.copy()
    df["SIRWFP"] = df["SFIRA"] * 10000 * df["IRCWU_MM"] / 1e9
    df["GWIRWFP"] = df["GWIRA"] * 10000 * df["IRCWU_MM"] / 1e9
    df["RFWFP"] = (df["GWIRA"] + df["SFIRA"] + df["RFHA"]) * 10000 * df["RFCWU_MM"] / 1e9
    df["TCWU_VOL_MCM"] = df["SIRWFP"] + df["GWIRWFP"] + df["RFWFP"]
    df["GW_WITHDRAWALS"] = np.where(df["GWIREFF"] > 0, df["GWIRWFP"] / (df["GWIREFF"] / 100), 0)

    df["PROD_KG"] = (df["IRHA"] * df["IRYLD"] + df["RFHA"] * df["RFYLD"]) * 1000
    df["USD"] = df["PROD_KG"] * df["PRICE_ST"] / 1e6

    df["PWP"] = np.where(df["TCWU_VOL_MCM"] > 0, df["PROD_KG"] / (df["TCWU_VOL_MCM"] * 1e6), 0)
    df["EWP"] = np.where(df["TCWU_VOL_MCM"] > 0, df["USD"] / df["TCWU_VOL_MCM"], 0)

    # per-crop nutrition totals (for the Calorie/Protein supply-vs-consumption
    # Output rows) - CAL/PRO are per-kg-ish rates from the integrated file.
    # NOTE: this specific pair of Output rows is UNVALIDATED - see README. The
    # water-related Output rows (PWP, GW WFP %, GW withdrawals %) were checked
    # numerically against the reference screenshot and matched well; Calorie/
    # Protein surplus could not be reconciled to the reference's -49%/-31%
    # example despite testing several unit-scale hypotheses for CAL/PRO/population,
    # so these numbers should be treated as illustrative, not verified.
    df["PROD_CAL"] = df["PROD_KG"] * df["CAL"]
    df["PROD_PRO"] = df["PROD_KG"] * df["PRO"]

    df = df.replace([np.inf, -np.inf], 0).fillna(0)
    return df


if __name__ == "__main__":
    main()
