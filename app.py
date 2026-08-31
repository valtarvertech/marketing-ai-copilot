"""
Marketing AI Copilot -- Streamlit entry point.

This file is intentionally thin: load the synthetic data once, let the
user pick a section from the sidebar, and hand off to the matching
render_* function in src/ui_sections.py. All of the actual analysis
(metrics, comparisons, investigation, pacing, recommendations, ...)
lives in src/ so it can be tested independently of the UI -- see tests/.

Run with:  streamlit run app.py
"""

import streamlit as st

from src.data_loader import load_all, DataNotFoundError
from src import ui_sections
from src.ui_components import inject_theme, demo_data_tag, nav_flow_legend

st.set_page_config(page_title="Marketing AI Copilot", layout="wide")
inject_theme()

# Order matters beyond readability: it's grouped 2/3/3/2 to match the
# product's four-stage reasoning flow (Overview / Diagnose / Understand /
# Act), and src/ui_components.py's CSS draws divider lines at the 3rd,
# 6th, and 9th sidebar item assuming exactly this grouping.
SECTIONS = {
    "Executive Overview": ui_sections.render_executive_overview,
    "Performance Intelligence": ui_sections.render_performance_intelligence,
    "Campaign Intelligence": ui_sections.render_campaign_intelligence,
    "Keyword Intelligence": ui_sections.render_keyword_intelligence,
    "Search Term Intelligence": ui_sections.render_search_term_intelligence,
    "Budget Pacing": ui_sections.render_budget_pacing,
    "Competitive Intelligence": ui_sections.render_competitive_intelligence,
    "Change Intelligence": ui_sections.render_change_intelligence,
    "Optimization Center": ui_sections.render_optimization_center,
    "Ask My Account": ui_sections.render_ask_my_account,
}


@st.cache_data
def _load_data():
    return load_all()


def main():
    # A cross-page "Investigate ->" button (see src/ui_sections.py) sets
    # pending_nav_section instead of nav_section directly, since the sidebar
    # radio below is already instantiated by the time such a button's click
    # handler runs -- Streamlit forbids writing a widget's own session_state
    # key after that widget has been drawn in the same run. Consuming the
    # pending value here, before the radio is created, is the safe point.
    if "pending_nav_section" in st.session_state:
        st.session_state["nav_section"] = st.session_state.pop("pending_nav_section")

    st.sidebar.title("Marketing AI Copilot")
    st.sidebar.caption("Marketing Intelligence & Decision Support")
    with st.sidebar:
        demo_data_tag()
    st.sidebar.divider()
    with st.sidebar:
        nav_flow_legend()
    section = st.sidebar.radio("Navigate", list(SECTIONS.keys()), label_visibility="collapsed", key="nav_section")

    try:
        data = _load_data()
    except DataNotFoundError as e:
        st.error(str(e))
        st.stop()

    SECTIONS[section](data)


if __name__ == "__main__":
    main()
