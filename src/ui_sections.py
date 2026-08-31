"""
Streamlit rendering functions, one per navigation section.

Kept separate from app.py (the entry point) so app.py stays a short,
readable router: load data once, pick a section from the sidebar, call
the matching render_* function. Every function here reads from the
already-loaded DataFrames and calls into src/ for all the actual math --
this file only formats results as Streamlit widgets.
"""

from datetime import timedelta

import pandas as pd
import streamlit as st

from src.metrics import aggregate, favorability, METRIC_DIRECTION
from src.comparisons import (
    compare_day_over_day, compare_week_over_week, week_over_week_range, day_over_day_range,
)
from src.contribution import rank_contributors, rate_changes
from src.investigation import investigate_metric_change, investigate_range
from src.pacing import compute_pacing
from src.keyword_intelligence import (
    top_performers as top_keywords, high_spend_low_conversion as low_conv_keywords, classify_keywords,
)
from src.search_term_intelligence import negative_keyword_candidates, expansion_candidates, classify_search_terms
from src.change_intelligence import changes_for_campaign, describe_changes, performance_around_change
from src.competitive import auction_trend, summarize_competitive_pressure, generate_competitive_commentary
from src.recommendations import generate_recommendations, seed_tracked_recommendation_example
from src.question_router import answer as answer_question
from src.executive_brief import generate_brief
from src.evidence import investigate_with_evidence, build_pacing_contexts
from src.rolling import (
    rolling_8_day_dates, rolling_8_day_range, compare_rolling_8_day,
    build_daily_monitoring_table, latest_day_vs_prior_average,
    generate_8day_brief, rolling_week_ranges, build_weekly_matrix, weekly_pct_change_matrix,
    generate_5week_brief, format_date_range, split_contributors, split_rate_movers,
)
from src.formatting import (
    RAW_METRIC_LABELS, RATE_METRIC_LABELS, ALL_METRIC_LABELS as _ALL_METRIC_LABELS,
    fmt_percent, fmt_money, fmt_points, fmt_or_dash, metric_label, chronological_categories,
    METRIC_FORMATTERS as _METRIC_FORMATTERS,
)
from src.ui_components import (
    inject_theme, page_header, section_heading, render_badge, badge_html,
    status_badge_kind, insight_card, empty_state,
)

# Local aliases kept so the rest of this file (written before formatting.py
# existed) doesn't need a mechanical rename; src/formatting.py is the
# single source of truth both point to.
def _pct(x):
    return fmt_percent(x, signed=True)


_money = fmt_money


# ---------------------------------------------------------------------------
# Shared building blocks (used by Executive Overview and Performance Intelligence)
# ---------------------------------------------------------------------------
# Which way st.metric should color a KPI's delta, based on whether higher
# or lower is actually better for that metric (see src.metrics.METRIC_DIRECTION).
# "normal" = up green/down red, "inverse" = up red/down green, "off" = no color.
_DELTA_COLOR_BY_DIRECTION = {"higher_is_better": "normal", "lower_is_better": "inverse", "neutral": "off"}

_KPI_CARDS = [
    ("conversions", "Conversions", lambda v: f"{v:,.0f}"),
    ("spend", "Spend", _money),
    ("roas", "ROAS", lambda v: f"{v:.2f}x"),
    ("cpa", "CPA", _money),
    ("ctr", "CTR", lambda v: f"{v:.2%}"),
]

_BRIEF_CALLOUT = {"Favorable": "success", "Unfavorable": "error", "Mixed": "warning", "Stable": "info"}

_SNAPSHOT_COLUMNS = ["campaign", "conversions", "spend", "conversion_rate", "cpa", "roas"]
_SNAPSHOT_LABELS = {
    "campaign": "Campaign", "conversions": "Conversions", "spend": "Spend",
    "conversion_rate": "Conversion Rate", "cpa": "CPA", "roas": "ROAS",
}


def _render_kpi_cards(row, current_suffix="_current", kpi_cards=None):
    """Metric-aware KPI cards: color and a text status label both come
    from src.metrics.favorability()/METRIC_DIRECTION, so a CPA increase
    reads unfavorable (red) rather than naively green-because-it-went-up.
    `row` must have `{metric}{current_suffix}` and `{metric}_pct_change`
    for every metric in kpi_cards."""
    kpi_cards = kpi_cards or _KPI_CARDS
    cols = st.columns(len(kpi_cards))
    for col, (metric, label, fmt) in zip(cols, kpi_cards):
        pct = row[f"{metric}_pct_change"]
        status = favorability(metric, pct)
        delta_color = _DELTA_COLOR_BY_DIRECTION[METRIC_DIRECTION.get(metric, "neutral")]
        col.metric(label, fmt(row[f"{metric}{current_suffix}"]), _pct(pct), delta_color=delta_color)
        col.caption(status)


def _render_brief_callout(brief):
    getattr(st, _BRIEF_CALLOUT.get(brief["overall"], "info"))(f"**{brief['overall']}.** {brief['summary']}")


def _format_metric_table(raw_table):
    """raw_table: DataFrame indexed by metric key, any columns (dates or
    week labels). Returns the same shape with metric-aware formatted
    strings and human-readable row labels -- the shared "clean table"
    treatment used by both rolling monitoring tables."""
    # Built as a fresh object-dtype frame rather than mutating a numeric
    # copy in place -- assigning formatted strings into a float64 frame
    # row-by-row triggers a pandas dtype-compatibility warning.
    formatted = pd.DataFrame(index=raw_table.index, columns=raw_table.columns, dtype=object)
    for metric in raw_table.index:
        fmt = _METRIC_FORMATTERS.get(metric, lambda v: f"{v:,.2f}")
        formatted.loc[metric] = raw_table.loc[metric].apply(fmt)
    formatted.index = [_ALL_METRIC_LABELS.get(m, m) for m in formatted.index]
    return formatted


def _render_monitoring_table(raw_table, mode="values", newest_suffix=" (Latest)"):
    """Render a metrics-as-rows table with the newest (rightmost) column
    visually highlighted. mode="values" formats each row by metric type;
    mode="pct" formats every cell as a signed percentage (used for the
    week-over-prior-week view)."""
    if mode == "pct":
        formatted = pd.DataFrame(index=raw_table.index, columns=raw_table.columns, dtype=object)
        for metric in raw_table.index:
            formatted.loc[metric] = raw_table.loc[metric].apply(_pct)
        formatted.index = [_ALL_METRIC_LABELS.get(m, m) for m in formatted.index]
    else:
        formatted = _format_metric_table(raw_table)

    col_labels = [str(c) for c in formatted.columns]
    col_labels[-1] = col_labels[-1] + newest_suffix
    formatted.columns = col_labels

    styled = formatted.style.set_properties(
        subset=[col_labels[-1]], **{"background-color": "rgba(99,102,241,0.15)", "font-weight": "600"}
    )
    st.dataframe(styled, use_container_width=True)


def _clean_metric_table(df, metric, id_col="campaign", id_label="Campaign"):
    """Turn a wide `{metric}_<suffix>` comparison/ranking table (from
    comparisons.compare(), contribution.rank_contributors()/rate_changes(),
    or rolling.latest_day_vs_prior_average()) into a presentation-ready
    table: human labels, metric-aware formatting, no technical field
    names, no index."""
    label = _ALL_METRIC_LABELS.get(metric, metric)
    fmt = _METRIC_FORMATTERS.get(metric, lambda v: f"{v:,.2f}")
    out = pd.DataFrame({id_label: df[id_col].values}) if id_col in df.columns else pd.DataFrame()

    suffix_labels = [
        ("_current", f"{label} (Current)"), ("_previous", f"{label} (Previous)"),
        ("_latest", f"{label} (Latest)"), ("_prior_avg", f"{label} (Prior Avg)"),
    ]
    for suffix, col_label in suffix_labels:
        col = f"{metric}{suffix}"
        if col in df.columns:
            out[col_label] = df[col].apply(fmt)

    if f"{metric}_abs_change" in df.columns:
        out["Change"] = df[f"{metric}_abs_change"].apply(fmt)
    if f"{metric}_pct_change" in df.columns:
        out["% Change"] = df[f"{metric}_pct_change"].apply(_pct)
    if "contribution_share" in df.columns:
        out["Contribution Share"] = df["contribution_share"].apply(
            lambda v: "n/a" if pd.isna(v) else f"{v:+.0%}"
        )
    return out


# ---------------------------------------------------------------------------
# Executive Overview
# ---------------------------------------------------------------------------
def render_executive_overview(data):
    campaigns = data["campaigns"]
    cur_start, cur_end, prev_start, prev_end = rolling_8_day_range(campaigns)

    page_header(
        "Executive Overview",
        description="What is happening in this account right now?",
        account_line="ConnectWave Communications",
    )
    st.caption(f"Reporting period: {format_date_range(cur_start, cur_end)} (rolling 8 days)")

    st.markdown("##### Account Health")
    brief = generate_brief(campaigns, current_range=(cur_start, cur_end), previous_range=(prev_start, prev_end))
    _render_brief_callout(brief)

    st.divider()

    st.markdown("##### Primary KPIs")
    st.caption(f"{format_date_range(cur_start, cur_end)} vs. the preceding 8-day period, "
               f"{format_date_range(prev_start, prev_end)}.")
    rolling_8day = compare_rolling_8_day(campaigns, group_by=None).iloc[0]
    _render_kpi_cards(rolling_8day, current_suffix="_current")

    st.divider()

    st.markdown("##### Highest-Priority Item")
    recs_preview = generate_recommendations(
        campaigns, data["keywords"], data["search_terms"], data["changes"], data["auction_insights"], cur_end,
    )
    top_item = next((r for r in recs_preview if r.category == "High Priority"), None) or \
        next((r for r in recs_preview if r.category == "Opportunity"), None)
    if top_item:
        insight_card(
            top_item.title, f"{top_item.reason} Suggested action: {top_item.suggested_action}",
            kind="negative" if top_item.category == "High Priority" else "positive",
            badge=top_item.category,
        )
    else:
        empty_state("No high-priority issues or standout opportunities were identified this period.")

    st.divider()

    st.markdown("##### Rolling 8-Day Trend")
    metric_choice = st.selectbox(
        "Metric", list(RAW_METRIC_LABELS.keys()), format_func=lambda m: RAW_METRIC_LABELS[m], key="exec_trend_metric"
    )
    daily_totals = campaigns.groupby("date")[list(RAW_METRIC_LABELS.keys())].sum()
    trend_df = daily_totals[[metric_choice]].copy()
    trend_df.index = pd.to_datetime(trend_df.index)
    trend_df.columns = ["Daily"]
    trend_df["7-Day Avg"] = trend_df["Daily"].rolling(7, min_periods=1).mean()

    st.caption(f"{RAW_METRIC_LABELS[metric_choice]} — {trend_df.index.min().date()} to {trend_df.index.max().date()} "
               f"(full 90-day history shown; rolling 7-day average smooths day-of-week noise).")
    st.line_chart(trend_df, height=260)

    changes = data.get("changes")
    if changes is not None and not changes.empty:
        window_changes = changes[(changes["date"] >= cur_start) & (changes["date"] <= cur_end)]
        window_changes = window_changes.sort_values("date")
        if not window_changes.empty:
            event_list = "; ".join(f"{row['date']} – {row['campaign']}: {row['change_type'].replace('_', ' ')}"
                                    for _, row in window_changes.iterrows())
            st.caption(
                f"Account changes logged during the current 8-day period (shown for timing context only — "
                f"this does not prove any of them caused the trend above; see Change Intelligence "
                f"for full detail): {event_list}."
            )

    st.divider()

    st.markdown("##### Campaign Snapshot")
    st.caption(f"{format_date_range(cur_start, cur_end)}. Decision-focused view -- the full metric "
               "breakdown lives in Campaign Intelligence.")
    recent = campaigns[(campaigns["date"] >= cur_start) & (campaigns["date"] <= cur_end)]
    perf = aggregate(recent, group_by="campaign")
    by_campaign_change = compare_rolling_8_day(campaigns, group_by="campaign").set_index("campaign")
    perf = perf.set_index("campaign")
    perf["trend_status"] = [
        favorability("conversions", by_campaign_change.loc[c, "conversions_pct_change"]) if c in by_campaign_change.index else "No data"
        for c in perf.index
    ]
    perf = perf.reset_index().sort_values("conversions", ascending=False)

    snapshot = perf[_SNAPSHOT_COLUMNS + ["trend_status"]].rename(columns={**_SNAPSHOT_LABELS, "trend_status": "Trend / Status"})
    styled = snapshot.style.format({
        "Conversions": "{:,.0f}", "Spend": "${:,.2f}", "Conversion Rate": "{:.2%}",
        "CPA": "${:,.2f}", "ROAS": "{:.2f}x",
    }).hide(axis="index")
    st.dataframe(styled, use_container_width=True)

    st.divider()

    st.markdown("##### Attention & Opportunity")
    st.caption("Highest-priority items from Optimization Center -- see that page for the complete, evidence-backed list.")
    needs_attention = [r for r in recs_preview if r.category == "High Priority"]
    opportunities = [r for r in recs_preview if r.category == "Opportunity"]
    monitoring_count = sum(1 for r in recs_preview if r.category in ("Investigate", "Monitor"))

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"**Needs Attention** {badge_html(str(len(needs_attention)), 'negative')}", unsafe_allow_html=True)
        if needs_attention:
            for r in needs_attention[:3]:
                insight_card(r.title, r.reason, kind="negative")
        else:
            empty_state("Nothing needs urgent attention right now.")
    with col2:
        st.markdown(f"**Opportunities** {badge_html(str(len(opportunities)), 'positive')}", unsafe_allow_html=True)
        if opportunities:
            for r in opportunities[:3]:
                insight_card(r.title, r.reason, kind="positive")
        else:
            empty_state("No standout opportunities identified this period.")
    with col3:
        st.markdown(f"**Stable / Monitoring** {badge_html(str(monitoring_count), 'neutral')}", unsafe_allow_html=True)
        st.caption(f"{monitoring_count} item(s) worth periodic review -- see Optimization Center for detail.")

    st.divider()

    with st.expander("Weekly Performance (deeper supporting detail)"):
        st.caption("Latest weeks, actual date ranges, key metrics compared side by side.")
        week_ranges = rolling_week_ranges(campaigns, num_weeks=5)
        weekly_metric = st.selectbox(
            "Metric", ["conversions", "spend", "roas", "cpa", "ctr", "conversion_rate"],
            format_func=lambda m: _ALL_METRIC_LABELS.get(m, RAW_METRIC_LABELS.get(m, m)), key="exec_weekly_metric",
        )
        weekly_matrix = build_weekly_matrix(campaigns, week_ranges)
        _render_monitoring_table(weekly_matrix.loc[[weekly_metric]], mode="values")


# ---------------------------------------------------------------------------
# Performance Intelligence
# ---------------------------------------------------------------------------
def _investigate_button(label, campaign, metric, key):
    """A button that jumps to Campaign Intelligence's investigation tool
    pre-filled for `campaign`/`metric`. Uses session_state + rerun rather
    than claiming causation here -- it's a pointer to evidence, not a verdict.

    Sets "pending_*" keys rather than the target widgets' own keys directly:
    those widgets (the sidebar nav radio, Campaign Intelligence's pickers)
    were already instantiated earlier in this same script run, and Streamlit
    forbids writing to a widget's session_state key after it's been drawn.
    The pending values are consumed at the top of the target page's render
    function, before its widgets are (re-)created on the next run."""
    if st.button(label, key=key):
        st.session_state["pending_nav_section"] = "Campaign Intelligence"
        st.session_state["pending_ci_campaign_pick"] = campaign
        st.session_state["pending_ci_metric_pick"] = metric
        st.session_state["pending_ci_period_pick"] = "week_over_week"
        st.rerun()


def _render_wow_driver_analysis(campaigns_df, current_range, previous_range):
    """Shared by Rolling 5 Weeks (newest vs. preceding displayed week).
    Additive metrics get mathematically valid contribution splitting;
    ratio metrics get meaningful deterioration/improvement ranking --
    the two are never mixed, since a ratio's per-campaign changes don't
    sum to an account-level change."""
    all_metrics = {**RAW_METRIC_LABELS, **RATE_METRIC_LABELS}
    metric_pick = st.selectbox(
        "Metric", list(all_metrics.keys()), format_func=lambda m: all_metrics[m], key="pi_wow_metric"
    )

    if metric_pick in RAW_METRIC_LABELS:
        ranked, total_change = rank_contributors(campaigns_df, metric_pick, current_range, previous_range)
        detractors, offsets = split_contributors(ranked, metric_pick)
        label = RAW_METRIC_LABELS[metric_pick]
        st.caption(f"Account-level {label.lower()} changed by {_METRIC_FORMATTERS[metric_pick](total_change)}.")

        st.markdown("**Largest Negative Contributors**")
        if detractors.empty:
            st.info("No campaign pulled this metric down.")
        else:
            st.dataframe(_clean_metric_table(detractors, metric_pick), hide_index=True, use_container_width=True)
            pick = st.selectbox(
                "Investigate a campaign from above", detractors["campaign"].tolist(), key="pi_wow_investigate_detractor"
            )
            _investigate_button(f"Investigate {pick} →", pick, metric_pick, key="pi_wow_investigate_btn_detractor")

        st.markdown("**Positive Offsets**")
        if offsets.empty:
            st.info("No campaign offset the decline.")
        else:
            st.dataframe(_clean_metric_table(offsets, metric_pick), hide_index=True, use_container_width=True)
    else:
        rc = rate_changes(campaigns_df, metric_pick, current_range, previous_range)
        deteriorating, improving = split_rate_movers(rc, metric_pick)
        label = RATE_METRIC_LABELS[metric_pick]
        st.caption(f"Ranked by meaningful {label} movement per campaign (ratio metrics aren't additive across campaigns).")

        st.markdown("**Meaningful Deterioration**")
        if deteriorating.empty:
            st.info(f"No campaign's {label} deteriorated meaningfully.")
        else:
            st.dataframe(_clean_metric_table(deteriorating, metric_pick), hide_index=True, use_container_width=True)
            pick = st.selectbox(
                "Investigate a campaign from above", deteriorating["campaign"].tolist(), key="pi_wow_investigate_deteriorating"
            )
            _investigate_button(f"Investigate {pick} →", pick, metric_pick, key="pi_wow_investigate_btn_rate")

        st.markdown("**Meaningful Improvement**")
        if improving.empty:
            st.info(f"No campaign's {label} improved meaningfully.")
        else:
            st.dataframe(_clean_metric_table(improving, metric_pick), hide_index=True, use_container_width=True)


def _weekday_date(d):
    return f"{d.strftime('%A, %b')} {d.day}"


def _render_rolling_8_days(campaigns_df):
    dates = rolling_8_day_dates(campaigns_df)
    st.caption(f"{format_date_range(dates[0], dates[-1])} ({len(dates)} days) — always the most "
               f"recent complete days in the dataset.")

    st.markdown("##### Latest Day vs. Trailing 7-Day Average")
    diff = latest_day_vs_prior_average(campaigns_df)
    row = diff["table"].iloc[0]
    prior_start, prior_end = diff["prior_range"]
    st.caption(f"{_weekday_date(diff['latest_date'])} vs. the daily average of "
               f"{format_date_range(prior_start, prior_end)}.")
    _render_kpi_cards(row, current_suffix="_latest")

    st.markdown("##### Rolling 8-Day Brief")
    brief = generate_8day_brief(campaigns_df)
    _render_brief_callout(brief)
    if brief["overall"] == "Unfavorable":
        if st.button("View Drivers →", key="pi_8day_view_drivers"):
            st.session_state["pending_pi_view"] = "Rolling 5 Weeks"
            st.rerun()
        st.caption("Jumps to the Week-over-Week driver breakdown in Rolling 5 Weeks below.")

    st.divider()

    st.markdown("##### 8-Day Monitoring Table")
    table = build_daily_monitoring_table(campaigns_df, dates)
    _render_monitoring_table(table, mode="values")


def _render_rolling_5_weeks(campaigns_df):
    week_ranges = rolling_week_ranges(campaigns_df, num_weeks=5)
    st.caption(
        "Weeks shown: " + " | ".join(format_date_range(s, e) for s, e in week_ranges)
        + ". Each is always a complete, non-overlapping 7-day window ending on the latest available date -- "
          "there is no partial week by construction (unlike a calendar-week-aligned view)."
    )

    st.markdown("##### 5-Week Performance Brief")
    brief5 = generate_5week_brief(campaigns_df, num_weeks=5)
    _render_brief_callout(brief5)

    st.divider()

    st.markdown("##### Weekly Monitoring Matrix")
    show_pct = st.checkbox("Show % change from prior displayed week", key="pi_weekly_pct_toggle")
    matrix = build_weekly_matrix(campaigns_df, week_ranges)
    if show_pct:
        _render_monitoring_table(weekly_pct_change_matrix(matrix), mode="pct")
    else:
        _render_monitoring_table(matrix, mode="values")

    st.markdown("##### Weekly Trend")
    trend_metric = st.selectbox(
        "Metric", list(RAW_METRIC_LABELS.keys()) + list(RATE_METRIC_LABELS.keys()),
        format_func=lambda m: {**RAW_METRIC_LABELS, **RATE_METRIC_LABELS}[m], key="pi_weekly_trend_metric"
    )
    # matrix.columns are already in chronological order (oldest -> newest);
    # a plain string index would sort alphabetically on the chart (e.g.
    # "Aug 3-9" would land after "Aug 24-30"), so it's wrapped as an
    # explicitly-ordered category instead.
    trend_series = matrix.loc[trend_metric]
    trend_series.index = chronological_categories(trend_series.index)
    st.bar_chart(trend_series)

    st.divider()

    st.markdown("##### Week-over-Week Driver Analysis")
    current_range, previous_range = week_ranges[-1], week_ranges[-2]
    st.caption(f"Newest complete week ({format_date_range(*current_range)}) vs. the immediately "
               f"preceding week ({format_date_range(*previous_range)}).")
    _render_wow_driver_analysis(campaigns_df, current_range, previous_range)


def _render_day_over_day(campaigns_df):
    latest = campaigns_df["date"].max()
    previous = latest - timedelta(days=1)
    st.caption(f"{_weekday_date(latest)} vs. {_weekday_date(previous)}.")

    latest_is_weekend = latest.weekday() >= 5
    previous_is_weekend = previous.weekday() >= 5
    if latest_is_weekend != previous_is_weekend:
        st.caption(
            "Note: one of these two days is a weekend and the other isn't — normal weekday/weekend "
            "seasonality can explain part of any difference. Rolling 8 Days or Rolling 5 Weeks give "
            "a more like-for-like comparison."
        )

    account_cmp = compare_day_over_day(campaigns_df, group_by=None).iloc[0]
    _render_kpi_cards(account_cmp, current_suffix="_current")

    st.markdown("##### By Campaign")
    all_metrics = {**RAW_METRIC_LABELS, **RATE_METRIC_LABELS}
    metric_pick = st.selectbox(
        "Metric", list(all_metrics.keys()), format_func=lambda m: all_metrics[m], key="pi_dod_metric"
    )
    by_campaign = compare_day_over_day(campaigns_df, group_by="campaign")
    by_campaign = by_campaign.reindex(
        by_campaign[f"{metric_pick}_abs_change"].abs().sort_values(ascending=False).index
    )
    st.dataframe(_clean_metric_table(by_campaign, metric_pick), hide_index=True, use_container_width=True)


def render_performance_intelligence(data):
    _consume_pending_state("pi_view")

    page_header(
        "Performance Intelligence",
        description="What time period am I looking at? What changed? Is it meaningful? Which campaigns drove it?",
        account_line="ConnectWave Communications",
    )

    campaigns = data["campaigns"]
    view = st.radio(
        "View", ["Rolling 8 Days", "Rolling 5 Weeks", "Day over Day"], horizontal=True, key="pi_view"
    )

    if view == "Rolling 8 Days":
        _render_rolling_8_days(campaigns)
    elif view == "Rolling 5 Weeks":
        _render_rolling_5_weeks(campaigns)
    else:
        _render_day_over_day(campaigns)


# ---------------------------------------------------------------------------
# Campaign Intelligence (also where Sprint 1's original functionality lives on)
# ---------------------------------------------------------------------------
def _consume_pending_state(*keys):
    """Copy any "pending_<key>" values set by a cross-page navigation
    button into their real widget keys, before those widgets are created
    in this run. Must run before the corresponding st.* widget calls."""
    for key in keys:
        pending_key = f"pending_{key}"
        if pending_key in st.session_state:
            st.session_state[key] = st.session_state.pop(pending_key)


_STANDOUT_SPECS = [
    ("Most Conversions", "conversions", "idxmax", "neutral", lambda r: f'{r["conversions"]:,.0f} conversions -- the account\'s largest volume driver.'),
    ("Best ROAS", "roas", "idxmax", "positive", lambda r: f'{r["roas"]:.2f}x -- the account\'s most efficient return on spend.'),
    ("Highest Conversion Rate", "conversion_rate", "idxmax", "positive", lambda r: f'{r["conversion_rate"]:.1%} of clicks convert -- worth understanding what this campaign does well.'),
    ("Highest CPA", "cpa", "idxmax", "warning", lambda r: f'${r["cpa"]:,.2f} per conversion -- worth a closer look, not necessarily a problem if ROAS/conversion value remain strong.'),
]


def render_campaign_intelligence(data):
    _consume_pending_state("ci_campaign_pick", "ci_metric_pick", "ci_period_pick")

    page_header(
        "Campaign Intelligence",
        description="Which campaigns are driving performance -- top performers, efficiency leaders, "
                     "volume leaders, and emerging problems.",
        account_line="ConnectWave Communications",
    )

    campaigns = data["campaigns"]
    max_date = campaigns["date"].max()
    lookback = st.slider("Lookback window (days)", 7, 90, 30)
    window_start = max_date - timedelta(days=lookback - 1)
    recent = campaigns[(campaigns["date"] >= window_start) & (campaigns["date"] <= max_date)]
    st.caption(f"{format_date_range(window_start, max_date)} ({lookback} days)")

    perf = aggregate(recent, group_by="campaign").sort_values("conversions", ascending=False)
    display = perf.rename(columns=_ALL_METRIC_LABELS)
    styled = display.style.format({
        _ALL_METRIC_LABELS[m]: _METRIC_FORMATTERS[m] for m in _ALL_METRIC_LABELS if _ALL_METRIC_LABELS[m] in display.columns
    }).hide(axis="index")
    st.dataframe(styled, use_container_width=True)

    section_heading("Standout Campaigns", "Highest doesn't always mean best -- read each card's context.")
    cols = st.columns(len(_STANDOUT_SPECS))
    for col, (title, metric, agg_fn, kind, describe) in zip(cols, _STANDOUT_SPECS):
        row = perf.loc[getattr(perf[metric], agg_fn)()]
        with col:
            insight_card(f'{title}: "{row["campaign"]}"', describe(row), kind=kind)

    section_heading("Investigate a Specific Campaign", "Reached from elsewhere in the app? Your selection carries over automatically.")
    campaign_pick = st.selectbox("Campaign", sorted(campaigns["campaign"].unique()), key="ci_campaign_pick")
    metric_pick = st.selectbox("Metric to investigate", list(RAW_METRIC_LABELS) + list(RATE_METRIC_LABELS),
                                format_func=lambda m: {**RAW_METRIC_LABELS, **RATE_METRIC_LABELS}[m],
                                key="ci_metric_pick")
    period_pick = st.radio("Period", ["week_over_week", "day_over_day"], horizontal=True,
                            format_func=lambda p: p.replace("_", " ").title(), key="ci_period_pick")

    if period_pick == "week_over_week":
        current_range, previous_range = week_over_week_range(campaigns)[0:2], week_over_week_range(campaigns)[2:4]
    else:
        current_range, previous_range = day_over_day_range(campaigns)[0:2], day_over_day_range(campaigns)[2:4]

    report = investigate_with_evidence(
        campaigns, data["changes"], data["auction_insights"], data["search_terms"],
        metric_pick, current_range, previous_range, campaign=campaign_pick,
    )
    _render_investigation_report(report)


def _clean_performance_table(df, id_cols=None, extra_labels=None):
    """Rename id/metric columns to presentation labels, format metric
    values by type, and hide the index -- the shared "clean table"
    treatment for any aggregate()-shaped DataFrame (keyword, search-term,
    or campaign level)."""
    rename_map = {c: c.replace("_", " ").title() for c in (id_cols or [])}
    if extra_labels:
        rename_map.update(extra_labels)
    rename_map.update(_ALL_METRIC_LABELS)
    display = df.rename(columns=rename_map)
    fmt = {label: _METRIC_FORMATTERS[m] for m, label in _ALL_METRIC_LABELS.items() if label in display.columns}
    return display.style.format(fmt).hide(axis="index")


# ---------------------------------------------------------------------------
# Keyword Intelligence
# ---------------------------------------------------------------------------
_KEYWORD_STATUS_KIND = {"Strong": "positive", "Efficient": "positive", "Monitor": "neutral",
                         "Review": "warning", "Waste Candidate": "negative"}


def render_keyword_intelligence(data):
    page_header(
        "Keyword Intelligence",
        description="Which keywords are helping or hurting performance? Status combines volume, ROAS, "
                     "and relative spend -- never CPA alone.",
        account_line="ConnectWave Communications",
    )

    keywords = data["keywords"]
    max_date = keywords["date"].max()
    min_available_days = (max_date - keywords["date"].min()).days + 1

    col1, col2, col3 = st.columns(3)
    with col1:
        campaign_pick = st.selectbox("Campaign", ["All"] + sorted(keywords["campaign"].unique().tolist()), key="kw_campaign")
    with col2:
        lookback = st.slider("Lookback (days)", 7, min_available_days, min_available_days, key="kw_lookback")
    with col3:
        metric_pick = st.selectbox("Rank by", ["conversions", "clicks", "spend"], key="kw_top_metric")

    window_start = max_date - timedelta(days=lookback - 1)
    subset = keywords if campaign_pick == "All" else keywords[keywords["campaign"] == campaign_pick]
    st.caption(f"{format_date_range(window_start, max_date)} ({lookback} days)")

    classified = classify_keywords(subset, start_date=window_start, end_date=max_date)
    if classified.empty:
        empty_state(f"No keyword data available for {campaign_pick} in this window.")
        return

    sections = [
        ("Top Performers", "Strong", "High conversion volume with ROAS at or above the median for this set."),
        ("Efficiency Opportunities", "Efficient", "Above-median ROAS -- efficient, even if not the highest volume."),
        ("Needs Review", "Review", "High relative spend with below-median ROAS -- not yet a clear waste candidate."),
        ("Potential Waste", "Waste Candidate", "High relative spend AND ROAS below 1.0x (losing money on ad spend)."),
    ]
    for title, status, description in sections:
        section_heading(title, description)
        rows = classified[classified["status"] == status].sort_values(metric_pick, ascending=False)
        if rows.empty:
            empty_state(f'No keywords are currently classified "{status}" for this selection -- ' +
                        ("a positive signal." if status == "Waste Candidate" else "nothing to show yet."))
        else:
            st.dataframe(_clean_performance_table(rows, id_cols=["campaign", "keyword", "match_type", "status"]),
                         use_container_width=True)


# ---------------------------------------------------------------------------
# Search Term Intelligence
# ---------------------------------------------------------------------------
_SEARCH_TERM_RECOMMENDATION = {
    "Negative Candidate": "Add as a negative keyword -- meaningful spend with no conversions.",
    "Expansion Candidate": "Add as a dedicated keyword to gain bid/match-type control over proven demand.",
    "Needs Review": "Not yet conclusive either way -- monitor for another period before acting.",
    "Relevant": "Performing within normal range -- no action needed.",
}
_SEARCH_TERM_STATUS_KIND = {
    "Negative Candidate": "negative", "Expansion Candidate": "positive",
    "Needs Review": "warning", "Relevant": "neutral",
}


def render_search_term_intelligence(data):
    page_header(
        "Search Term Intelligence",
        description="What are users actually searching, and what should we do about it? "
                     "Recommendations only -- nothing here modifies a campaign automatically.",
        account_line="ConnectWave Communications",
    )

    search_terms = data["search_terms"]
    max_date = search_terms["date"].max()
    min_available_days = (max_date - search_terms["date"].min()).days + 1

    col1, col2 = st.columns(2)
    with col1:
        campaign_pick = st.selectbox("Campaign", ["All"] + sorted(search_terms["campaign"].unique().tolist()), key="st_campaign")
    with col2:
        lookback = st.slider("Lookback (days)", 7, min_available_days, min_available_days, key="st_lookback")

    window_start = max_date - timedelta(days=lookback - 1)
    subset = search_terms if campaign_pick == "All" else search_terms[search_terms["campaign"] == campaign_pick]
    st.caption(f"{format_date_range(window_start, max_date)} ({lookback} days)")

    classified = classify_search_terms(subset, start_date=window_start, end_date=max_date)
    if classified.empty:
        empty_state(f"No search-term data available for {campaign_pick} in this window.")
        return

    classified = classified.copy()
    classified["recommendation"] = classified["classification"].map(_SEARCH_TERM_RECOMMENDATION)
    counts = classified["classification"].value_counts()

    cols = st.columns(4)
    for col, status in zip(cols, ["Negative Candidate", "Expansion Candidate", "Needs Review", "Relevant"]):
        col.metric(status, int(counts.get(status, 0)))

    st.divider()

    for status in ["Negative Candidate", "Expansion Candidate", "Needs Review"]:
        section_heading(status, _SEARCH_TERM_RECOMMENDATION[status])
        rows = classified[classified["classification"] == status].sort_values("spend", ascending=False)
        if rows.empty:
            if status == "Negative Candidate":
                empty_state(
                    f"No high-spend / zero-conversion search terms were detected during "
                    f"{format_date_range(window_start, max_date)}. This is a positive signal; "
                    f"continue monitoring query quality."
                )
            else:
                empty_state(f'No search terms currently classified "{status}".')
        else:
            st.dataframe(
                _clean_performance_table(
                    rows, id_cols=["campaign", "search_term", "matched_keyword", "classification", "recommendation"],
                    extra_labels={"search_term": "Search Term", "matched_keyword": "Triggering Keyword"},
                ),
                use_container_width=True,
            )


# ---------------------------------------------------------------------------
# Budget Pacing
# ---------------------------------------------------------------------------
_PACING_CONTEXT_KIND = {
    "Opportunity": "positive", "On Track": "positive", "Review": "warning",
    "Caution": "warning", "Monitor": "warning", "At Risk": "negative",
}
_PACING_TABLE_COLUMNS = [
    "campaign", "monthly_budget", "spend_to_date", "expected_spend_to_date", "remaining_budget",
    "remaining_days", "projected_month_end_spend", "projected_pct_of_budget", "recommended_daily_spend", "status",
]
_PACING_TABLE_LABELS = {
    "campaign": "Campaign", "monthly_budget": "Monthly Budget", "spend_to_date": "Spend to Date",
    "expected_spend_to_date": "Expected Spend to Date", "remaining_budget": "Remaining Budget",
    "remaining_days": "Remaining Days", "projected_month_end_spend": "Projected Month-End Spend",
    "projected_pct_of_budget": "Projected % of Budget", "recommended_daily_spend": "Recommended Daily Spend",
    "status": "Status",
}


def render_budget_pacing(data):
    campaigns = data["campaigns"]
    as_of = campaigns["date"].max()

    page_header(
        "Budget Pacing",
        description="Are we likely to spend the budget appropriately -- and should we? Under-pacing never "
                     "automatically means \"spend more\"; over-pacing never automatically means \"cut spend\". "
                     "Performance decides.",
        account_line="ConnectWave Communications",
    )
    st.caption(f"As of {as_of} (most recent complete date in the dataset).")

    pacing_df, contexts = build_pacing_contexts(campaigns, as_of)
    total = pacing_df[pacing_df["campaign"] == "ACCOUNT TOTAL"].iloc[0]

    cols = st.columns(5)
    cols[0].metric("Monthly Budget", _money(total["monthly_budget"]))
    cols[1].metric("Spend to Date", _money(total["spend_to_date"]))
    cols[2].metric("Expected Spend to Date", _money(total["expected_spend_to_date"]))
    cols[3].metric("Projected Month-End Spend", _money(total["projected_month_end_spend"]))
    variance = total["projected_month_end_spend"] - total["monthly_budget"]
    cols[4].metric("Projected Variance", _money(variance), delta_color="off")

    days_elapsed_pct = 1 - (total["remaining_days"] / (total["remaining_days"] + as_of.day)) if (total["remaining_days"] + as_of.day) else 0
    spend_pct = min(1.0, total["spend_to_date"] / total["monthly_budget"]) if total["monthly_budget"] else 0.0
    st.progress(spend_pct, text=f"{spend_pct:.0%} of monthly budget spent · {days_elapsed_pct:.0%} of the month elapsed")

    st.divider()

    section_heading("Campaign Pacing")
    campaign_rows = pacing_df[pacing_df["campaign"] != "ACCOUNT TOTAL"][_PACING_TABLE_COLUMNS]
    display = campaign_rows.rename(columns=_PACING_TABLE_LABELS)
    styled = display.style.format({
        "Monthly Budget": _money, "Spend to Date": _money, "Expected Spend to Date": _money,
        "Remaining Budget": _money, "Projected Month-End Spend": _money, "Recommended Daily Spend": _money,
        "Projected % of Budget": lambda v: "n/a" if pd.isna(v) else f"{v:.0%}",
    }).hide(axis="index")
    st.dataframe(styled, use_container_width=True)

    st.divider()

    section_heading(
        "Pacing Context & Recommendations",
        "Combines pacing status with how each campaign's ROAS compares to the account average this month -- "
        "the basis for whether under-pacing is a real opportunity or a reason for caution.",
    )
    for campaign, ctx in contexts.items():
        campaign_row = pacing_df[pacing_df["campaign"] == campaign].iloc[0]
        campaign_spend_pct = min(1.0, campaign_row["spend_to_date"] / campaign_row["monthly_budget"]) if campaign_row["monthly_budget"] else 0.0
        insight_card(
            f'"{campaign}" — {ctx["context"]}', ctx["commentary"], kind=_PACING_CONTEXT_KIND.get(ctx["context"], "neutral"),
        )
        st.progress(campaign_spend_pct, text=f"{campaign_spend_pct:.0%} of monthly budget spent")


# ---------------------------------------------------------------------------
# Competitive Intelligence
# ---------------------------------------------------------------------------
def render_competitive_intelligence(data):
    page_header(
        "Competitive Intelligence",
        description="Are competitive conditions changing? Based on synthetic auction-insight data -- "
                     "directional, not a precise competitive measurement. We describe what the auction data "
                     "shows and never claim a specific competitor action caused a performance change without evidence.",
        account_line="ConnectWave Communications",
    )

    campaigns_df = data["campaigns"]
    auction = data["auction_insights"]
    campaign_pick = st.selectbox("Campaign", sorted(auction["campaign"].unique()))

    cur_start, cur_end, prev_start, prev_end = week_over_week_range(campaigns_df)
    trend = auction_trend(auction, campaign_pick, (cur_start, cur_end), (prev_start, prev_end))

    cols = st.columns(4)
    labels = [("impression_share", "Impression Share"), ("outranking_share", "Outranking Share"),
              ("lost_is_rank", "Lost IS (Rank)"), ("lost_is_budget", "Lost IS (Budget)")]
    for col, (key, label) in zip(cols, labels):
        current, previous = trend[key]["current"], trend[key]["previous"]
        delta = fmt_points(current - previous) if current is not None and previous is not None else None
        col.metric(label, fmt_percent(current) if current is not None else "n/a", delta, delta_color="off")

    st.markdown(f"**Most recently observed top competitor:** {trend['top_competitor']}")

    section_heading("Commentary")
    st.info(generate_competitive_commentary(campaign_pick, trend))
    with st.expander("Full evidence"):
        for line in summarize_competitive_pressure(trend):
            st.markdown(f"- {line}")

    section_heading("Weekly Trend", "Latest 5 weeks, actual date ranges.")
    campaign_auction = auction[auction["campaign"] == campaign_pick].sort_values("week_start_date").tail(5).copy()
    campaign_auction["week_label"] = campaign_auction["week_start_date"].apply(
        lambda d: format_date_range(d, d + timedelta(days=6))
    )
    trend_df = campaign_auction.set_index("week_label")[["impression_share", "lost_is_rank", "lost_is_budget"]]
    trend_df = trend_df.rename(columns={
        "impression_share": "Impression Share", "lost_is_rank": "Lost IS (Rank)", "lost_is_budget": "Lost IS (Budget)",
    })
    # week_label is already chronological (sorted above); an explicit
    # ordered category stops the chart from re-sorting it alphabetically.
    trend_df.index = chronological_categories(trend_df.index)
    st.line_chart(trend_df, height=280)


# ---------------------------------------------------------------------------
# Change Intelligence
# ---------------------------------------------------------------------------
def render_change_intelligence(data):
    page_header(
        "Change Intelligence",
        description="What changed in the account, and did performance move around the same time? "
                     "Timing correlation is evidence, never proof of causation.",
        account_line="ConnectWave Communications",
    )

    changes = data["changes"]
    campaigns_df = data["campaigns"]

    col1, col2 = st.columns(2)
    with col1:
        campaign_pick = st.selectbox("Campaign", ["All"] + sorted(changes["campaign"].unique().tolist()), key="chg_campaign")
    with col2:
        type_options = ["All"] + sorted(changes["change_type"].unique().tolist())
        type_pick = st.selectbox("Change Type", type_options, format_func=lambda t: t.replace("_", " ").title() if t != "All" else t, key="chg_type")

    subset = changes
    if campaign_pick != "All":
        subset = subset[subset["campaign"] == campaign_pick]
    if type_pick != "All":
        subset = subset[subset["change_type"] == type_pick]
    subset = subset.sort_values("date", ascending=False)

    if subset.empty:
        empty_state("No changes match the current filters.")
        return

    for _, row in subset.iterrows():
        with st.expander(f"{row['date']} — {row['campaign']}: {row['change_type'].replace('_', ' ').title()}"):
            # `or` alone doesn't catch this: a missing CSV field becomes a
            # NaN float on load, and NaN is truthy in Python, so `nan or
            # "—"` evaluates to `nan` -- fmt_or_dash checks for NaN explicitly.
            old_value = fmt_or_dash(row["old_value"], empty_meaning="no previous value -- newly added")
            new_value = fmt_or_dash(row["new_value"])
            st.markdown(f"**Old value:** {old_value}   |   **New value:** {new_value}")
            st.markdown(f"**Owner / Source:** {row['changed_by']}")
            st.markdown(f"**Note:** {row['notes']}")

            result = performance_around_change(campaigns_df, row["campaign"], row["date"], window_days=7)
            if result["has_data"]:
                before, after = result["before"], result["after"]
                st.markdown("**Performance in the 7 days before vs. after this change:**")
                cols = st.columns(3)
                cols[0].metric("Conversions", f"{after['conversions']:,.0f}", f"{after['conversions'] - before['conversions']:+,.0f} vs. before", delta_color="off")
                cols[1].metric("Conversion Rate", fmt_percent(after["conversion_rate"]), fmt_points(after["conversion_rate"] - before["conversion_rate"]), delta_color="off")
                cols[2].metric("CPA", fmt_money(after["cpa"]), fmt_money(after["cpa"] - before["cpa"]), delta_color="off")
                st.caption(
                    "Performance changed shortly after this account change. This is timing correlation, "
                    "not proof that the change caused it -- see Campaign Intelligence's investigation tool "
                    "for corroborating evidence (traffic, competitive, search-term signals)."
                )
            else:
                st.caption("Not enough surrounding data to compare before/after performance for this change.")


# ---------------------------------------------------------------------------
# Optimization Center
# ---------------------------------------------------------------------------
_RECOMMENDATION_CATEGORY_BADGE = {
    "High Priority": "negative", "Opportunity": "positive", "Investigate": "warning",
    "Monitor": "neutral", "Implemented": "info",
}
_CONFIDENCE_BADGE_KIND = {"High": "positive", "Medium": "warning", "Low": "neutral"}


def _recommendation_source_page(rec):
    """Best-effort mapping from a recommendation's content back to the
    intelligence page with the supporting detail, for a contextual
    "View evidence" link. Heuristic and presentation-only -- it doesn't
    change what the recommendation means, only where it points."""
    text = f"{rec.title} {rec.entity}".lower()
    if "negative keyword" in text or "search term" in text or "search-term" in text:
        return "Search Term Intelligence"
    if 'keyword: "' in text or "review keyword" in text:
        return "Keyword Intelligence"
    if "budget" in text or "pacing" in text:
        return "Budget Pacing"
    if "rank pressure" in text or "competitive" in text:
        return "Competitive Intelligence"
    if text.startswith("investigate "):
        return "Campaign Intelligence"
    return None


def _render_recommendation_card(rec):
    category_badge = badge_html(rec.category, kind=_RECOMMENDATION_CATEGORY_BADGE.get(rec.category, "neutral"))
    confidence_badge = badge_html(f"{rec.confidence} confidence", kind=_CONFIDENCE_BADGE_KIND.get(rec.confidence, "neutral"))

    with st.expander(f"{rec.title} — {rec.entity}"):
        st.markdown(f"{category_badge} {confidence_badge}", unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Why**")
            st.caption(rec.reason)
            st.markdown("**Evidence**")
            st.caption(rec.evidence)
        with col2:
            st.markdown("**Expected Impact**")
            st.caption(rec.expected_impact)
            st.markdown("**Status**")
            st.caption(rec.status)

        st.info(f"**Suggested action:** {rec.suggested_action}")

        if rec.status == "Implemented":
            st.markdown(
                f"**Implemented:** {rec.date_implemented}  |  **Observation window:** {rec.observation_window_days} days"
            )
            st.markdown(f"**Measured outcome:** {rec.measured_outcome}")

        source_page = _recommendation_source_page(rec)
        if source_page:
            if st.button(f"View evidence in {source_page} →", key=f"opt_nav_{rec.category}_{rec.title}_{rec.entity}"):
                st.session_state["pending_nav_section"] = source_page
                st.rerun()


def render_optimization_center(data):
    page_header(
        "Optimization Center",
        description="What should we do next? Rule-based recommendations combining evidence from pacing, "
                     "performance, search terms, keywords, and competitive signals. Nothing here is auto-applied.",
        account_line="ConnectWave Communications",
    )

    campaigns = data["campaigns"]
    as_of = campaigns["date"].max()
    recs = generate_recommendations(
        campaigns, data["keywords"], data["search_terms"], data["changes"], data["auction_insights"], as_of
    )
    tracked_example = seed_tracked_recommendation_example(campaigns, data["changes"])
    if tracked_example:
        recs = recs + [tracked_example]

    if not recs:
        empty_state(
            "No recommendations were generated for the current period. This means no rule found "
            "sufficient evidence to act on -- not that everything is necessarily optimal."
        )
        return

    categories = ["High Priority", "Opportunity", "Investigate", "Monitor", "Implemented"]
    counts = {cat: sum(1 for r in recs if r.category == cat) for cat in categories}
    cols = st.columns(len(categories))
    for col, cat in zip(cols, categories):
        col.metric(cat, counts[cat])

    st.divider()

    empty_state_copy = {
        "High Priority": "No high-priority issues right now -- a positive signal, not a gap in coverage.",
        "Opportunity": "No standout opportunities identified this period.",
        "Investigate": "Nothing currently warrants investigation.",
        "Monitor": "Nothing to keep an eye on beyond normal operation right now.",
        "Implemented": "No recommendations have been marked implemented yet.",
    }

    tabs = st.tabs([f"{cat} ({counts[cat]})" for cat in categories])
    for tab, cat in zip(tabs, categories):
        with tab:
            cat_recs = [r for r in recs if r.category == cat]
            if not cat_recs:
                empty_state(empty_state_copy.get(cat, f"No {cat.lower()} items right now."))
                continue
            for rec in cat_recs:
                _render_recommendation_card(rec)


# ---------------------------------------------------------------------------
# Ask My Account
# ---------------------------------------------------------------------------
_EXAMPLE_QUESTIONS = [
    "How did we perform during the last 8 days?", "How did we perform last week?",
    "Why did conversions decrease?", "Which campaign generated the most conversions?",
    "Which campaigns need attention?", "Are we pacing to budget?",
    "What changed recently?", "What search terms are wasting spend?",
    "Where are the best optimization opportunities?", "Is competitive pressure increasing?",
    "Why did CPA increase?",
]


def render_ask_my_account(data):
    _consume_pending_state("ask_question_input")

    page_header(
        "Ask My Account",
        description="Ask questions about your account and get answers grounded in performance, pacing, "
                     "search-term, keyword, change, and competitive evidence.",
        account_line="ConnectWave Communications",
    )

    st.markdown("**Try a question:**")
    cols = st.columns(3)
    for i, q in enumerate(_EXAMPLE_QUESTIONS):
        if cols[i % 3].button(q, key=f"ask_example_{i}"):
            st.session_state["pending_ask_question_input"] = q
            st.rerun()

    st.divider()
    question = st.text_input("Or ask your own question", key="ask_question_input")
    if question:
        result = answer_question(question, data)
        _render_ask_my_account_answer(result)


def _render_ask_my_account_answer(result):
    """`result` is a plain string (most question types), a "not_material"
    dict (a metric moved, but below the investigation threshold -- no
    investigation was performed, so none is shown), or a "structured"
    dict (the full "why did X change?" multi-step synthesis). Only
    sections that actually apply are shown, never a fixed template
    padded with "n/a"."""
    if not isinstance(result, dict):
        st.markdown("##### Answer")
        st.info(result)
        return

    if result.get("type") == "not_material":
        st.markdown("##### Answer")
        st.info(result["answer"])
        render_badge(result["assessment"], kind="neutral")
        st.caption(
            f"Change: {fmt_percent(result['pct_change'], signed=True)}  ·  "
            f"Materiality threshold: {fmt_percent(result['threshold'])}"
        )
        st.markdown("**Recommended Monitoring Action**")
        st.write(result["monitoring_action"])
        return

    st.markdown("##### Answer")
    st.info(result["answer"])

    if result.get("what_changed"):
        st.markdown("**What Changed**")
        st.write(result["what_changed"])

    if result.get("signals"):
        st.markdown("**Likely Contributing Signals**")
        for s in result["signals"]:
            st.markdown(f"- {s}")

    if result.get("alternatives"):
        with st.expander("Alternative Explanations"):
            for a in result["alternatives"]:
                st.markdown(f"- {a}")

    if result.get("next_step"):
        st.markdown("**Recommended Next Step**")
        st.success(result["next_step"])

    col1, col2 = st.columns([2, 1])
    with col1:
        if result.get("evidence_used"):
            st.caption("Evidence used: " + " · ".join(result["evidence_used"]))
    with col2:
        if result.get("confidence"):
            render_badge(f"{result['confidence']} confidence", kind=_CONFIDENCE_BADGE_KIND.get(result["confidence"], "neutral"))


# ---------------------------------------------------------------------------
# Shared: investigation report renderer
# ---------------------------------------------------------------------------
def _render_investigation_report(report):
    v = report["verify"]

    if not v["changed_materially"]:
        st.info(report["conclusion"])
        return

    st.markdown("#### Observed Change")
    label = metric_label(report["metric"])
    st.markdown(
        f"**{label}** {v['direction']} by **{abs(v['abs_change']):,.2f}** "
        f"({v['pct_change']:+.1%})." if v["pct_change"] is not None else
        f"**{label}** {v['direction']} by **{abs(v['abs_change']):,.2f}**."
    )

    top_campaigns = list(report["hypotheses"].keys())
    if top_campaigns:
        primary = top_campaigns[0]
        hyp = report["hypotheses"][primary]
        st.markdown("#### Likely Contributing Signal")
        render_badge(hyp["confidence"], kind={"High": "positive", "Medium": "warning", "Low": "neutral"}.get(hyp["confidence"]))
        st.markdown(hyp["text"])

        if report.get("suggested_next_test"):
            st.markdown(f"**Suggested next test:** {report['suggested_next_test']}")

        if len(top_campaigns) > 1:
            with st.expander("Alternative explanations considered"):
                for alt in report.get("alternative_explanations", [])[1:]:
                    st.markdown(f"- {alt}")
                if len(report.get("alternative_explanations", [])) <= 1:
                    empty_state("No other campaign showed a comparably material, distinct driver this period.")

    with st.expander("Show the full evidence trail (verify -> quantify -> localize -> investigate -> hypothesize -> test)"):
        st.markdown("**1. Verify & Quantify**")
        st.json({
            "current_value": v["current_value"], "previous_value": v["previous_value"],
            "absolute_change": v["abs_change"], "percent_change": v["pct_change"],
            "changed_materially": v["changed_materially"],
        })

        st.markdown("**2. Localize (ranked contributors)**")
        st.dataframe(report["localize"]["ranked_contributors"], use_container_width=True)

        st.markdown("**3. Investigate the chain + Hypothesize + Test**")
        for campaign, ev in report["investigate"].items():
            st.markdown(f"*{campaign}*")
            st.json(ev)
            hyp = report["hypotheses"].get(campaign, {})
            st.markdown(f"Hypothesis: **{hyp.get('text', 'n/a')}** (confidence: {hyp.get('confidence', 'n/a')})")
            if "search_term_quality" in hyp:
                st.caption(f"Search-term quality check: {hyp['search_term_quality']}")
            if "budget_context" in hyp:
                st.caption(f"Budget context: {hyp['budget_context']}")
