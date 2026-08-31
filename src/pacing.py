"""
Budget pacing.

Pure, deterministic math: given a campaign's (or the account's) monthly
budget and how much has been spent so far this month, figure out
whether spend is tracking ahead of, behind, or on top of a straight-line
expectation, and what daily spend for the rest of the month would land
exactly on budget.

Two related percentages are reported because they answer different
questions:
  - pacing_pct_to_date: "are we spending faster or slower than expected,
    based on how far through the month we are?" (compares spend-to-date
    against a straight-line share of the budget)
  - projected_pct_of_budget: "if the current daily rate continues, will
    we end the month over or under the full budget?"
"""

import calendar

import pandas as pd

from src.metrics import safe_div

STATUS_OVER = "Over pacing"
STATUS_UNDER = "Under pacing"
STATUS_ON_TRACK = "On pace"


def _status(pacing_pct_to_date):
    if pacing_pct_to_date is None:
        return "Unknown"
    if pacing_pct_to_date > 1.10:
        return STATUS_OVER
    if pacing_pct_to_date < 0.90:
        return STATUS_UNDER
    return STATUS_ON_TRACK


def compute_pacing(df, as_of_date, group_by="campaign"):
    """Return a DataFrame with one pacing row per group (plus an
    'ACCOUNT TOTAL' row), as of as_of_date."""
    days_in_month = calendar.monthrange(as_of_date.year, as_of_date.month)[1]
    month_start = as_of_date.replace(day=1)
    day_of_month = as_of_date.day
    remaining_days = days_in_month - day_of_month

    month_to_date = df[(df["date"] >= month_start) & (df["date"] <= as_of_date)]
    spend_to_date = month_to_date.groupby(group_by)["spend"].sum()

    # Use the budget value on each group's most recent row as of as_of_date,
    # since a budget can change mid-month (e.g. a mid-month cut).
    current_budgets = (
        df[df["date"] <= as_of_date]
        .sort_values("date")
        .groupby(group_by)
        .tail(1)
        .set_index(group_by)["monthly_budget"]
    )

    rows = []
    for group_value in current_budgets.index:
        budget = current_budgets[group_value]
        spent = spend_to_date.get(group_value, 0.0)
        rows.append(_pacing_row(group_by, group_value, budget, spent, day_of_month, days_in_month, remaining_days))

    total_budget = current_budgets.sum()
    total_spent = spend_to_date.sum()
    rows.append(_pacing_row(group_by, "ACCOUNT TOTAL", total_budget, total_spent, day_of_month, days_in_month, remaining_days))

    return pd.DataFrame(rows)


def _pacing_row(group_by, group_value, budget, spend_to_date, day_of_month, days_in_month, remaining_days):
    expected_spend_to_date = budget * day_of_month / days_in_month
    pacing_pct_to_date = safe_div(spend_to_date, expected_spend_to_date, default=None)
    projected_month_end_spend = safe_div(spend_to_date, day_of_month, default=0.0) * days_in_month
    projected_pct_of_budget = safe_div(projected_month_end_spend, budget, default=None)
    remaining_budget = budget - spend_to_date
    recommended_daily_spend = safe_div(remaining_budget, remaining_days, default=None) if remaining_days > 0 else None

    return {
        group_by: group_value,
        "monthly_budget": budget,
        "spend_to_date": round(spend_to_date, 2),
        "expected_spend_to_date": round(expected_spend_to_date, 2),
        "remaining_budget": round(remaining_budget, 2),
        "remaining_days": remaining_days,
        "projected_month_end_spend": round(projected_month_end_spend, 2),
        "pacing_pct_to_date": pacing_pct_to_date,
        "projected_pct_of_budget": projected_pct_of_budget,
        "recommended_daily_spend": round(recommended_daily_spend, 2) if recommended_daily_spend is not None else None,
        "status": _status(pacing_pct_to_date),
    }
