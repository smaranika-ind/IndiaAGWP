from atlas_view import render_sidebar_controls_comparison, render_comparison_view


def render_comparisons():
    sel = render_sidebar_controls_comparison()
    render_comparison_view(sel)
