# Roadmap

This MVP intentionally uses synthetic data, deterministic logic, and no
external services. The phases below are future work, in roughly the
order they'd unlock the most value.

## Phase 1 -- Real Connectors (Paid Search)
- Google Ads API connector (OAuth, developer token -- placeholders
  already reserved in `.env.example`)
- Microsoft Advertising connector
- SA360 connector
- Each connector's only job: produce a DataFrame matching the existing
  normalized schema in `src/data_loader.py`. No changes to `src/metrics.py`
  or downstream modules should be required.

## Phase 2 -- Analytics & Other Paid Channels
- GA4 connector (sessions, on-site conversions, attribution)
- Adobe Analytics connector
- Paid social: Meta, LinkedIn, TikTok
- Display/programmatic and DSP connectors
- Google Search Console (organic query overlap with paid search terms)

## Phase 3 -- CRM & Offline Conversion Sources
- CRM system integration (lead -> opportunity -> closed-won tracking)
- Call tracking integration
- Website analytics / on-site event tracking beyond GA4
- Offline conversion import (matching ad clicks to CRM outcomes)

## Phase 4 -- Real AI Layer
- Implement `AnthropicExplainer` (or equivalent) behind the existing
  `Explainer` interface in `src/ai_layer.py`
- Executive summary generation from investigation reports
- Follow-up investigation suggestions ("you might also want to check...")
- Natural-language expansion of "Ask My Account" beyond the current
  deterministic question router

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
