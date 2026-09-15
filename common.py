import json
import os
import re

import pandas as pd
import streamlit as st

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "app_data")

# ---------------------------------------------------------------------------
# Visual identity (matches the IWMI Water Productivity Atlas colour scheme)
# ---------------------------------------------------------------------------
PANEL_DARK = "#1c3f5f"
NAVBAR_BG = "#d9dde1"
ACCENT_GREEN = "#2e7d32"
QUANTILE_COLORS = ["#d1382d", "#f2a33c", "#a8d18d", "#3f7d34"]  # low -> high
NA_COLOR = "#d3d3d3"


def inject_css():
    st.markdown(
        f"""
        <style>
        #MainMenu, footer {{visibility: hidden;}}
        .block-container {{padding-top: 0.5rem; padding-bottom: 1rem; max-width: 1500px;}}

        /* Force a light grey canvas regardless of the visitor's system theme
           preference - Streamlit Cloud otherwise sometimes serves a dark theme. */
        .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{
            background-color: #f3f5f7 !important;
        }}
        body {{background-color: #f3f5f7 !important;}}

        .wpatlas-navbar {{
            background: {NAVBAR_BG};
            padding: 14px 28px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 3px solid {PANEL_DARK};
            margin: 0 -1rem 1rem -1rem;
        }}
        .wpatlas-navbar .brand {{
            font-size: 28px; font-weight: 800; color: #1a1a1a;
        }}
        .wpatlas-navlinks span {{
            margin-left: 24px; font-weight: 600; color: {PANEL_DARK}; font-size: 16px;
        }}
        .wpatlas-navlinks span.active {{
            color: {ACCENT_GREEN}; border-bottom: 3px solid {ACCENT_GREEN}; padding-bottom: 4px;
        }}
        .wpatlas-navlinks span.disabled {{
            color: #9aa0a6;
        }}

        .panel-header {{
            background: {PANEL_DARK}; color: white; padding: 8px 16px;
            font-weight: 700; font-size: 15px; border-radius: 4px 4px 0 0;
            text-align: center; margin-bottom: 0;
        }}
        .panel-body {{
            border: 1px solid #d7dbe0; border-top: none; padding: 10px 14px 14px 14px;
            border-radius: 0 0 4px 4px; margin-bottom: 18px; background: white;
        }}
        .sidebar-header {{
            background: {PANEL_DARK}; color: white; padding: 8px 12px; font-weight: 700;
            border-radius: 4px; text-align: center; margin-bottom: 10px;
        }}
        section[data-testid="stSidebar"] {{background: #eef1f4;}}

        .stTabs [data-baseweb="tab-list"] {{gap: 32px; border-bottom: 2px solid #d7dbe0;}}
        .stTabs [data-baseweb="tab"] {{font-weight: 700; font-size: 18px; padding-top: 4px;}}
        .stTabs [aria-selected="true"] {{color: {ACCENT_GREEN} !important;}}
        .stTabs [data-baseweb="tab-highlight"] {{background-color: {ACCENT_GREEN} !important;}}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_navbar():
    """A static brand bar - rendered once, above the real (native, clickable)
    Streamlit tabs. Earlier this also drew a row of 'Home / Trends / Comparison /
    Scenarios / Nexus' text links, but those were purely decorative (no click
    handler) and, worse, visually overlapped the real tab control due to a
    negative-margin CSS trick, making the genuine tabs impossible to click."""
    st.markdown(
        """
        <div class="wpatlas-navbar">
            <div class="brand">\U0001F4A7 Water Productivity Atlas &ndash; India</div>
            <div class="wpatlas-navlinks"><span class="disabled">Scenarios &amp; Nexus: coming soon</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def panel(title):
    """Context-manager-like helper: call panel_start(title) ... panel_end()."""
    st.markdown(f'<div class="panel-header">{title}</div>', unsafe_allow_html=True)


def panel_open(title):
    st.markdown(f'<div class="panel-header">{title}</div><div class="panel-body">', unsafe_allow_html=True)


def panel_close():
    st.markdown("</div>", unsafe_allow_html=True)


def key(s):
    return re.sub(r"\s+", " ", str(s).strip().upper())


# ---------------------------------------------------------------------------
# Data loading (cached)
# ---------------------------------------------------------------------------
@st.cache_data
def load_district_data():
    return pd.read_parquet(f"{DATA_DIR}/district_data.parquet")


@st.cache_data
def load_state_data():
    return pd.read_parquet(f"{DATA_DIR}/state_data.parquet")


@st.cache_data
def load_state_map_data():
    return pd.read_parquet(f"{DATA_DIR}/state_data_for_map.parquet")


@st.cache_data
def load_national_data():
    return pd.read_parquet(f"{DATA_DIR}/national_data.parquet")


@st.cache_data
def load_district_geojson():
    with open(f"{DATA_DIR}/districts.geojson") as f:
        gj = json.load(f)
    for feat in gj["features"]:
        p = feat["properties"]
        p["JOIN_KEY"] = f"{p['STATE_KEY']}||{p['DISTRICT_KEY']}"
    return gj


@st.cache_data
def load_state_geojson():
    with open(f"{DATA_DIR}/states.geojson") as f:
        gj = json.load(f)
    return gj


def get_level_data(level):
    """level: 'District', 'State', or 'National'.
    Returns (attribute df, geo-ready df for maps)."""
    if level == "District":
        df = load_district_data()
        return df, df
    elif level == "State":
        return load_state_data(), load_state_map_data()
    else:
        df = load_national_data()
        return df, df


# ---------------------------------------------------------------------------
# Quantile classification for the choropleth (matches the atlas's discrete legend)
# ---------------------------------------------------------------------------
NA_LABEL = "Data not available/reliable"


def classify_quantile(values, n=4, decimals=2):
    """Bins positive values into n quantile classes with labels like '[0.28,0.58]',
    everything else (<=0 or NaN) goes to NA_LABEL. Returns (labels Series, color_map, order)."""
    s = pd.to_numeric(values, errors="coerce")
    valid = s[s > 0]
    out = pd.Series(NA_LABEL, index=s.index, dtype=object)

    if valid.empty or valid.nunique() < 2:
        return out, {NA_LABEL: NA_COLOR}, [NA_LABEL]

    n_bins = min(n, valid.nunique())
    try:
        bins, edges = pd.qcut(valid, q=n_bins, duplicates="drop", retbins=True)
    except Exception:
        bins, edges = pd.cut(valid, bins=n_bins, retbins=True)
        n_bins = len(edges) - 1

    cat_labels = []
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        bracket = "[" if i == 0 else "("
        cat_labels.append(f"{bracket}{lo:.{decimals}f},{hi:.{decimals}f}]")

    bins = bins.cat.rename_categories(cat_labels)
    out.loc[valid.index] = bins.astype(str)

    color_map = {lab: QUANTILE_COLORS[i % len(QUANTILE_COLORS)] for i, lab in enumerate(cat_labels)}
    color_map[NA_LABEL] = NA_COLOR
    order = cat_labels + [NA_LABEL]
    return out, color_map, order
