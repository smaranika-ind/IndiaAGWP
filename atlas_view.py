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

# --- Layout sizing: keep the 3 right-hand panels' combined height equal to the
# left map panel's height, split evenly, so the two columns end flush. ---
MAP_HEIGHT = 520
_PANEL_HEADER_H = 38        # approx height of the dark ".panel-header" bar (px)
_PANEL_BODY_OVERHEAD = 26   # approx border + padding around each chart (px)
_PANEL_GAP = 18             # ".panel-body" margin-bottom between stacked panels (px)


def _right_chart_height(total_map_height, n_panels=3):
    total_gaps = _PANEL_GAP * (n_panels - 1)
    h = round(
        (total_map_height + _PANEL_HEADER_H + _PANEL_BODY_OVERHEAD - total_gaps) / n_panels
        - (_PANEL_HEADER_H + _PANEL_BODY_OVERHEAD)
    )
    return max(90, h)


RIGHT_CHART_HEIGHT = _right_chart_height(MAP_HEIGHT)

DASH_STYLES = ["dot", "solid", "dash", "dashdot"]
MAX_COMPARE_ITEMS = 4
SUBMAP_HEIGHT = 300


def _crop_display(c):
    return "All crops" if c == "ALL CROPS" else c


# ============================================================================
# TRENDS: sidebar + view
# ============================================================================

def render_sidebar_controls_trends():
    district_df, _ = get_level_data("District")
    all_years = sorted(district_df["YEAR"].unique().tolist())
    all_crops = ["ALL CROPS"] + sorted(c for c in district_df["CROP"].unique() if c != "ALL CROPS")
    all_states = sorted(district_df["STATE"].unique().tolist())
    all_labels = all_labels_flat()

    st.sidebar.markdown('<div class="sidebar-header">Analysis Options</div>', unsafe_allow_html=True)
    with st.sidebar.form(key="controls_form_trends"):
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


def render_trends_view(sel):
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

    with map_col:
        panel_open("Temporal Variation")
        st.markdown(f"**{year}**")
        _render_trends_map(level, indicator_col, crop, year, unit, short, zoom_state)
        panel_close()

    with stats_col:
        panel_open("Statistical Analysis")
        _render_boxplot_single(level, indicator_col, crop, year, zoom_state,
                                label_choice=indicator_label, unit=unit, height=RIGHT_CHART_HEIGHT)
        panel_close()

        panel_open("Effect of Other Factors")
        _render_dual_axis_single(secondary_unit, crop, indicator_col, "TYLD_TOL",
                                  left_name=short, right_name="Yield",
                                  left_color="#1f77b4", right_color="#d62728",
                                  height=RIGHT_CHART_HEIGHT, ns="trends")
        panel_close()

        panel_open("Additional Insights")
        _render_dual_axis_single(secondary_unit, crop, "THA_TOL", "TCWU_TOL",
                                  left_name="Area", right_name="CWU",
                                  left_color="#7b52ab", right_color="#111111",
                                  left_scale=1e-6, right_scale=1e-3,
                                  left_axis_title="Area (M ha)", right_axis_title="CWU (B m\u00b3)",
                                  height=RIGHT_CHART_HEIGHT, ns="trends")
        panel_close()

    panel_open("AI Summary")
    if st.button("Generate AI summary", key="trends_ai_summary_go"):
        st.session_state["trends_ai_summary_shown"] = True
    if st.session_state.get("trends_ai_summary_shown"):
        _render_ai_summary(level, indicator_col, indicator_label, unit, crop, year, secondary_unit, zoom_state)
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
                            file_name=f"wpatlas_trends_{level.lower()}_{crop}_{year}.csv",
                            mime="text/csv", key="trends_download")


def _render_trends_map(level, indicator_col, crop, year, unit, short, zoom_state):
    df, geo_df = get_level_data(level)
    filtered = df[(df["YEAR"] == year) & (df["CROP"] == crop)].copy()

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
        _state_choropleth(crop, year, indicator_col, short, unit, MAP_HEIGHT, key_suffix="trends")
    else:
        _district_choropleth(zoom_state, crop, year, indicator_col, short, unit, MAP_HEIGHT, key_suffix="trends")


# ============================================================================
# COMPARISON: sidebar + view
# ============================================================================

def render_sidebar_controls_comparison():
    district_df, _ = get_level_data("District")
    all_years = sorted(district_df["YEAR"].unique().tolist())
    all_crops = sorted(c for c in district_df["CROP"].unique() if c != "ALL CROPS")
    all_states = sorted(district_df["STATE"].unique().tolist())
    all_labels = all_labels_flat()

    default_crop = ["Rice"] if "Rice" in all_crops else all_crops[:1]

    st.sidebar.markdown('<div class="sidebar-header">Analysis Options</div>', unsafe_allow_html=True)
    with st.sidebar.form(key="controls_form_cmp"):
        primary_unit = st.selectbox(
            "Primary unit of analysis", ["Administrative level", "River basin (needs data)"], key="cmp_primary",
        )
        secondary_mode = st.selectbox("Secondary unit of analysis", ["All India", "States"], index=1, key="cmp_secmode")
        state_multi = []
        if secondary_mode == "States":
            state_multi = st.multiselect(
                "State(s)", all_states, default=all_states[:1], key="cmp_states",
                help="Pick 2+ states (with 1 crop) to compare states, or 1 state (with 2+ crops) to compare crops within it.",
            )
        indicator_label = st.selectbox(
            "Indicator", all_labels, index=all_labels.index("Physical Water Productivity"), key="cmp_indicator",
        )
        _ = st.selectbox("Production system", ["Crop"], key="cmp_prodsys")
        crop_multi = st.multiselect(
            "Crop(s)", all_crops, default=default_crop, key="cmp_crops",
            help="Pick 2+ crops (with 1 state, or All India) to compare crops, or 1 crop (with 2+ states) to compare states.",
        )
        year = st.selectbox("Year", all_years, index=len(all_years) - 1, key="cmp_year")
        st.form_submit_button("Update")

    if primary_unit.startswith("River basin"):
        st.sidebar.caption("River basin scale needs a basin boundary file - see README. Showing Administrative level.")

    if not crop_multi:
        crop_multi = default_crop
    if secondary_mode == "States" and not state_multi:
        state_multi = all_states[:1]

    _, label_to_col = indicator_options()

    if len(state_multi) > 1 and len(crop_multi) <= 1:
        compare_by = "state"
        items = state_multi
        fixed_crop = crop_multi[0]
        fixed_state = None
    elif len(crop_multi) > 1:
        compare_by = "crop"
        items = crop_multi
        fixed_crop = None
        fixed_state = state_multi[0] if (secondary_mode == "States" and state_multi) else None
    else:
        compare_by = "single"
        items = state_multi[:1] if (secondary_mode == "States" and state_multi) else ["All India"]
        fixed_crop = crop_multi[0]
        fixed_state = items[0] if items[0] != "All India" else None

    truncated = len(items) > MAX_COMPARE_ITEMS
    items = items[:MAX_COMPARE_ITEMS]

    return {
        "compare_by": compare_by,
        "items": items,
        "truncated": truncated,
        "fixed_crop": fixed_crop,
        "fixed_state": fixed_state,
        "indicator_label": indicator_label,
        "indicator_col": label_to_col[indicator_label],
        "year": year,
    }


def render_comparison_view(sel):
    compare_by = sel["compare_by"]
    items = sel["items"]
    indicator_col = sel["indicator_col"]
    indicator_label = sel["indicator_label"]
    year = sel["year"]
    unit = unit_of(indicator_col)
    short = short_of(indicator_col)

    if sel["truncated"]:
        st.info(f"Showing the first {MAX_COMPARE_ITEMS} selections to keep the layout readable.")

    total_map_height = max(MAP_HEIGHT, len(items) * SUBMAP_HEIGHT)
    right_height = _right_chart_height(total_map_height)

    map_col, stats_col = st.columns([1.7, 1])

    with map_col:
        panel_open("Spatial Variation")
        for item in items:
            st.markdown(f"**{item}**")
            if compare_by == "state":
                _district_choropleth(item, sel["fixed_crop"], year, indicator_col, short, unit,
                                      SUBMAP_HEIGHT, key_suffix=f"cmp_state_{item}")
            elif compare_by == "crop":
                _district_choropleth(sel["fixed_state"], item, year, indicator_col, short, unit,
                                      SUBMAP_HEIGHT, key_suffix=f"cmp_crop_{item}")
            else:
                zoom = None if item == "All India" else item
                _district_choropleth(zoom, sel["fixed_crop"], year, indicator_col, short, unit,
                                      SUBMAP_HEIGHT, key_suffix="cmp_single")
        panel_close()

    with stats_col:
        panel_open("Statistical Analysis")
        _render_comparison_boxplot(sel, indicator_label, unit, right_height)
        panel_close()

        panel_open("Effect of Other Factors")
        _render_comparison_dual_axis(sel, indicator_col, "TYLD_TOL", short, "Yield",
                                      "#1f77b4", "#d62728", height=right_height)
        panel_close()

        panel_open("Additional Insights")
        _render_comparison_dual_axis(sel, "THA_TOL", "TCWU_TOL", "Area", "CWU",
                                      "#7b52ab", "#111111",
                                      left_scale=1e-6, right_scale=1e-3,
                                      left_axis_title="Area (M ha)", right_axis_title="CWU (B m\u00b3)",
                                      height=right_height)
        panel_close()

    panel_open("AI Summary")
    if st.button("Generate AI summary", key="cmp_ai_summary_go"):
        st.session_state["cmp_ai_summary_shown"] = True
    if st.session_state.get("cmp_ai_summary_shown"):
        _render_comparison_ai_summary(sel, indicator_label, unit)
    else:
        st.caption("Click the button to generate a plain-language summary of this comparison.")
    panel_close()

    with st.expander("View & download the data behind this view"):
        frames = [_scope_district_values(sel, item).assign(_ITEM=item) for item in items]
        show = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        st.dataframe(show, use_container_width=True)
        if not show.empty:
            st.download_button("Download CSV", show.to_csv(index=False).encode("utf-8"),
                                file_name=f"wpatlas_comparison_{compare_by}_{year}.csv",
                                mime="text/csv", key="cmp_download")


# ============================================================================
# Shared map-drawing helpers
# ============================================================================

def _state_choropleth(crop, year, indicator_col, short, unit, height, key_suffix):
    _, state_map_df = get_level_data("State")
    geo_filtered = state_map_df[(state_map_df["YEAR"] == year) & (state_map_df["CROP"] == crop)].copy()
    gj = load_state_geojson()
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
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(
        margin=dict(l=0, r=0, t=6, b=0), height=height,
        legend_title_text=f"{_crop_display(crop)} {short} ({unit})",
        legend=dict(orientation="v", yanchor="top", y=0.98, xanchor="left", x=1.0),
        paper_bgcolor="white", plot_bgcolor="white",
    )
    st.plotly_chart(fig, use_container_width=True, key=f"map_{key_suffix}_state_{indicator_col}_{crop}_{year}")


def _district_choropleth(zoom_state, crop, year, indicator_col, short, unit, height, key_suffix):
    _, geo_df = get_level_data("District")
    geo_filtered = geo_df[(geo_df["YEAR"] == year) & (geo_df["CROP"] == crop)].copy()

    gj = load_district_geojson()
    if zoom_state:
        skey = key(zoom_state)
        gj = {"type": "FeatureCollection",
              "features": [f for f in gj["features"] if f["properties"]["STATE_KEY"] == skey]}
        geo_filtered = geo_filtered[geo_filtered["STATE"] == zoom_state]

    geo_filtered["JOIN_KEY"] = geo_filtered["STATE_KEY"] + "||" + geo_filtered["DISTRICT_KEY"]
    all_keys = pd.DataFrame([
        {"JOIN_KEY": f["properties"]["JOIN_KEY"], "STATE": f["properties"].get("State"),
         "DISTRICT": f["properties"].get("District")}
        for f in gj["features"]
    ])
    complete = all_keys.merge(geo_filtered, on="JOIN_KEY", how="left", suffixes=("", "_data"))
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
        margin=dict(l=0, r=0, t=6, b=0), height=height,
        legend_title_text=f"{_crop_display(crop)} {short} ({unit})",
        legend=dict(orientation="v", yanchor="top", y=0.98, xanchor="left", x=1.0),
        paper_bgcolor="white", plot_bgcolor="white",
    )
    st.plotly_chart(fig, use_container_width=True,
                     key=f"map_{key_suffix}_district_{indicator_col}_{crop}_{year}_{zoom_state}")


# ============================================================================
# Trends-only: single box plot / single dual-axis chart
# ============================================================================

def _render_boxplot_single(level, indicator_col, crop, year, zoom_state, label_choice, unit, height):
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
    fig.update_layout(margin=dict(l=0, r=0, t=6, b=0), height=height, xaxis_title=None,
                       paper_bgcolor="white", plot_bgcolor="white", font=dict(size=11))
    fig.update_traces(marker_color="#e8845a", line_color="#e8845a",
                       marker=dict(opacity=0.65, size=6), jitter=0.4, pointpos=0, boxmean=False)
    st.plotly_chart(fig, use_container_width=True,
                     key=f"box_trends_{level}_{indicator_col}_{crop}_{year}_{zoom_state}")


def _render_dual_axis_single(secondary_unit, crop, left_col, right_col, left_name, right_name,
                              left_color, right_color, height, left_scale=1.0, right_scale=1.0,
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
    fig.update_layout(margin=dict(l=0, r=0, t=22, b=0), height=height,
                       legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=10)),
                       paper_bgcolor="white", plot_bgcolor="white", font=dict(size=11))
    st.plotly_chart(fig, use_container_width=True,
                     key=f"dual_{ns}_{secondary_unit}_{crop}_{left_col}_{right_col}")


# ============================================================================
# Comparison-only: multi-item box plot / multi-item dual-axis chart
# ============================================================================

def _scope_district_values(sel, item):
    """District-level rows for one comparison item (a state or a crop), used for
    both the box plot and the downloadable data table."""
    dist_df, _ = get_level_data("District")
    year = sel["year"]
    compare_by = sel["compare_by"]

    if compare_by == "state":
        sub = dist_df[(dist_df["YEAR"] == year) & (dist_df["CROP"] == sel["fixed_crop"])
                      & (dist_df["STATE"] == item)]
    elif compare_by == "crop":
        sub = dist_df[(dist_df["YEAR"] == year) & (dist_df["CROP"] == item)]
        if sel["fixed_state"]:
            sub = sub[sub["STATE"] == sel["fixed_state"]]
    else:  # single
        sub = dist_df[(dist_df["YEAR"] == year) & (dist_df["CROP"] == sel["fixed_crop"])]
        if item != "All India":
            sub = sub[sub["STATE"] == item]
    return sub.copy()


def _scope_trend(sel, item):
    """State-level (or national) yearly trend for one comparison item, for the
    two dual-axis charts."""
    compare_by = sel["compare_by"]
    if compare_by == "state":
        state_df, _ = get_level_data("State")
        return state_df[(state_df["STATE"] == item) & (state_df["CROP"] == sel["fixed_crop"])].sort_values("YEAR")
    elif compare_by == "crop":
        if sel["fixed_state"]:
            state_df, _ = get_level_data("State")
            return state_df[(state_df["STATE"] == sel["fixed_state"]) & (state_df["CROP"] == item)].sort_values("YEAR")
        nat_df, _ = get_level_data("National")
        return nat_df[nat_df["CROP"] == item].sort_values("YEAR")
    else:  # single
        if item == "All India":
            nat_df, _ = get_level_data("National")
            return nat_df[nat_df["CROP"] == sel["fixed_crop"]].sort_values("YEAR")
        state_df, _ = get_level_data("State")
        return state_df[(state_df["STATE"] == item) & (state_df["CROP"] == sel["fixed_crop"])].sort_values("YEAR")


def _render_comparison_boxplot(sel, label_choice, unit, height):
    indicator_col = sel["indicator_col"]
    frames = []
    for item in sel["items"]:
        sub = _scope_district_values(sel, item)
        sub = sub[sub[indicator_col] > 0]
        if not sub.empty:
            frames.append(pd.DataFrame({indicator_col: sub[indicator_col], "GROUP": item}))

    if not frames:
        st.caption("Not enough data to compare - try different selections.")
        return

    plot_df = pd.concat(frames, ignore_index=True)
    fig = px.box(plot_df, x="GROUP", y=indicator_col, points="all", color="GROUP",
                 labels={indicator_col: f"{label_choice} ({unit})", "GROUP": ""})
    fig.update_layout(margin=dict(l=0, r=0, t=6, b=0), height=height, showlegend=False,
                       paper_bgcolor="white", plot_bgcolor="white", font=dict(size=11))
    fig.update_traces(marker=dict(opacity=0.65, size=6), jitter=0.4, pointpos=0, boxmean=False)
    st.plotly_chart(fig, use_container_width=True,
                     key=f"cmpbox_{sel['compare_by']}_{'_'.join(sel['items'])}_{indicator_col}_{sel['year']}")


def _render_comparison_dual_axis(sel, left_col, right_col, left_name, right_name,
                                  left_color, right_color, height,
                                  left_scale=1.0, right_scale=1.0,
                                  left_axis_title=None, right_axis_title=None):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    any_data = False
    for i, item in enumerate(sel["items"]):
        trend = _scope_trend(sel, item)
        if trend.empty:
            continue
        any_data = True
        dash = DASH_STYLES[i % len(DASH_STYLES)]
        fig.add_trace(go.Scatter(x=trend["YEAR"], y=trend[left_col] * left_scale,
                                  name=f"{left_name}-{item}",
                                  line=dict(color=left_color, dash=dash)), secondary_y=False)
        fig.add_trace(go.Scatter(x=trend["YEAR"], y=trend[right_col] * right_scale,
                                  name=f"{right_name}-{item}",
                                  line=dict(color=right_color, dash=dash)), secondary_y=True)

    if not any_data:
        st.caption("No data for this selection.")
        return

    fig.update_yaxes(title_text=left_axis_title or left_name, secondary_y=False, color=left_color)
    fig.update_yaxes(title_text=right_axis_title or right_name, secondary_y=True, color=right_color)
    fig.update_layout(margin=dict(l=0, r=0, t=22, b=0), height=height,
                       legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=9)),
                       paper_bgcolor="white", plot_bgcolor="white", font=dict(size=11))
    st.plotly_chart(fig, use_container_width=True,
                     key=f"cmpdual_{sel['compare_by']}_{'_'.join(sel['items'])}_{left_col}_{right_col}")


# ============================================================================
# AI Summary (templated, instant - see README for the "is this a real LLM" note)
# ============================================================================

def _render_ai_summary(level, indicator_col, indicator_label, unit, crop, year, secondary_unit, zoom_state):
    crop_disp = _crop_display(crop)
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
        f"- **Mean:** {vmean:,.2f} {unit}  \u2022  **Median:** {vmedian:,.2f} {unit}",
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


def _render_comparison_ai_summary(sel, indicator_label, unit):
    indicator_col = sel["indicator_col"]
    year = sel["year"]
    crop_disp = _crop_display(sel["fixed_crop"]) if sel["fixed_crop"] else None

    stats = {}
    for item in sel["items"]:
        sub = _scope_district_values(sel, item)
        valid = sub[sub[indicator_col] > 0]
        if not valid.empty:
            stats[item] = valid[indicator_col].mean()

    if not stats:
        st.caption("Not enough data to summarize this comparison.")
        return

    lines = [f"For **{indicator_label}** in **{year}**{f' ({crop_disp})' if crop_disp else ''}:"]
    for item, mean_val in stats.items():
        lines.append(f"- **{item}**: average {mean_val:,.2f} {unit}")

    best_item = max(stats, key=stats.get)
    worst_item = min(stats, key=stats.get)
    if best_item != worst_item:
        gap = stats[best_item] - stats[worst_item]
        lines.append(
            f"- **{best_item}** is highest, **{abs(gap):,.2f} {unit}** ahead of **{worst_item}** (the lowest)."
        )

    st.markdown("\n".join(lines))
