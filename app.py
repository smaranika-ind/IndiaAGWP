import os
import sys

# Ensure this script's own folder is importable regardless of the working
# directory the host (e.g. Streamlit Community Cloud) launches from.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

from common import inject_css, render_navbar
from tab_trends import render_trends
from tab_comparisons import render_comparisons

st.set_page_config(page_title="Water Productivity Atlas - India", layout="wide")
inject_css()
render_navbar()

# A mode selector (styled to look like tabs) rather than st.tabs(): Trends and
# Comparison need genuinely different sidebars (Comparison uses multi-select
# State(s)/Crop(s), Trends uses single-select + Tertiary unit). With st.tabs(),
# every tab's body runs on every script pass regardless of which is visually
# selected, so two different sidebar forms would both render at once. A radio
# only executes the branch that's actually selected, avoiding that.
mode = st.radio("Section", ["Trends", "Comparison"], horizontal=True,
                label_visibility="collapsed", key="page_mode")

if mode == "Trends":
    render_trends()
else:
    render_comparisons()

st.sidebar.markdown("---")
st.sidebar.caption(
    "District/crop/year crop-water-use & production data, 1999-2022, 78 crops. "
    "Scenarios and Nexus need extra data - see README."
)
