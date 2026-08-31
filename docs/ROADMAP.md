# Roadmap

Marketing AI Copilot's product vision is a **multi-channel paid-media
intelligence copilot** — not a paid-search-only tool. The phases below
describe how the current implementation evolves toward that vision, in
roughly the order they'd unlock the most value. Everything past
"Current Foundation" is planned/future work: no live platform
integration, cross-channel data, or external AI currently exists in
this repository.

## Current Foundation (Proven)

This is what v1.0.0 actually implements today, using a synthetic
paid-search dataset:

- A normalized data schema (`src/data_loader.py`) that isn't tied to any
  one platform's field names — the analytics layer only ever sees
  `date`, `platform`, `channel`, `campaign`, `impressions`, `clicks`,
  `spend`, `conversions`, `conversion_value`, and similar generic columns
- Deterministic analytics (metrics, comparisons, rolling periods,
  contribution analysis) that never depend on the data having come from
  a paid-search platform specifically
- A cross-module evidence layer and investigation engine that reasons
  over that normalized data
- A rule-based recommendation engine and a deterministic "Ask My
  Account" question router

The paid-search implementation exists to prove this architecture end to
end against a demanding, realistic use case — not to define the
product's ceiling.

## Phase 1 -- Live Measurement & Search Integrations
- Google Ads API connector (OAuth, developer token -- placeholders
  already reserved in `.env.example`)
- Microsoft Advertising connector
- SA360 connector
- GA4 connector (sessions, on-site conversions, attribution)
- Adobe Analytics connector
- CRM / offline conversion sources (lead -> opportunity -> closed-won
  tracking, call tracking, offline conversion import)
- Each connector's only job: produce a DataFrame matching the existing
  normalized schema in `src/data_loader.py`. No changes to `src/metrics.py`
  or downstream modules should be required.

## Phase 2 -- Multi-Channel Paid-Media Expansion
- Meta Ads
- LinkedIn Ads
- TikTok Ads
- Other paid-media platforms where appropriate (display/programmatic,
  DSPs, Google Search Console for organic/paid query overlap)
- Same connector contract as Phase 1: normalize to the existing schema,
  don't fork the analytics layer per platform

## Phase 3 -- Cross-Channel Intelligence
Once more than one platform is normalized into the same schema, extend
the existing single-platform logic across channels rather than building
parallel per-channel versions of it:
- Channel/campaign contribution analysis (`src/contribution.py` already
  ranks which campaigns drove an account-level change within one
  platform; extend the same math to rank channels)
- Cross-channel performance diagnostics using the existing investigation
  engine's evidence chain (traffic, budget, competitive, change-log) --
  applied across platforms, not just within one
- Ask My Account able to answer questions like "why did paid-media
  conversions decline last week, and which channel contributed most?"

## Phase 4 -- AI Explanation Layer
- Implement `AnthropicExplainer` (or equivalent) behind the existing
  `Explainer` interface in `src/ai_layer.py`
- Executive summary generation from investigation reports
- Follow-up investigation suggestions ("you might also want to check...")
- Richer, more conversational "Ask My Account" responses, built by
  having the LLM narrate the same structured evidence the deterministic
  engine already produces -- the AI layer extends this architecture, it
  does not replace the underlying calculations

## Phase 5 -- MCP Integrations
- Expose Marketing AI Copilot's analysis functions as MCP tools so
  other AI systems (Claude Desktop, other agents) can query campaign
  performance, run investigations, and fetch recommendations directly
- Potential MCP servers for connectors themselves (e.g. a Google Ads
  MCP server) once real API access exists

## Phase 6 -- Data Backend
- Move off flat CSVs to a real database (likely Postgres) once data
  volume/history grows beyond what's comfortable in-memory
- Historical change-history storage separate from raw performance data
- Proper migrations, indexing for fast period-over-period queries

## Phase 7 -- Authentication & Multi-User Workspaces
- Workspaces with an owner
- Roles: admin, analyst, executive/read-only, invited user
- Role-based permissions (see docs/ARCHITECTURE.md)
- Invitation flow for adding users to a workspace

## Phase 8 -- Deployment
- Containerize the app
- Hosted deployment (e.g. Streamlit Community Cloud for a demo, or a
  proper cloud deployment once multi-user support exists)
- Secrets management for real API credentials (never committed to the repo)

## Explicitly Out of Scope For Now
- Billing/subscription management
- Automatic campaign modification (recommendations remain
  human-reviewed suggestions indefinitely, by design)
- Claims of statistical/causal certainty beyond what rule-based
  evidence supports
