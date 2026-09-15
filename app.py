import os
import sys

# Ensure this script's own folder is importable regardless of the working
# directory the host (e.g. Streamlit Community Cloud) launches from.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

from common import inject_css, render_navbar
from atlas_view import render_sidebar_controls
from tab_trends import render_trends
from tab_comparisons import render_comparisons

st.set_page_config(page_title="Water Productivity Atlas - India", layout="wide")
inject_css()
render_navbar()

sel = render_sidebar_controls()

tab_trends, tab_comparisons = st.tabs(["Trends", "Comparison"])

with tab_trends:
    render_trends(sel)

with tab_comparisons:
    render_comparisons(sel)

st.sidebar.markdown("---")
st.sidebar.caption(
    "District/crop/year crop-water-use & production data, 1999-2022, 78 crops. "
    "Scenarios and Nexus need extra data - see README."
)
