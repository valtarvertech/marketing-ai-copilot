from datetime import date

import pandas as pd

from src.pacing import compute_pacing, STATUS_OVER, STATUS_UNDER, STATUS_ON_TRACK


def _daily_rows(campaign, daily_spend, num_days, monthly_budget, start=date(2026, 1, 1)):
    rows = []
    for i in range(num_days):
        d = date(start.year, start.month, start.day + i)
        rows.append({
            "date": d, "campaign": campaign, "impressions": 1000, "clicks": 100,
            "spend": daily_spend, "conversions": 5, "conversion_value": 100.0,
            "monthly_budget": monthly_budget,
        })
    return rows


def test_pacing_on_track_with_clean_numbers():
    # January has 31 days. $100/day for 10 days = $1000 spent.
    # A $3100 monthly budget evenly spread is exactly $100/day, so
    # spend-to-date should exactly match the expected spend-to-date.
    df = pd.DataFrame(_daily_rows("A", 100.0, 10, 3100.0))
    result = compute_pacing(df, as_of_date=date(2026, 1, 10), group_by="campaign")
    row = result[result["campaign"] == "A"].iloc[0]

    assert row["spend_to_date"] == 1000.0
    assert row["expected_spend_to_date"] == 1000.0
    assert row["pacing_pct_to_date"] == 1.0
    assert row["status"] == STATUS_ON_TRACK
    assert row["remaining_budget"] == 2100.0
    assert row["remaining_days"] == 21
    assert row["recommended_daily_spend"] == 100.0
    assert row["projected_month_end_spend"] == 3100.0


def test_pacing_flags_over_pacing():
    df = pd.DataFrame(_daily_rows("A", 150.0, 10, 3100.0))
    result = compute_pacing(df, as_of_date=date(2026, 1, 10), group_by="campaign")
    row = result[result["campaign"] == "A"].iloc[0]

    assert row["status"] == STATUS_OVER
    assert row["pacing_pct_to_date"] > 1.10


def test_pacing_flags_under_pacing():
    df = pd.DataFrame(_daily_rows("A", 50.0, 10, 3100.0))
    result = compute_pacing(df, as_of_date=date(2026, 1, 10), group_by="campaign")
    row = result[result["campaign"] == "A"].iloc[0]

    assert row["status"] == STATUS_UNDER
    assert row["pacing_pct_to_date"] < 0.90


def test_pacing_uses_most_recent_budget_when_it_changes_mid_month():
    rows = _daily_rows("A", 100.0, 5, 3100.0)
    rows += _daily_rows("A", 100.0, 5, 1550.0, start=date(2026, 1, 6))
    df = pd.DataFrame(rows)
    result = compute_pacing(df, as_of_date=date(2026, 1, 10), group_by="campaign")
    row = result[result["campaign"] == "A"].iloc[0]

    assert row["monthly_budget"] == 1550.0


def test_account_total_row_sums_all_campaigns():
    rows = _daily_rows("A", 100.0, 10, 3100.0) + _daily_rows("B", 50.0, 10, 1550.0)
    df = pd.DataFrame(rows)
    result = compute_pacing(df, as_of_date=date(2026, 1, 10), group_by="campaign")
    total_row = result[result["campaign"] == "ACCOUNT TOTAL"].iloc[0]

    assert total_row["spend_to_date"] == 1000.0 + 500.0
    assert total_row["monthly_budget"] == 3100.0 + 1550.0


def test_pacing_runs_on_real_data_without_error(campaigns_df):
    as_of = campaigns_df["date"].max()
    result = compute_pacing(campaigns_df, as_of_date=as_of, group_by="campaign")
    assert "ACCOUNT TOTAL" in result["campaign"].values
    assert result["status"].isin([STATUS_OVER, STATUS_UNDER, STATUS_ON_TRACK, "Unknown"]).all()
