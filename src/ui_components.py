"""
Shared, presentation-only UI building blocks.

The dark SaaS look mostly comes from .streamlit/config.toml's native
theme (reliable across Streamlit versions, no brittle CSS needed for
backgrounds/fonts/widgets). This module adds a small, narrowly-scoped
CSS layer -- only for things the theme config can't reach (status
badges, insight cards, section rhythm) -- plus the small set of
Python helpers every page uses to stay visually consistent: a page
header, a section heading, a status badge, an insight card, and a
neutral empty-state message.

Business logic never lives here -- these functions only render what
they're given.
"""

import streamlit as st

_CSS = """
<style>
/* Marketing AI Copilot brand: navy #00193F (navigation/foundation) +
   electric blue #0059F9 (interactive/brand/AI accent). Semantic colors
   (green/red/amber/gray) are intentionally kept separate from brand
   color -- #0059F9 means "selected/interactive/brand", never "good". */
.mac-page-desc { color: #9AA4B2; font-size: 0.92rem; margin-top: -0.4rem; margin-bottom: 0.25rem; }
.mac-section-desc { color: #9AA4B2; font-size: 0.85rem; margin-top: -0.35rem; margin-bottom: 0.5rem; }

.mac-badge {
    display: inline-block; padding: 0.12rem 0.55rem; border-radius: 999px;
    font-size: 0.72rem; font-weight: 600; letter-spacing: 0.02em;
    border: 1px solid transparent; white-space: nowrap;
}
.mac-badge-positive { background: rgba(34,197,94,0.14); color: #4ADE80; border-color: rgba(34,197,94,0.35); }
.mac-badge-negative { background: rgba(239,68,68,0.14); color: #F87171; border-color: rgba(239,68,68,0.35); }
.mac-badge-neutral  { background: rgba(148,163,184,0.14); color: #CBD5E1; border-color: rgba(148,163,184,0.30); }
.mac-badge-warning  { background: rgba(245,158,11,0.14); color: #FBBF24; border-color: rgba(245,158,11,0.35); }
.mac-badge-info     { background: rgba(0,89,249,0.16); color: #7FACFF; border-color: rgba(0,89,249,0.45); }

.mac-card {
    border: 1px solid #262B3A; background: #131722; border-radius: 10px;
    padding: 0.85rem 1rem; margin-bottom: 0.6rem;
}
.mac-card-title { font-weight: 600; font-size: 0.95rem; margin-bottom: 0.25rem; }
.mac-card-body { color: #C2C8D2; font-size: 0.87rem; line-height: 1.45; }
.mac-card-positive { border-left: 3px solid #22C55E; }
.mac-card-negative { border-left: 3px solid #EF4444; }
.mac-card-warning  { border-left: 3px solid #F59E0B; }
.mac-card-neutral  { border-left: 3px solid #0059F9; }

/* Professional environment badge -- two-line, brand-navy accented.
   Deliberately not hidden or minimized: the synthetic-data disclosure
   is a credibility signal, not something to downplay. */
.mac-env-badge {
    display: block; padding: 0.5rem 0.7rem; border-radius: 8px;
    background: rgba(0,89,249,0.10); border: 1px solid rgba(0,89,249,0.35);
    margin: 0.3rem 0 0.2rem 0;
}
.mac-env-badge-title {
    color: #9DC1FF; font-size: 0.7rem; font-weight: 700; letter-spacing: 0.08em;
}
.mac-env-badge-sub { color: #B7C4DA; font-size: 0.72rem; margin-top: 0.1rem; }

section[data-testid="stSidebar"] .mac-nav-label {
    color: #8FA3C9; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.08em;
    margin: 0.7rem 0 0.15rem 0;
}
.mac-flow-legend {
    color: #7C8BAE; font-size: 0.72rem; line-height: 1.5; margin: 0.1rem 0 0.4rem 0;
}
.mac-flow-legend b { color: #B9C7E6; }

/* Groups the 10 nav items visually into the product's four reasoning
   stages (Overview / Diagnose / Understand / Act) without restructuring
   the underlying radio widget -- a single st.radio keeps navigation
   state simple and every existing test working; this is presentation
   only, targeting Streamlit's stable radiogroup markup. Page order in
   app.py's SECTIONS dict must stay grouped 2/3/3/2 for these positions
   (3rd, 6th, 9th item) to land on the right boundaries. */
section[data-testid="stSidebar"] div[role="radiogroup"] > label:nth-of-type(3),
section[data-testid="stSidebar"] div[role="radiogroup"] > label:nth-of-type(6),
section[data-testid="stSidebar"] div[role="radiogroup"] > label:nth-of-type(9) {
    margin-top: 0.85rem; padding-top: 0.55rem;
    border-top: 1px solid rgba(255,255,255,0.09);
}
</style>
"""

_BADGE_KIND = {
    "Favorable": "positive", "Unfavorable": "negative", "Flat": "neutral",
    "Neutral": "neutral", "No data": "neutral", "Mixed": "warning",
    "Stable": "neutral", "On pace": "positive", "Under pacing": "warning",
    "Over pacing": "warning", "At Risk": "negative",
}


def inject_theme():
    st.markdown(_CSS, unsafe_allow_html=True)


def page_header(title, description=None, account_line=None):
    st.title(title)
    if account_line:
        st.caption(account_line)
    if description:
        st.markdown(f'<div class="mac-page-desc">{description}</div>', unsafe_allow_html=True)


def section_heading(title, description=None):
    st.markdown(f"##### {title}")
    if description:
        st.markdown(f'<div class="mac-section-desc">{description}</div>', unsafe_allow_html=True)


def badge_html(label, kind=None):
    kind = kind or _BADGE_KIND.get(label, "neutral")
    return f'<span class="mac-badge mac-badge-{kind}">{label}</span>'


def render_badge(label, kind=None):
    st.markdown(badge_html(label, kind), unsafe_allow_html=True)


def status_badge_kind(label):
    return _BADGE_KIND.get(label, "neutral")


def insight_card(title, body, kind="neutral", badge=None):
    badge_markup = f' {badge_html(badge)}' if badge else ""
    st.markdown(
        f'<div class="mac-card mac-card-{kind}">'
        f'<div class="mac-card-title">{title}{badge_markup}</div>'
        f'<div class="mac-card-body">{body}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )


def empty_state(message):
    st.info(message)


def demo_data_tag():
    """Professional environment badge -- deliberately visible, never
    minimized. Disclosing synthetic data is a credibility signal."""
    st.markdown(
        '<div class="mac-env-badge">'
        '<div class="mac-env-badge-title">DEMO ENVIRONMENT</div>'
        '<div class="mac-env-badge-sub">Synthetic dataset</div>'
        "</div>",
        unsafe_allow_html=True,
    )


def nav_group_label(text):
    """A small caption-style group header inside the sidebar (e.g.
    "OVERVIEW", "DIAGNOSE") -- organizes navigation by the product's
    reasoning flow rather than a flat control list."""
    st.markdown(f'<div class="mac-nav-label">{text}</div>', unsafe_allow_html=True)


def nav_flow_legend():
    """The four-stage reasoning flow that groups the sidebar's 10 pages,
    shown once above the navigation list."""
    st.markdown(
        '<div class="mac-flow-legend"><b>What happened</b> → <b>Where</b> → '
        '<b>Why</b> → <b>What next</b></div>',
        unsafe_allow_html=True,
    )
