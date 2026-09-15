import numpy as np
import pandas as pd

import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from common import (
    get_level_data, load_district_geojson, load_state_geojson,
    classify_quantile, panel_open, panel_close, key,
)
from indicators import all_labels_flat, indicator_options, unit_of, short_of


def _crop_display(c):
    return "All crops" if c == "ALL CROPS" else c


def render_sidebar_controls():
    """Renders the single shared 'Analysis Options' sidebar form and returns the
    selected values as a dict. Shared across the Trends and Comparison tabs so the
    sidebar only appears once (Streamlit renders every tab's body on each script run,
    so per-tab sidebar widgets would otherwise duplicate)."""
    district_df, _ = get_level_data("District")
    all_years = sorted(district_df["YEAR"].unique().tolist())
    all_crops = ["ALL CROPS"] + sorted(c for c in district_df["CROP"].unique() if c != "ALL CROPS")
    all_states = sorted(district_df["STATE"].unique().tolist())
    all_labels = all_labels_flat()

    st.sidebar.markdown('<div class="sidebar-header">Analysis Options</div>', unsafe_allow_html=True)
    with st.sidebar.form(key="controls_form"):
        primary_unit = st.selectbox(
            "Primary unit of analysis", ["Administrative level", "River basin (needs data)"],
        )
        secondary_unit = st.selectbox("Secondary unit of analysis", ["All India"] + all_states)
        tertiary_unit = st.selectbox(
            "Tertiary unit of analysis", ["Country wise", "State wise", "District wise"], index=1,
        )
        indicator_label = st.selectbox(
            "Indicator", all_labels, index=all_labels.index("Physical Water Productivity"),
        )
        _ = st.selectbox("Production system", ["Crop"])
        crop = st.selectbox("Crop(s)", all_crops, format_func=_crop_display)
        year = st.selectbox("Year(s)", all_years, index=len(all_years) - 1)
        st.form_submit_button("Update")

    if primary_unit.startswith("River basin"):
        st.sidebar.caption("River basin scale needs a basin boundary file - see README. Showing Administrative level.")

    level_map = {"Country wise": "National", "State wise": "State", "District wise": "District"}
    _, label_to_col = indicator_options()

    return {
        "level": level_map[tertiary_unit],
        "secondary_unit": secondary_unit,
        "zoom_state": None if secondary_unit == "All India" else secondary_unit,
        "indicator_label": indicator_label,
        "indicator_col": label_to_col[indicator_label],
        "crop": crop,
        "year": year,
    }


def render_atlas_view(mode, sel):
    """mode: 'trends' or 'comparison' - only changes the main-panel header text
    ('Temporal Variation' vs 'Spatial Variation'), matching the reference screenshots.
    sel: dict returned by render_sidebar_controls()."""
    level = sel["level"]
    indicator_col = sel["indicator_col"]
    crop = sel["crop"]
    year = sel["year"]
    zoom_state = sel["zoom_state"]
    secondary_unit = sel["secondary_unit"]
    indicator_label = sel["indicator_label"]

    unit = unit_of(indicator_col)
    short = short_of(indicator_col)

    map_col, stats_col = st.columns([1.7, 1])

    header_title = "Temporal Variation" if mode == "trends" else "Spatial Variation"
    with map_col:
        panel_open(header_title)
        st.markdown(f"**{year}**")
        _render_map(level, indicator_col, crop, year, unit, short, zoom_state, mode)
        panel_close()

    with stats_col:
        panel_open("Statistical Analysis")
        _render_boxplot(level, indicator_col, crop, year, zoom_state, label_choice=indicator_label, unit=unit, mode=mode)
        panel_close()

        panel_open("Effect of Other Factors")
        _render_dual_axis(secondary_unit, crop, indicator_col, "TYLD_TOL",
                           left_name=short, right_name="Yield",
                           left_color="#1f77b4", right_color="#d62728", ns=mode)
        panel_close()

        panel_open("Additional Insights")
        _render_dual_axis(secondary_unit, crop, "THA_TOL", "TCWU_TOL",
                           left_name="Area", right_name="CWU",
                           left_color="#7b52ab", right_color="#111111",
                           left_scale=1e-6, right_scale=1e-3,  # ha->M ha, MCM->BCM
                           left_axis_title="Area (M ha)", right_axis_title="CWU (B m\u00b3)", ns=mode)
        panel_close()

    panel_open("AI Summary")
    gen_key = f"{mode}_ai_summary_go"
    if st.button("Generate AI summary", key=gen_key):
        st.session_state[f"{mode}_ai_summary_shown"] = True
    if st.session_state.get(f"{mode}_ai_summary_shown"):
        _render_ai_summary(level, indicator_col, indicator_label, unit, crop, year,
                            secondary_unit, zoom_state, mode)
    else:
        st.caption("Click the button to generate a plain-language summary of the current view.")
    panel_close()

    with st.expander("View & download the data behind this view"):
        df, _ = get_level_data(level)
        show = df[(df["YEAR"] == year) & (df["CROP"] == crop)]
        if zoom_state and "STATE" in show.columns:
            show = show[show["STATE"] == zoom_state]
        st.dataframe(show, use_container_width=True)
        st.download_button("Download CSV", show.to_csv(index=False).encode("utf-8"),
                            file_name=f"wpatlas_{mode}_{level.lower()}_{crop}_{year}.csv",
                            mime="text/csv", key=f"{mode}_download")


def _render_map(level, indicator_col, crop, year, unit, short, zoom_state, mode):
    df, geo_df = get_level_data(level)
    filtered = df[(df["YEAR"] == year) & (df["CROP"] == crop)].copy()
    geo_filtered = geo_df[(geo_df["YEAR"] == year) & (geo_df["CROP"] == crop)].copy()

    if level == "National":
        if filtered.empty:
            st.warning("No data for this selection.")
            return
        val = filtered[indicator_col].iloc[0]
        c1, c2, c3 = st.columns(3)
        c1.metric(f"{short} ({unit})", f"{val:,.2f}")
        c2.metric("Total Production (t)", f"{filtered['PROD_TOL'].iloc[0]:,.0f}")
        c3.metric("Total Crop Water Use (MCM)", f"{filtered['TCWU_TOL'].iloc[0]:,.1f}")
        return

    if level == "State":
        gj = load_state_geojson()
        # Make sure every state in the shapefile shows up, even ones with no row for this
        # crop/year (e.g. a crop not grown there) - otherwise Plotly leaves them blank
        # instead of gray, which looked like states (e.g. Jammu & Kashmir) were "missing".
        all_keys = pd.DataFrame({"STATE_KEY_SHP": [f["properties"]["STATE_KEY_SHP"] for f in gj["features"]]})
        complete = all_keys.merge(geo_filtered, on="STATE_KEY_SHP", how="left")
        complete[indicator_col] = complete[indicator_col].fillna(0)
        cats, color_map, order = classify_quantile(complete[indicator_col])
        complete["_CLASS"] = cats
        complete["_DISPLAY_NAME"] = complete["STATE_KEY_SHP"].str.title()
        fig = px.choropleth(
            complete, geojson=gj, locations="STATE_KEY_SHP", featureidkey="properties.STATE_KEY_SHP",
            color="_CLASS", category_orders={"_CLASS": order}, color_discrete_map=color_map,
            hover_name="_DISPLAY_NAME",
            hover_data={"STATE_KEY_SHP": False, indicator_col: ":.2f", "_CLASS": False},
        )
    else:  # District
        gj = load_district_geojson()
        if zoom_state:
            skey = key(zoom_state)
            gj = {"type": "FeatureCollection",
                  "features": [f for f in gj["features"] if f["properties"]["STATE_KEY"] == skey]}

        dmap = geo_filtered.copy()
        if zoom_state:
            dmap = dmap[dmap["STATE"] == zoom_state]
        dmap["JOIN_KEY"] = dmap["STATE_KEY"] + "||" + dmap["DISTRICT_KEY"]

        # Same completeness fix as the state map: reindex to every district in the
        # (possibly zoomed) geojson so districts with no row for this crop/year still render gray.
        all_keys = pd.DataFrame([
            {"JOIN_KEY": f["properties"]["JOIN_KEY"], "STATE": f["properties"].get("State"),
             "DISTRICT": f["properties"].get("District")}
            for f in gj["features"]
        ])
        complete = all_keys.merge(dmap, on="JOIN_KEY", how="left", suffixes=("", "_data"))
        complete[indicator_col] = complete[indicator_col].fillna(0)
        if "STATE_data" in complete.columns:
            complete["STATE"] = complete["STATE_data"].fillna(complete["STATE"])
        if "DISTRICT_data" in complete.columns:
            complete["DISTRICT"] = complete["DISTRICT_data"].fillna(complete["DISTRICT"])

        cats, color_map, order = classify_quantile(complete[indicator_col])
        complete["_CLASS"] = cats
        fig = px.choropleth(
            complete, geojson=gj, locations="JOIN_KEY", featureidkey="properties.JOIN_KEY",
            color="_CLASS", category_orders={"_CLASS": order}, color_discrete_map=color_map,
            hover_name="DISTRICT",
            hover_data={"STATE": True, indicator_col: ":.2f", "JOIN_KEY": False, "_CLASS": False},
        )

    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(
        margin=dict(l=0, r=0, t=10, b=0), height=520,
        legend_title_text=f"{_crop_display(crop)} {short} ({unit})",
        legend=dict(orientation="v", yanchor="top", y=0.98, xanchor="left", x=1.0),
        paper_bgcolor="white", plot_bgcolor="white",
    )
    st.plotly_chart(fig, use_container_width=True, key=f"map_{mode}_{level}_{indicator_col}_{crop}_{year}_{zoom_state}")


def _render_boxplot(level, indicator_col, crop, year, zoom_state, label_choice, unit, mode):
    df, _ = get_level_data("District" if level == "District" else ("State" if level == "State" else "National"))
    filtered = df[(df["YEAR"] == year) & (df["CROP"] == crop)].copy()
    if level == "District" and zoom_state:
        filtered = filtered[filtered["STATE"] == zoom_state]

    if level == "National" or filtered.empty or filtered[indicator_col].replace(0, np.nan).dropna().shape[0] < 2:
        st.caption("Distribution needs more than one spatial unit - pick State wise or District wise to see this.")
        return

    plot_df = filtered[filtered[indicator_col] > 0].copy()
    plot_df["YEAR_STR"] = str(year)
    fig = px.box(plot_df, x="YEAR_STR", y=indicator_col, points="all",
                 labels={indicator_col: f"{label_choice} ({unit})", "YEAR_STR": "Year"})
    fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=270, xaxis_title=None,
                       paper_bgcolor="white", plot_bgcolor="white")
    # Spread the overlaid points across the box width (jitter) instead of stacking them
    # in a single vertical line down the middle, which is what looked "misaligned".
    fig.update_traces(marker_color="#e8845a", line_color="#e8845a",
                       marker=dict(opacity=0.65, size=6), jitter=0.4, pointpos=0,
                       boxmean=False)
    st.plotly_chart(fig, use_container_width=True, key=f"box_{mode}_{level}_{indicator_col}_{crop}_{year}_{zoom_state}")


def _render_dual_axis(secondary_unit, crop, left_col, right_col, left_name, right_name,
                       left_color, right_color, left_scale=1.0, right_scale=1.0,
                       left_axis_title=None, right_axis_title=None, ns="trends"):
    if secondary_unit == "All India":
        df, _ = get_level_data("National")
        trend = df[df["CROP"] == crop].sort_values("YEAR")
    else:
        df, _ = get_level_data("State")
        trend = df[(df["STATE"] == secondary_unit) & (df["CROP"] == crop)].sort_values("YEAR")

    if trend.empty:
        st.caption("No data for this selection.")
        return

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(x=trend["YEAR"], y=trend[left_col] * left_scale, name=left_name,
                              line=dict(color=left_color)), secondary_y=False)
    fig.add_trace(go.Scatter(x=trend["YEAR"], y=trend[right_col] * right_scale, name=right_name,
                              line=dict(color=right_color)), secondary_y=True)
    fig.update_yaxes(title_text=left_axis_title or left_name, secondary_y=False, color=left_color)
    fig.update_yaxes(title_text=right_axis_title or right_name, secondary_y=True, color=right_color)
    fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=270,
                       legend=dict(orientation="h", yanchor="bottom", y=1.02),
                       paper_bgcolor="white", plot_bgcolor="white")
    st.plotly_chart(fig, use_container_width=True,
                     key=f"dual_{ns}_{secondary_unit}_{crop}_{left_col}_{right_col}")


def _render_ai_summary(level, indicator_col, indicator_label, unit, crop, year, secondary_unit, zoom_state, mode):
    """A templated, instantly-computed 'AI summary' - range/mean/median across the
    current view's spatial units, plus a gap-vs-national figure when a specific state
    is selected. This is deterministic statistics phrased as text, not a live LLM call
    (no external API key is configured in this deployment) - see README for how to
    wire in a real LLM later if wanted."""
    crop_disp = _crop_display(crop)

    # National reference value (always available for the gap comparison)
    nat_df, _ = get_level_data("National")
    nat_row = nat_df[(nat_df["YEAR"] == year) & (nat_df["CROP"] == crop)]
    nat_val = nat_row[indicator_col].iloc[0] if not nat_row.empty else None

    if level == "National":
        st.markdown(
            f"At the **national** scale, **{indicator_label}** for **{crop_disp}** in **{year}** "
            f"was **{nat_val:,.2f} {unit}**. Switch to State wise or District wise to see the "
            f"spread across spatial units and a gap comparison."
        )
        return

    df, _ = get_level_data(level)
    scope_df = df[(df["YEAR"] == year) & (df["CROP"] == crop)].copy()
    scope_label = "states"
    if level == "District":
        scope_label = "districts"
        if zoom_state:
            scope_df = scope_df[scope_df["STATE"] == zoom_state]
            scope_label = f"districts in {zoom_state}"

    name_col = "STATE" if level == "State" else "DISTRICT"
    valid = scope_df[scope_df[indicator_col] > 0]

    if valid.empty:
        st.caption("Not enough data in this view to summarize.")
        return

    vmin, vmax = valid[indicator_col].min(), valid[indicator_col].max()
    vmean, vmedian = valid[indicator_col].mean(), valid[indicator_col].median()
    row_min = valid.loc[valid[indicator_col].idxmin()]
    row_max = valid.loc[valid[indicator_col].idxmax()]

    lines = [
        f"For **{indicator_label}** ({crop_disp}, **{year}**) across **{len(valid)} {scope_label}**:",
        f"- **Range:** {vmin:,.2f} to {vmax:,.2f} {unit} "
        f"(lowest in **{row_min[name_col]}**, highest in **{row_max[name_col]}**)",
        f"- **Mean:** {vmean:,.2f} {unit}  •  **Median:** {vmedian:,.2f} {unit}",
    ]

    if zoom_state:
        state_df, _ = get_level_data("State")
        state_row = state_df[(state_df["YEAR"] == year) & (state_df["CROP"] == crop)
                              & (state_df["STATE"] == zoom_state)]
        if not state_row.empty and nat_val:
            state_val = state_row[indicator_col].iloc[0]
            gap = state_val - nat_val
            pct = (gap / nat_val * 100) if nat_val else 0
            direction = "above" if gap > 0 else "below"
            lines.append(
                f"- **Gap vs national:** {zoom_state}'s overall value is **{state_val:,.2f} {unit}**, "
                f"{abs(pct):,.1f}% {direction} the national figure of {nat_val:,.2f} {unit}."
            )
    elif nat_val is not None:
        lines.append(
            f"- **National reference:** {nat_val:,.2f} {unit}. Pick a specific state under "
            f"'Secondary unit of analysis' to see its gap vs this national figure."
        )

    st.markdown("\n".join(lines))
