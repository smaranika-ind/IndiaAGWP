"""Indicator metadata: column name -> label, unit, category, short code (for legend titles)."""

INDICATORS = {
    "PROD_TOL":    {"label": "Total Production", "unit": "tonnes", "short": "PROD", "cat": "Production & Area"},
    "THA_TOL":     {"label": "Total Cropped Area", "unit": "ha", "short": "AREA", "cat": "Production & Area"},
    "TYLD_TOL":    {"label": "Yield", "unit": "t/ha", "short": "YIELD", "cat": "Production & Area"},

    "TCWU_TOL":    {"label": "Total Crop Water Use (TCWU)", "unit": "MCM", "short": "TCWU", "cat": "Water Use"},
    "IRCWU_TOL":   {"label": "Blue Water Use (Irrigation)", "unit": "MCM", "short": "IRCWU", "cat": "Water Use"},
    "RFCWU_TOL":   {"label": "Green Water Use (Rainfall)", "unit": "MCM", "short": "RFCWU", "cat": "Water Use"},

    "PWP_TOL":     {"label": "Physical Water Productivity", "unit": "Kg m\u207b\u00b3", "short": "PWP", "cat": "Water Productivity", "hib": True},
    "EWP_TOL":     {"label": "Economic Water Productivity", "unit": "USD m\u207b\u00b3", "short": "EWP", "cat": "Water Productivity", "hib": True},
    "NCWP_TOL":    {"label": "Nutritional Water Productivity (Calorie)", "unit": "M kcal m\u207b\u00b3", "short": "NCWP", "cat": "Water Productivity", "hib": True},
    "NPWP_TOL":    {"label": "Nutritional Water Productivity (Protein)", "unit": "kg protein-equiv. m\u207b\u00b3", "short": "NPWP", "cat": "Water Productivity", "hib": True},
    "NFWP_TOL":    {"label": "Nutritional Water Productivity (Fat)", "unit": "kg fat-equiv. m\u207b\u00b3", "short": "NFWP", "cat": "Water Productivity", "hib": True},

    "TWFP_TOL":    {"label": "Total Water Footprint", "unit": "m\u00b3/tonne", "short": "TWFP", "cat": "Water Footprint", "hib": False},
    "TBLWFP_TOL":  {"label": "Blue Water Footprint", "unit": "m\u00b3/tonne", "short": "BLWFP", "cat": "Water Footprint", "hib": False},
    "TGRWFP_TOL":  {"label": "Green Water Footprint", "unit": "m\u00b3/tonne", "short": "GRWFP", "cat": "Water Footprint", "hib": False},

    "TCWFP_TOL":   {"label": "Total Calorie Water Footprint", "unit": "m\u00b3/M kcal", "short": "TCWFP", "cat": "Nutritional Footprint", "hib": False},
    "TBLCWFP_TOL": {"label": "Blue Calorie Water Footprint", "unit": "m\u00b3/M kcal", "short": "BLCWFP", "cat": "Nutritional Footprint", "hib": False},
    "TGRCWFP_TOL": {"label": "Green Calorie Water Footprint", "unit": "m\u00b3/M kcal", "short": "GRCWFP", "cat": "Nutritional Footprint", "hib": False},

    "TPWFP_TOL":   {"label": "Total Protein Water Footprint", "unit": "m\u00b3/t protein-equiv.", "short": "TPWFP", "cat": "Nutritional Footprint", "hib": False},
    "TBLPWFP_TOL": {"label": "Blue Protein Water Footprint", "unit": "m\u00b3/t protein-equiv.", "short": "BLPWFP", "cat": "Nutritional Footprint", "hib": False},
    "TGRPWFP_TOL": {"label": "Green Protein Water Footprint", "unit": "m\u00b3/t protein-equiv.", "short": "GRPWFP", "cat": "Nutritional Footprint", "hib": False},

    "TFWFP_TOL":   {"label": "Total Fat Water Footprint", "unit": "m\u00b3/t fat-equiv.", "short": "TFWFP", "cat": "Nutritional Footprint", "hib": False},
    "TBLFWFP_TOL": {"label": "Blue Fat Water Footprint", "unit": "m\u00b3/t fat-equiv.", "short": "BLFWFP", "cat": "Nutritional Footprint", "hib": False},
    "TGRFWFP_TOL": {"label": "Green Fat Water Footprint", "unit": "m\u00b3/t fat-equiv.", "short": "GRFWFP", "cat": "Nutritional Footprint", "hib": False},
}

CATEGORY_ORDER = ["Production & Area", "Water Use", "Water Productivity",
                   "Water Footprint", "Nutritional Footprint"]


def indicator_options():
    """Returns (categories dict label-grouped, label->col map) for a grouped selectbox."""
    label_to_col = {v["label"]: k for k, v in INDICATORS.items()}
    categories = {}
    for col, meta in INDICATORS.items():
        categories.setdefault(meta["cat"], []).append(meta["label"])
    return categories, label_to_col


def all_labels_flat():
    """Flat list of every indicator label, ordered by category, for a single selectbox."""
    categories, _ = indicator_options()
    out = []
    for cat in CATEGORY_ORDER:
        out.extend(categories.get(cat, []))
    return out


def unit_of(col):
    return INDICATORS.get(col, {}).get("unit", "")


def label_of(col):
    return INDICATORS.get(col, {}).get("label", col)


def short_of(col):
    return INDICATORS.get(col, {}).get("short", col.replace("_TOL", ""))


def higher_is_better(col):
    return INDICATORS.get(col, {}).get("hib", True)
