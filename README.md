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

**Temperature:** warm. They already know and like you.

**Job:** reach past champions who just started a new job, while the move is fresh (14 to 45 days).

**Steps**
1. Put `name,email,linkedin_url,old_company,old_company_domain,role` in `data/champions.csv` (see `data/champions.example.csv`). Only people you actually helped.
2. Check for moves with Deepline: `deepline plays run prebuilt/job-change-check --csv data/champions.csv --columns.company_domain old_company_domain --max-credits N`. It costs 1.96 credits only per `moved` row. Statuses: `moved | no_change | left_company | unknown | profile_unavailable | no_new_company`.
3. Keep fresh movers: `uv run python -m outbound.filter out/champions_checked.csv --out out/movers.csv --keep-regex 'job_change.status=^moved$' --days job_change.date=14..45 --neq job_change.new_company,old_company`.
4. GetLeads `lookup_company` on each new employer; Claude drops anyone outside the `CLAUDE.md` ICP with a one-line reason.
5. Find the new email with `uv run python -m outbound.waterfall`. If the champion is not the buyer, GetLeads `lookup_decision_makers` adds the budget owner.
6. Suppress against your CRM: `uv run python -m outbound.filter ... --suppress data/crm_export.csv`.
7. Draft each email opening `Congrats on {{new_company}}. Remember when we helped you at {{old_company}}?` plus two short lines. No account details. Run it every Monday and send nothing until you approve.

**Prompt to paste**
```
Run the Play 4 skill. Read data/champions.csv and CLAUDE.md. Check each champion with
deepline plays run prebuilt/job-change-check (5 rows first, always --max-credits), keep status moved with a move date 14 to 45 days old and a
different new company, drop non-ICP employers with a one-line reason, find the new email with outbound.waterfall, add the
budget owner if the champion is not the buyer, and suppress against data/crm_export.csv. Draft one email per champion that
opens exactly: Congrats on {{new_company}}. Remember when we helped you at {{old_company}}? then two short lines, no account
details, no usage data, no contract terms. Show every draft in a table and send nothing until I approve.
```

**Why it works:** 91% of past champions have not come back on their own three months into a new job (UserGems 2023), and new executives convert 2.5x better in their first three months. You pay only when someone actually moved, and the message references a real shared history instead of a pitch.

**What you get:** `out/movers_final.csv` with fresh, ICP-fit, unsuppressed champions, a `.dropped.csv` beside each filter step showing why rows left, and a table of drafts to approve.

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
