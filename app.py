import csv

print("Good morning! Welcome to Marketing AI Copilot.")

data_file = "data/campaigns.csv"

# -----------------------------------------------------------------------
# 1. Load the data
# -----------------------------------------------------------------------
# csv.DictReader turns each row into a dictionary keyed by the column
# headers (date, campaign_name, channel, impressions, clicks, spend,
# conversions, conversion_value). Every value comes back as a string,
# even the numbers, because a CSV file is just plain text.
with open(data_file, mode="r") as file:
    reader = csv.DictReader(file)
    campaigns = list(reader)

# The numeric fields need to be converted from strings to int/float
# before we can do any math with them (e.g. "18500" -> 18500).
NUMERIC_FIELDS = ["impressions", "clicks", "spend", "conversions", "conversion_value"]

for campaign in campaigns:
    for field in NUMERIC_FIELDS:
        if field in ("impressions", "clicks", "conversions"):
            campaign[field] = int(campaign[field])
        else:
            campaign[field] = float(campaign[field])


# -----------------------------------------------------------------------
# 2. Calculate metrics for one campaign
# -----------------------------------------------------------------------
def calculate_metrics(campaign):
    """Given one campaign's raw numbers, return a copy with 5 extra
    calculated metrics added to it."""

    # CTR (Click-Through Rate): what percent of people who saw the ad clicked it.
    ctr = campaign["clicks"] / campaign["impressions"]

    # CPC (Cost Per Click): how much, on average, each click cost.
    cpc = campaign["spend"] / campaign["clicks"]

    # Conversion Rate: what percent of clicks turned into a conversion.
    conversion_rate = campaign["conversions"] / campaign["clicks"]

    # CPA (Cost Per Acquisition): how much, on average, each conversion cost.
    cpa = campaign["spend"] / campaign["conversions"]

    # ROAS (Return On Ad Spend): how many dollars came back for every dollar spent.
    roas = campaign["conversion_value"] / campaign["spend"]

    # Start with everything the campaign already had, then add the new metrics.
    enriched_campaign = dict(campaign)
    enriched_campaign["ctr"] = ctr
    enriched_campaign["cpc"] = cpc
    enriched_campaign["conversion_rate"] = conversion_rate
    enriched_campaign["cpa"] = cpa
    enriched_campaign["roas"] = roas
    return enriched_campaign


# -----------------------------------------------------------------------
# 3. Build the enriched list (original data + calculated metrics)
# -----------------------------------------------------------------------
campaigns_with_metrics = [calculate_metrics(campaign) for campaign in campaigns]


# -----------------------------------------------------------------------
# 4. Find the standout campaigns
# -----------------------------------------------------------------------
# max() scans the whole list and returns the single item where the
# "key" function produces the largest value.
most_conversions = max(campaigns_with_metrics, key=lambda c: c["conversions"])
best_roas = max(campaigns_with_metrics, key=lambda c: c["roas"])
highest_ctr = max(campaigns_with_metrics, key=lambda c: c["ctr"])
highest_conversion_rate = max(campaigns_with_metrics, key=lambda c: c["conversion_rate"])

# Highest CPA isn't necessarily "best" — it means this campaign paid the
# most, on average, to win each conversion, which is worth a closer look.
highest_cpa = max(campaigns_with_metrics, key=lambda c: c["cpa"])

total_spend = sum(c["spend"] for c in campaigns_with_metrics)
total_conversions = sum(c["conversions"] for c in campaigns_with_metrics)


# -----------------------------------------------------------------------
# 5. Generate a plain-English, rule-based summary
# -----------------------------------------------------------------------
def generate_summary(most_conversions, highest_cpa, best_roas, highest_ctr,
                      highest_conversion_rate, total_spend, total_conversions):
    """Turn the standout campaigns we already found into a plain-English
    report. This function only formats text -- it does no new math and
    uses no external AI, just simple rules based on the numbers above."""

    lines = []
    lines.append("Campaign Performance Summary")
    lines.append("-----------------------------")
    lines.append(f"Total spend across all campaigns: ${total_spend:,.2f}")
    lines.append(f"Total conversions: {total_conversions}")
    lines.append("")
    lines.append(
        f'"{most_conversions["campaign_name"]}" drove the most conversions '
        f'({most_conversions["conversions"]}).'
    )
    lines.append(
        f'"{highest_cpa["campaign_name"]}" had the highest cost per acquisition '
        f'(${highest_cpa["cpa"]:.2f}) -- worth a closer look.'
    )
    lines.append(
        f'"{best_roas["campaign_name"]}" delivered the best return on ad spend '
        f'({best_roas["roas"]:.2f}x).'
    )
    lines.append(
        f'"{highest_ctr["campaign_name"]}" had the highest click-through rate '
        f'({highest_ctr["ctr"]:.2%}).'
    )
    lines.append(
        f'"{highest_conversion_rate["campaign_name"]}" had the highest conversion rate '
        f'({highest_conversion_rate["conversion_rate"]:.2%}).'
    )
    return "\n".join(lines)


# -----------------------------------------------------------------------
# 6. Print everything out
# -----------------------------------------------------------------------
print("\nPer-Campaign Metrics")
print("---------------------")
for c in campaigns_with_metrics:
    print(
        f'{c["campaign_name"]:20} '
        f'CTR: {c["ctr"]:.2%}  '
        f'CPC: ${c["cpc"]:.2f}  '
        f'Conv Rate: {c["conversion_rate"]:.2%}  '
        f'CPA: ${c["cpa"]:.2f}  '
        f'ROAS: {c["roas"]:.2f}x'
    )

summary = generate_summary(
    most_conversions,
    highest_cpa,
    best_roas,
    highest_ctr,
    highest_conversion_rate,
    total_spend,
    total_conversions,
)

print("\n" + summary)
