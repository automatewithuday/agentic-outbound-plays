# Martechs Outbound System — 5 agentic outbound Plays in Claude Code (GetLeads + Deepline + Apify, no ColdIQ needed)

Based on Michel Lieben's article "Here's how to Generate Leads With 5 Agentic Outbound Workflows in Claude Code" (https://x.com/MichLieben/status/2100264228947107996). The article uses ColdIQ; this repo reproduces the same five workflows (called Plays here) with substitutions: ColdIQ → GetLeads / Deepline / Apify, Instantly → Smartlead, lemlist → HeyReach, Trigify → GetLeads profile monitoring. Bring your own keys.

## Before you build: connect once

1. Clone this repo.
2. `cp .env.example .env` and fill in your keys.
3. `uv sync`
4. Connect the GetLeads MCP: `claude mcp add getleads ...` (exact command: see the docs at https://app.getleads.io).
5. Install Deepline: follow https://code.deepline.com/INSTALL.md.
6. Write your rules into `CLAUDE.md`. The ICP section is the only edit you need.
7. Test with ONE company before running a list.

## Play 1 · Waterfall email finder (cold)

_coming in Task 2_

## Play 2 · Signal scoring (warm)

_coming in Task 5_

## Play 3 · LinkedIn post engagers (warm)

_coming in Task 6_

## Play 4 · Champion reactivation (warm)

_coming in Task 3_

## Play 5 · Website visitor → email sequence (hot)

_coming in Task 4_

## Build order

1. Setup — keys, MCP and CLAUDE.md first; every Play depends on them.
2. Play 1 — cheapest, proves the cost and suppression plumbing on a plain list.
3. Play 4 — your own past champions; the warmest list with the least data work.
4. Play 5 — hot intent; small volume, highest reply rate.
5. Play 2 — needs scoring rules tuned against your results from Plays 1, 4 and 5.
6. Play 3 — post scraping is the most variable cost; do it last with a tight cap.

## Rhythm

_to be filled in a later task_

## Guardrails

- First 100 contacts, then inspect before scaling.
- Batches of 100-200 rows; `/compact` between batches.
- Approvals stay on for anything that sends.

## Prefer ColdIQ?

`claude mcp add coldiq --scope user -e COLDIQ_API_KEY=<key> -- npx -y @coldiq/mcp@latest`
Map: find_email → Play 1, find_signals → Play 2, extract_post_engagement → Play 3, job-change signals → Play 4, setup_website_visitors → Play 5.
Disclosure: ColdIQ is the article author's company.
