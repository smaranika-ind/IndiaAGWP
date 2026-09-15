from atlas_view import render_sidebar_controls_trends, render_trends_view


def render_trends():
    sel = render_sidebar_controls_trends()
    render_trends_view(sel)
