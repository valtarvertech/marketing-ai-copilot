# Architecture

```
DATA SOURCES
    |
CONNECTORS
    |
STANDARDIZATION / NORMALIZATION
    |
DETERMINISTIC ANALYTICS
    |
INVESTIGATION ENGINE
    |
RECOMMENDATION ENGINE
    |
AI EXPLANATION / REASONING LAYER (optional)
    |
USER INTERFACE
```

## Data Sources & Connectors

**Current state:** one connector-equivalent -- `scripts/generate_synthetic_data.py`
-- which produces normalized CSVs directly. There is no live API
integration yet, by design (see docs/ROADMAP.md).

**Why this matters for the future:** the analysis layer (`src/metrics.py`
onward) never touches a CSV or a platform-specific field name directly.
It only knows about `src/data_loader.py`'s output: pandas DataFrames
with a fixed, normalized schema (`date`, `platform`, `channel`,
`campaign`, `impressions`, `clicks`, `spend`, `conversions`,
`conversion_value`, ...). A future real connector (Google Ads API,
GA4, Meta, ...) just needs to produce a DataFrame with those same
columns -- nothing downstream has to change. This is the
"connector -> normalization" boundary in the diagram above, and it's
the reason the platform can eventually support multiple ad platforms
without rewriting the investigation or recommendation logic.

## Standardization / Normalization

`src/data_loader.py` is the only module that reads raw files. It:
- Validates required columns exist (fails fast with a clear message if not)
- Parses dates into real `date` objects
- Returns plain pandas DataFrames with the normalized schema described above

## Deterministic Analytics

`src/metrics.py` and `src/comparisons.py`. All CTR/CPC/conversion
rate/CPA/ROAS math lives in exactly one place (`metrics.py`), used by
every other module. Two rules are enforced throughout:

1. **Aggregate raw numbers first, then divide.** Averaging daily ratios
   directly is a common analytics mistake (it weights a low-volume day
   the same as a high-volume day). `metrics.aggregate()` always sums
   impressions/clicks/spend/conversions/conversion_value first and
   derives the ratios from those sums.
2. **Division is always safe.** `metrics.safe_div()` returns a default
   (usually 0 or NaN) instead of raising or producing `inf` on a
   zero denominator -- used everywhere a ratio is computed.

No AI model is ever asked to perform this arithmetic.

## Investigation Engine

`src/investigation.py`. Given a metric and a time period, it works
through an explicit, auditable sequence -- never jumping straight from
"a number changed" to a conclusion:

1. **VERIFY** -- did the metric actually change materially?
2. **QUANTIFY** -- absolute and percent change.
3. **LOCALIZE** -- `src/contribution.py` ranks which campaigns drove an
   additive metric's change (their per-campaign deltas sum to the
   account-level delta); rate metrics get each campaign's own
   before/after value instead, since rates aren't additive across
   campaigns.
4. **INVESTIGATE** -- for the top contributors, walk the performance
   chain (impressions -> clicks -> CTR -> CPC -> conversion rate),
   check the change log (`src/change_intelligence.py`) for changes in
   the days before the shift, and check auction data
   (`src/competitive.py`) for competitive/budget signals.
5. **HYPOTHESIZE** -- a small, transparent rule set
   (`_classify_driver` in `investigation.py`) proposes a likely driver
   family (conversion-rate decline, volume decline, CPC pressure,
   possible search-term waste, ...).
6. **TEST** -- the hypothesis is corroborated (or not) against the
   auction and change-log evidence; confidence is upgraded only when
   there's real corroborating evidence, and a nearby change log entry
   is always described as "occurred before", never "caused", unless
   the surrounding evidence supports a stronger claim.
7. **CONCLUDE** -- a plain-English, hedged summary combining the
   verified fact with the best-supported hypothesis per contributor.
8. **RECOMMEND** -- handed to `src/recommendations.py`.

Confidence is always one of **High / Medium / Low**, assigned by
transparent rules -- never a fabricated statistic like "93.7%
confidence".

## Cross-Module Evidence Service

`src/evidence.py`. Individual modules each answer one narrow question
well; this module composes their outputs so no page has to treat
another module as a black box:

- **`investigate_with_evidence(...)`** wraps `investigation.investigate_range()`
  and adds two checks the base engine doesn't do on its own: whether
  search-term quality changed for the affected campaign
  (`search_term_intelligence.waste_share()`) and whether it was
  budget-constrained (`pacing.compute_pacing()`). It also surfaces
  **alternative explanations** (other campaigns' hypotheses, not just
  the primary one) and a **suggested next test**, keyed off the
  hypothesis driver (`NEXT_TEST_BY_DRIVER`).
- **`campaign_pacing_context(...)` / `build_pacing_contexts(...)`**
  combine a campaign's pacing status with its ROAS *relative to the
  account's own blended average that month* -- not a fixed floor -- to
  decide whether under-pacing is a real opportunity (`Opportunity`) or
  a reason for caution (`Caution`), and whether over-pacing is fine
  (`Review`) or a real problem (`At Risk`). This is the "under-pacing
  does not automatically mean spend more" logic in one place, used by
  both Budget Pacing and Optimization Center so they can never disagree.

This is also the intended seam for the future AI layer: an LLM would
receive this module's output (already-composed, structured evidence)
and write prose about it, rather than recomputing anything itself.

## Recommendation Engine

`src/recommendations.py`. Rule-based only, and every rule pulls from
`src/evidence.py` rather than a single isolated threshold. Each
`Recommendation` carries `title`, `entity`, `category`, `reason`,
`evidence`, `expected_impact`, `confidence`, `suggested_action`, and a
`status` (Suggested / Approved / Implemented / Dismissed). Categories
are **High Priority / Opportunity / Investigate / Monitor / Implemented**,
in that display order. Recommendations never modify a campaign
automatically.

Rules include: pacing-context recommendations (see above), search-term
negative/expansion candidates, keyword waste candidates (high relative
spend *and* sub-1.0x ROAS -- never CPA alone), rising competitive rank
pressure, and one recommendation tied to the single most material
account-level issue that week (reusing `executive_brief.generate_brief()`'s
own worst-metric logic, so Optimization Center never disagrees with the
Executive Overview brief).

A small **impact-tracking scaffold** is included:
recommendation -> implementation date -> observation window -> measured
outcome. `seed_tracked_recommendation_example()` demonstrates this end
to end using real synthetic data (the Scenario E negative-keyword
addition and its measured CPA change), rather than a placeholder.

## AI Explanation Layer (optional)

`src/ai_layer.py` defines an `Explainer` interface. The default,
always-active implementation (`RuleBasedExplainer`) does no network
calls and requires no API key -- it returns the deterministic text
already produced by the investigation/recommendation layers. A future
`AnthropicExplainer` (sketched in a comment, not implemented) would
receive the same structured facts and turn them into richer prose,
without ever receiving secrets/credentials as part of that payload.
**The application fully functions with zero external AI dependency.**

## User Interface

Streamlit (`app.py` + `src/ui_sections.py`). `app.py` is a thin router:
load data once (cached), read the sidebar selection, call the matching
`render_*` function. Each `render_*` function only formats results from
`src/` -- it contains no analysis logic of its own, which keeps the UI
layer swappable (e.g. a future non-Streamlit frontend) without
touching the analytics.

Cross-page navigation (e.g. an "Investigate ->" button in Performance
Intelligence jumping to Campaign Intelligence with the campaign/metric
pre-filled) uses a `pending_<key>` session-state pattern: Streamlit
forbids writing directly to a widget's own session-state key once that
widget has been drawn in the current run, so a button sets a
`pending_*` value and calls `st.rerun()`; the target page's render
function consumes it (`_consume_pending_state()`) before its own
widgets are created on the next run.

### Design System

- **`.streamlit/config.toml`** sets the dark base theme (colors, font)
  through Streamlit's native theming -- reliable across versions,
  no brittle CSS needed for the bulk of the app.
- **`src/formatting.py`** is the single source of truth for how every
  metric is displayed (currency, percent, ratio-`x`, percentage
  points). Every page formats through this module, so a percentage can
  never render as a raw decimal and a currency value never gets
  truncated.
- **`src/ui_components.py`** adds a small, narrowly-scoped CSS layer
  (status badges, insight cards, section rhythm) plus the shared
  Python helpers every page uses: `page_header()`, `section_heading()`,
  `insight_card()`, `render_badge()`, `empty_state()`, `demo_data_tag()`.
  A CPA increase reads as a red "Unfavorable" badge and an under-pacing
  campaign with strong ROAS reads as a green "Opportunity" card --
  color and label always come from `src/metrics.favorability()` /
  `src/evidence.campaign_pacing_context()`, never from raw sign alone.

## Multi-Platform Design (not yet populated with real data)

The normalized schema already includes a `platform` column
(`"Google Ads"` for all current synthetic data). Adding a second
platform means writing a new connector that outputs the same normalized
schema -- no changes to `metrics.py`, `comparisons.py`,
`investigation.py`, etc. See docs/ROADMAP.md for the target platform
list (Microsoft Advertising, SA360, Meta, LinkedIn, TikTok, GA4, Adobe
Analytics, and others).

## Multi-User / SaaS Future (documented only, not built)

Not implemented in the current MVP. Planned model:
- **Workspaces**, each with an **owner**
- Roles: **admin**, **analyst**, **executive/read-only**, **invited user**
- Workspace owners/admins can invite users and assign roles
- Role-based permissions gate write actions (approving recommendations,
  editing budgets) vs. read-only access (executives)

This is deliberately out of scope for the current MVP so it doesn't
complicate the synthetic-data, single-user local app.
