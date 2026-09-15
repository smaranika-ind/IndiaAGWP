import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from common import load_district_geojson, panel_open, panel_close, key

SCENARIO_DATA_DIR = "app_data"
DISPLAY_COLS = ["CROP", "SEASON", "SFIRA", "GWIRA", "RFHA", "IRYLD", "RFYLD",
                "SFIREFF", "GWIREFF", "RFEFF", "PRICE_ST", "PWP"]
DISPLAY_LABELS = {
    "CROP": "Crop", "SEASON": "Season", "SFIRA": "SFIRA", "GWIRA": "GWIRA",
    "RFHA": "RFA", "IRYLD": "IRYLD", "RFYLD": "RFYLD", "SFIREFF": "SFIREff",
    "GWIREFF": "GWIREff", "RFEFF": "RFEff", "PRICE_ST": "Price", "PWP": "PWP",
}
EDITABLE_COLS = ["SFIRA", "GWIRA", "RFHA", "IRYLD", "RFYLD", "PRICE_ST"]
TOP_N_DEFAULT = 6


@st.cache_data
def load_scenario_baseline():
    return pd.read_parquet(f"{SCENARIO_DATA_DIR}/scenario_baseline.parquet")


@st.cache_data
def load_scenario_drivers():
    return pd.read_parquet(f"{SCENARIO_DATA_DIR}/scenario_drivers.parquet")


def render_sidebar_controls_scenario():
    base_df = load_scenario_baseline()
    all_states = sorted(base_df["STATE"].unique().tolist())

    st.sidebar.markdown('<div class="sidebar-header">State &amp; District Selection</div>',
                         unsafe_allow_html=True)
    # State and District are reactive (not inside a form) so picking a new state
    # immediately refreshes the district list to match - putting both in one form
    # meant the district dropdown kept showing the PREVIOUS state's districts
    # until after submit, since form-bound values only update on submit.
    state = st.sidebar.selectbox("State", all_states, key="scn_state")
    districts = sorted(base_df[base_df["STATE"] == state]["DISTRICT"].unique().tolist())
    district = st.sidebar.selectbox("District", districts, key="scn_district")
    if st.sidebar.button("Update (reset what-if edits)", key="scn_update_btn"):
        scope_key = f"{state}||{district}"
        st.session_state.pop(f"scn_editor_{scope_key}", None)
        st.session_state.get("scn_added_rows", {}).pop(scope_key, None)

    _render_mini_district_map(state, district)

    st.sidebar.markdown('<div class="sidebar-header">Crop Diversification</div>',
                         unsafe_allow_html=True)
    dist_all_crops = base_df[(base_df["STATE"] == state) & (base_df["DISTRICT"] == district)]
    all_crop_options = sorted(dist_all_crops["CROP"].unique().tolist())
    add_crop = st.sidebar.selectbox("Crop(s)", all_crop_options, key="scn_add_crop")
    seasons_for_crop = sorted(dist_all_crops[dist_all_crops["CROP"] == add_crop]["SEASON"].unique().tolist())
    add_season = st.sidebar.selectbox("Season", seasons_for_crop, key="scn_add_season")
    if st.sidebar.button("Add crop", key="scn_add_crop_btn"):
        st.session_state.setdefault("scn_added_rows", {})
        scope_key = f"{state}||{district}"
        added = st.session_state["scn_added_rows"].setdefault(scope_key, set())
        added.add((add_crop, add_season))

    st.sidebar.markdown('<div class="sidebar-header">Abbreviations</div>', unsafe_allow_html=True)
    st.sidebar.caption(
        "**SFIRA** - Surface Irrigated Area (HA)  \n"
        "**GWIRA** - Groundwater Irrigated Area (HA)  \n"
        "**RFA** - Rainfed Area (HA)  \n"
        "**IRYLD / RFYLD** - Irrigated / Rainfed Yield (t/ha)  \n"
        "**SFIREff / GWIREff / RFEff** - Surface / Groundwater / Rainfall use efficiency (%)  \n"
        "**PWP** - Physical Water Productivity (kg/m\u00b3)"
    )

    return {"state": state, "district": district}


def _render_mini_district_map(state, district):
    gj = load_district_geojson()
    skey = key(state)
    features = [f for f in gj["features"] if f["properties"]["STATE_KEY"] == skey]
    if not features:
        return
    sub_gj = {"type": "FeatureCollection", "features": features}
    dkey = key(district)
    rows = [{"JOIN_KEY": f["properties"]["JOIN_KEY"],
              "SELECTED": "Selected" if f["properties"]["DISTRICT_KEY"] == dkey else "Other"}
             for f in features]
    plot_df = pd.DataFrame(rows)
    fig = px.choropleth(
        plot_df, geojson=sub_gj, locations="JOIN_KEY", featureidkey="properties.JOIN_KEY",
        color="SELECTED", color_discrete_map={"Selected": "#d1382d", "Other": "#d9d9d9"},
    )
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=220, showlegend=False,
                       paper_bgcolor="white", plot_bgcolor="white")
    st.sidebar.plotly_chart(fig, use_container_width=True, key=f"scn_minimap_{state}_{district}")


def _compute_row_outputs(df):
    df = df.copy()
    df["SIRWFP"] = df["SFIRA"] * 10000 * df["IRCWU_MM"] / 1e9
    df["GWIRWFP"] = df["GWIRA"] * 10000 * df["IRCWU_MM"] / 1e9
    df["RFWFP"] = (df["GWIRA"] + df["SFIRA"] + df["RFHA"]) * 10000 * df["RFCWU_MM"] / 1e9
    df["TCWU_VOL_MCM"] = df["SIRWFP"] + df["GWIRWFP"] + df["RFWFP"]
    df["GW_WITHDRAWALS"] = np.where(df["GWIREFF"] > 0, df["GWIRWFP"] / (df["GWIREFF"] / 100), 0)
    df["PROD_KG"] = (df["SFIRA"] + df["GWIRA"]) * df["IRYLD"] * 1000 + df["RFHA"] * df["RFYLD"] * 1000
    df["USD"] = df["PROD_KG"] * df["PRICE_ST"] / 1e6
    df["PWP"] = np.where(df["TCWU_VOL_MCM"] > 0, df["PROD_KG"] / (df["TCWU_VOL_MCM"] * 1e6), 0)
    df["PROD_CAL"] = df["PROD_KG"] * df["CAL"]
    df["PROD_PRO"] = df["PROD_KG"] * df["PRO"]
    return df.replace([np.inf, -np.inf], 0).fillna(0)


def _aggregate_outputs(df, gwavailability_mcm, population_millions):
    irwfp = (df["SIRWFP"] + df["GWIRWFP"]).sum()
    rfwfp = df["RFWFP"].sum()
    total_wfp = irwfp + rfwfp
    gw_wfp = df["GWIRWFP"].sum()
    gw_withdrawals = df["GW_WITHDRAWALS"].sum()

    irrigation_pct = (irwfp / total_wfp * 100) if total_wfp > 0 else 0
    gw_wfp_pct = (gw_wfp / gwavailability_mcm * 100) if gwavailability_mcm > 0 else 0
    gw_withdrawal_pct = (gw_withdrawals / gwavailability_mcm * 100) if gwavailability_mcm > 0 else 0

    # Calorie/protein self-sufficiency - see the caveat where PROD_CAL/PROD_PRO
    # are computed: this pair is unvalidated, unlike the three metrics above.
    population_actual = population_millions * 1e6
    cons_cal = (df["CONPC"] * population_actual * 365 * df["CAL"]).sum()
    cons_pro = (df["CONPC"] * population_actual * 365 * df["PRO"]).sum()
    cal_surplus = ((df["PROD_CAL"].sum() / cons_cal) - 1) * 100 if cons_cal > 0 else 0
    pro_surplus = ((df["PROD_PRO"].sum() / cons_pro) - 1) * 100 if cons_pro > 0 else 0

    return irrigation_pct, gw_wfp_pct, gw_withdrawal_pct, cal_surplus, pro_surplus


def render_scenario_view(sel):
    state, district = sel["state"], sel["district"]
    base_df = load_scenario_baseline()
    drivers_df = load_scenario_drivers()

    dist_all = base_df[(base_df["STATE"] == state) & (base_df["DISTRICT"] == district)].copy()
    driver_row = drivers_df[(drivers_df["STATE"] == state) & (drivers_df["DISTRICT"] == district)]
    gwavail_baseline = float(driver_row["GWAVAILABILITY_MCM"].iloc[0]) if not driver_row.empty else 0.0
    population_baseline = float(driver_row["POPULATION"].iloc[0]) if not driver_row.empty else 0.0

    if dist_all.empty:
        st.warning("No scenario data available for this district.")
        return

    scope_key = f"{state}||{district}"
    added = st.session_state.get("scn_added_rows", {}).get(scope_key, set())

    top_crops = (dist_all[dist_all["RANK"] <= TOP_N_DEFAULT][["CROP", "SEASON"]]
                 .drop_duplicates())
    show_pairs = set(map(tuple, top_crops.values.tolist())) | added
    shown = dist_all[dist_all.apply(lambda r: (r["CROP"], r["SEASON"]) in show_pairs, axis=1)].copy()
    shown = shown.sort_values("RANK")

    # ---------------- Baseline table (read-only) ----------------
    map_col, side_col = st.columns([1.7, 1])

    with map_col:
        panel_open("Baseline data (2018-2020)")
        base_display = shown[DISPLAY_COLS].rename(columns=DISPLAY_LABELS).round(2)
        totals = shown[["SFIRA", "GWIRA", "RFHA"]].sum()
        district_totals = dist_all[["SFIRA", "GWIRA", "RFHA"]].sum()
        st.dataframe(base_display, use_container_width=True, hide_index=True)
        tot_col1, tot_col2 = st.columns(2)
        tot_col1.markdown(
            f"**Total (shown crops):** SFIRA {totals['SFIRA']:,.0f} \u00b7 "
            f"GWIRA {totals['GWIRA']:,.0f} \u00b7 RFA {totals['RFHA']:,.0f}"
        )
        tot_col2.markdown(
            f"**District (all crops):** SFIRA {district_totals['SFIRA']:,.0f} \u00b7 "
            f"GWIRA {district_totals['GWIRA']:,.0f} \u00b7 RFA {district_totals['RFHA']:,.0f}"
        )
        panel_close()

        # ---------------- Alternative scenario (editable) ----------------
        panel_open("Alternative scenario (edit any cell to test a what-if)")
        edit_key = f"scn_editor_{scope_key}"
        edit_source = shown[["CROP", "SEASON"] + EDITABLE_COLS].rename(columns=DISPLAY_LABELS).round(2)
        edited = st.data_editor(
            edit_source, use_container_width=True, hide_index=True, key=edit_key,
            disabled=["Crop", "Season"],
        )
        panel_close()

    # ---- recompute the edited rows through the same formula pipeline ----
    alt = shown.copy().reset_index(drop=True)
    rename_back = {v: k for k, v in DISPLAY_LABELS.items()}
    edited_renamed = edited.rename(columns=rename_back)
    for c in EDITABLE_COLS:
        if c in edited_renamed.columns:
            alt[c] = edited_renamed[c].values
    alt = _compute_row_outputs(alt)

    with side_col:
        panel_open("Other drivers")
        pop_alt = st.number_input("Population ('000 000)", value=round(population_baseline, 2),
                                   step=0.1, key=f"scn_pop_{scope_key}")
        gwavail_alt = st.number_input("GW availability (M m\u00b3)", value=round(gwavail_baseline, 1),
                                       step=10.0, key=f"scn_gwavail_{scope_key}")
        st.caption(f"Baseline: Population {population_baseline:,.2f}  \u2022  "
                   f"GW availability {gwavail_baseline:,.1f} M m\u00b3")
        panel_close()

        panel_open("Output")
        irr_base, gwwfp_base, gwwd_base, cal_base, pro_base = _aggregate_outputs(
            shown, gwavail_baseline, population_baseline)
        irr_alt, gwwfp_alt, gwwd_alt, cal_alt, pro_alt = _aggregate_outputs(
            alt, gwavail_alt, pop_alt)
        out_table = pd.DataFrame({
            "Factor": ["Irrigation WFP - % of total",
                       "Groundwater WFP - % of extractable resources",
                       "Groundwater withdrawals - % of extractable resources",
                       "Calorie supply - % of consumption *",
                       "Protein supply - % of consumption *"],
            "Baseline": [irr_base, gwwfp_base, gwwd_base, cal_base, pro_base],
            "Alternative Scenario": [irr_alt, gwwfp_alt, gwwd_alt, cal_alt, pro_alt],
        })
        st.dataframe(out_table.style.format({"Baseline": "{:.1f}", "Alternative Scenario": "{:.1f}"}),
                     use_container_width=True, hide_index=True)
        st.caption(
            "\\* Calorie/Protein supply rows are unvalidated - the underlying CAL/PRO "
            "unit convention couldn't be confirmed against the reference example. "
            "Irrigation WFP % is also an approximation pending further validation. "
            "GW-related rows were checked numerically and track the reference closely. See README."
        )
        panel_close()

    with st.expander("View & download the scenario data behind this view"):
        st.dataframe(alt, use_container_width=True)
        st.download_button("Download CSV", alt.to_csv(index=False).encode("utf-8"),
                            file_name=f"wpatlas_scenario_{state}_{district}.csv",
                            mime="text/csv", key="scn_download")
