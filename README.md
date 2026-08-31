# Marketing AI Copilot

A marketing intelligence and decision-support platform for performance
marketers -- not another reporting dashboard. Marketing AI Copilot sits
above advertising and analytics platforms, standardizes their data,
**investigates** performance changes, identifies likely causes with
evidence, and recommends optimizations, so a marketer can ask "why did
conversions drop?" and get a real, evidence-based answer instead of a
chart.

This is also a portfolio project demonstrating AI-assisted software
engineering, marketing analytics, product thinking, and automation --
built with Claude Code.

## The Business Problem

Marketing dashboards are good at telling you *what* happened (clicks
went down, CPA went up). They're bad at telling you *why*, and even
worse at telling you *what to do about it*. A marketer is left manually
cross-referencing campaign reports, keyword data, search-term reports,
auction insights, and a change log in their head. Marketing AI Copilot
automates that cross-referencing with a deterministic investigation
engine, and lays the architecture for an AI layer to eventually turn
those findings into natural-language answers.

## Architecture

```
DATA SOURCES -> CONNECTORS -> NORMALIZATION -> DETERMINISTIC ANALYTICS
   -> INVESTIGATION ENGINE -> RECOMMENDATION ENGINE
   -> AI EXPLANATION LAYER (optional) -> USER INTERFACE
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full breakdown
of each layer. The short version: **all math is deterministic Python**
(CTR, CPC, conversion rate, CPA, ROAS, pacing, percent change,
contribution analysis) -- an AI model is never asked to do arithmetic.
An AI layer is a defined extension point for turning already-computed
facts into nicer prose later; the app fully works without one today.

## Current Capabilities

The product is organized around four questions, and every module maps to one:

| Question | Modules |
|---|---|
| **What happened?** | Executive Overview, Performance Intelligence |
| **Where did it happen?** | Campaign / Keyword / Search Term Intelligence |
| **Why might it have happened?** | Budget Pacing, Competitive Intelligence, Change Intelligence, the Investigation Engine |
| **What should we do next?** | Optimization Center, Ask My Account |

- **Executive Overview** -- the account landing page: rolling 8-day KPI
  cards with metric-aware favorable/unfavorable treatment, a deterministic
  Performance Brief, a rolling trend chart, latest-5-weeks performance,
  a decision-focused campaign snapshot, and a compact Attention/Opportunity
  panel pulled from the Optimization Center's own findings.
- **Performance Intelligence** -- three period views (Rolling 8 Days,
  Rolling 5 Weeks, Day over Day), each following the same hierarchy: what
  period, what changed, is it meaningful, is it favorable, which
  campaigns drove it, what to investigate next. Includes day-of-week-aware
  commentary (a quiet Saturday isn't mistaken for a new problem) and a
  week-over-week driver breakdown with mathematically valid contribution
  splitting for additive metrics and deterioration/improvement ranking
  for ratio metrics.
- **Campaign Intelligence** -- the full per-campaign metric table,
  standout-performer cards (explicitly warning that "highest" isn't
  always "best"), and a point-and-click investigation tool showing
  observed change, likely contributing signal, alternative explanations,
  confidence, and a suggested next test.
- **Keyword Intelligence** -- campaign filter, lookback control, and a
  multi-signal status label (Strong / Efficient / Monitor / Review /
  Waste Candidate) that never calls a keyword "waste" on CPA alone --
  only high relative spend *and* sub-1.0x ROAS earns that label.
- **Search Term Intelligence** -- campaign filter, lookback control, and
  a deterministic classification (Negative Candidate / Expansion
  Candidate / Needs Review / Relevant) with a recommendation per term.
  Recommendations only -- nothing is auto-applied.
- **Budget Pacing** -- account-level cards (budget, spend to date,
  expected spend, projected month-end spend and variance) plus a
  campaign pacing table and a **context-aware** recommendation per
  campaign: under-pacing only reads as an "Opportunity" when efficiency
  also supports it; otherwise it's flagged for investigation, never a
  blanket "spend more."
- **Competitive Intelligence** -- auction-insight trends (impression
  share, outranking share, lost IS due to rank vs. budget) with
  percentage-point-based deterministic commentary distinguishing
  rank-driven pressure from budget-driven visibility loss.
- **Change Intelligence** -- a filterable change-event timeline (by
  campaign and change type) with before/after performance shown for
  each event -- always framed as timing correlation, never proof of
  causation.
- **Optimization Center** -- recommendations organized into High
  Priority / Opportunity / Investigate / Monitor / Implemented, each
  with reason, evidence, expected impact, confidence, and a suggested
  action, generated from rules that combine signals across pacing,
  performance, search terms, keywords, and competitive data (see
  `src/evidence.py`) rather than firing off a single threshold in
  isolation.
- **Ask My Account** -- deterministic question routing over ~11 question
  types, including multi-step synthesis for "why did X change?" that
  checks traffic, conversion rate, search-term quality, budget context,
  competitive pressure, and recent changes before concluding (no
  external LLM required).
- **Investigation Engine** -- given a metric change, works through
  VERIFY -> QUANTIFY -> LOCALIZE -> INVESTIGATE -> HYPOTHESIZE -> TEST
  -> CONCLUDE -> RECOMMEND before saying anything. Tested against 5
  controlled synthetic scenarios (see "Synthetic Data" below).
- **Cross-module evidence service** (`src/evidence.py`) -- composes
  pacing, investigation, search-term, and competitive findings into one
  structure so Optimization Center and Ask My Account can reason across
  modules instead of treating each as an isolated dashboard.

### Design

A dark, restrained B2B SaaS visual system (`.streamlit/config.toml` for
the base theme, `src/ui_components.py` for badges/cards/section
headers), metric-aware color semantics throughout (a CPA increase is
red, not green, because higher CPA is unfavorable), and a persistent
`DEMO · SYNTHETIC DATA` indicator in the sidebar.

### Screenshots

_(Run the app locally to see it live -- screenshots to be added here.)_

## Installation

Requires Python 3.9+.

```bash
git clone <this-repo>
cd marketing-ai-copilot
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Running the App

```bash
python3 scripts/generate_synthetic_data.py   # only needed once, or to regenerate
streamlit run app.py
```

Then open the local URL Streamlit prints (usually http://localhost:8501).

## Project Structure

```
app.py                          Streamlit entry point (thin router)
.streamlit/config.toml          Dark theme (native Streamlit theming, not custom CSS overrides)
src/
  data_loader.py                CSV loading + normalization (the only place that reads raw files)
  formatting.py                 Single source of truth for how every metric is displayed
  metrics.py                    CTR/CPC/conversion rate/CPA/ROAS + metric-direction semantics (favorability())
  comparisons.py                Day-over-day / week-over-week / period-over-period comparisons
  rolling.py                    Rolling 8-day and rolling 5-week window construction + briefs
  contribution.py               Which campaigns drove an account-level change (additive vs. ratio metrics)
  investigation.py              The investigation engine (VERIFY -> ... -> CONCLUDE)
  evidence.py                   Cross-module evidence composition (pacing context, multi-signal investigation)
  pacing.py                     Budget pacing math
  keyword_intelligence.py       Keyword-level analysis + multi-signal status classification
  search_term_intelligence.py   Search-term analysis + deterministic classification
  change_intelligence.py        Correlates the change log with performance shifts
  competitive.py                Auction/competitive insight analysis + deterministic commentary
  recommendations.py            The Optimization Center's categorized recommendation engine
  question_router.py            "Ask My Account" deterministic question routing
  ai_layer.py                   AI explanation interface (no API key required to run the app)
  ui_components.py              Shared, presentation-only UI building blocks (badges, cards, headers)
  ui_sections.py                One render function per Streamlit nav section
data/                           Synthetic CSVs (see below)
scripts/generate_synthetic_data.py  Regenerates all synthetic data from a fixed random seed
tests/                          pytest suite (see Testing)
docs/ARCHITECTURE.md            Full architecture writeup
docs/ROADMAP.md                 Future phases
```

## Synthetic Data Disclaimer

**All data in this repository is synthetic.** "ConnectWave
Communications" is a fictional telecom company; there is no real
advertiser, customer, or account behind this data. Numbers are
generated by `scripts/generate_synthetic_data.py` with a fixed random
seed (reproducible) and cover ~90 days across 7 campaigns, plus
keywords, search terms, an account change log, and weekly
auction-insight data.

On top of realistic day-of-week seasonality and random noise, specific
performance "stories" are deliberately injected -- via multiplicative
overlays that never change how many random numbers are drawn, so adding
a new scenario never perturbs any other campaign's already-tested
values -- so the investigation engine has known ground truth to test
against (see `data/scenario_ground_truth.csv` and `tests/test_investigation.py`,
`tests/test_rolling.py`):

| Scenario | Campaign | Story |
|---|---|---|
| A | Enterprise Voice | CPC rises ~45% from competitive pressure; traffic holds steady |
| B | Business Fiber | Conversion rate drops ~35% after a landing page change; traffic unaffected |
| C | SD-WAN | A mid-month budget cut causes a volume decline (impressions/clicks down, CTR/CPC stable) |
| D | Managed Security | A batch of irrelevant search terms consumes extra spend/clicks with ~zero conversions |
| E | Remarketing | Adding negative keywords measurably improves conversion rate over the following 10 days |
| F | UCaaS | CPC creeps up while clicks/CVR hold flat: spend and CPA rise with conversions roughly unchanged -- also makes this an "under-pacing but recently weaker efficiency" pacing story |
| G | Brand Search | No overlay -- the account's stable, consistently strongest campaign, and a genuine "under-pacing + strong efficiency = opportunity" pacing story with zero data manipulation |
| H | (several campaigns) | Keyword-expansion candidates emerge naturally from baseline search-term performance -- not an injected anomaly |

Two pacing/efficiency stories (scenario F vs. G) are deliberately
engineered from *relative* benchmarking (each campaign's ROAS vs. the
account's own blended average that month) rather than a fixed
threshold -- this is also how `src/evidence.py`'s pacing-context logic
works in general, so it will keep producing sensible "opportunity" vs.
"caution" verdicts on data it has never seen.

## Technology Stack

- **Python 3.9+**, **pandas** for data manipulation
- **Streamlit** for the local web UI
- **pytest** for automated testing
- No database (CSV files), no external APIs, no paid services required

## Testing

```bash
pytest
```

Covers: CTR/CPC/conversion rate/CPA/ROAS correctness (including
divide-by-zero, zero-impressions/clicks/conversions/spend, and empty-data
edge cases), metric directionality/favorability, percent-change math,
rolling 8-day and rolling 5-week window construction (including
non-hardcoded date shifting), weekly trend classification, contribution
analysis for both additive and ratio metrics, budget pacing, the
context-aware pacing/recommendation logic, keyword and search-term
classification, change-event before/after correlation, the investigation
engine against all 6 injected scenarios, cross-module evidence synthesis,
question-routing (every documented example question), and a UI smoke
test that renders every navigation section and interactive path
(tabs, filters, cross-page navigation buttons) and asserts no exceptions.

## Roadmap

See [docs/ROADMAP.md](docs/ROADMAP.md) for planned future phases: real
Google Ads / Microsoft Ads / SA360 / GA4 / Adobe connectors, paid
social and programmatic platforms, MCP integrations, a real AI
provider, a database backend, authentication, multi-user workspaces,
and deployment.

## Portfolio Purpose

This project is built to demonstrate: AI-assisted software engineering
practices, marketing analytics domain knowledge, deterministic
data-pipeline design, evidence-based reasoning systems, and product
thinking about a real (if currently synthetic-data-only) marketing
intelligence platform.
