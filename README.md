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

**Temperature:** cold. They have never heard of you.

**Job:** stop settling for 40% email coverage. Coverage is the ceiling for every other Play.

**Steps**
1. Put `first_name,last_name,company_domain,linkedin_url` in `data/leads.csv` (see `data/leads.example.csv`).
2. Check `get_fair_use` on the GetLeads MCP, then dry-run: `uv run python -m outbound.waterfall data/leads.csv --out out/leads_enriched.csv --dry-run`.
3. Run it in batches of 150: GetLeads, then Deepline `prebuilt/person-to-email-batch`; add `--deep` for FullEnrich on the leftovers only.
4. Every email is verified (MillionVerifier, BounceBan once if catch-all). `verified` stops the waterfall, `catch_all` and `unknown` are stored with their status and stop, `discard` tries the next provider, nothing left is `not_found`.
5. Read `out/leads_enriched.csv.report.md`. Only `verified` goes to Smartlead; the rest go to a LinkedIn-only track.

**Prompt to paste**
```
Read data/leads.csv, dedupe, run uv run python -m outbound.waterfall data/leads.csv --out out/leads_enriched.csv --batch 150 --dry-run
and show me the plan. After I approve, run it for real: stop at the first verified email per row, never build an
email from a naming pattern, write out/leads_enriched.csv (email, email_status, email_provider, verifier, mx_class, miss_reason),
and report % verified / % catch-all / % unknown / % not found, hits per provider and spend.
Catch-all and unknown never go to Smartlead. Wait for my approval before pushing.
```

**Why it works:** no single vendor covers every region, so chaining them lifts coverage. GetLeads charges only on a hit, so the cheap first step costs nothing on misses, and the stop rule means you pay for the next provider only when needed.

**What you get:** `out/leads_enriched.csv` with every input row kept plus the six email columns, and a report with coverage percentages and spend. Aim for bounces under 2%.

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
