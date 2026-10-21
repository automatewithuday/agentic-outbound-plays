# Playbook — the five Plays step by step (operator reference)

This is the detailed reference. For the plain-language overview start with the [README](../README.md). Each Play below lists its steps, the exact commands, a prompt to paste into Claude Code, why it works, and what you get. The same steps live in `.claude/skills/play-*/SKILL.md`, which is what Claude actually follows.

## Before you build: connect once

1. Clone this repo.
2. `cp .env.example .env` and fill in your keys.
3. `uv sync`
4. Connect the GetLeads MCP: open https://app.getleads.io → Settings → MCP and copy the `claude mcp add getleads ...` command shown there.
5. Install Deepline: follow https://code.deepline.com/INSTALL.md.
6. Write your rules into `CLAUDE.md`. The ICP section is the only edit you need.
7. Test with ONE company before running a list.

## First-run checklist

- [ ] HeyReach: either connected through the GetLeads MCP tool `configure_heyreach` (free push via `send_contacts_to_heyreach`), or a HeyReach API key in `.env` as `HEYREACH_API_KEY` for the direct push `outbound/push_heyreach.py` (lists by default; a campaign push into an IN_PROGRESS campaign starts messaging).
- [ ] A Smartlead campaign created in the Smartlead UI and kept in DRAFT/paused until the copy is written and you have approved it; its id copied for `--campaign-id`.
- [ ] `data/crm_export.csv` exists (no CRM yet? copy the header row of `data/crm_export.example.csv`). Accepted values: `stage` `open|proposal|negotiation`, `in_sequence`/`is_customer` `true|1|yes`, `last_touched` `YYYY-MM-DD`.
- [ ] `cp .env.example .env` and filled in.
- [ ] `uv run python -m outbound.common --selftest` prints `OK`.

## Play 1 · Waterfall email finder (cold)

**Temperature:** cold. They have never heard of you.

**Job:** stop settling for 40% email coverage. Coverage is the ceiling for every other Play.

**Steps**
1. Put `first_name,last_name,company_domain,linkedin_url` in `data/leads.csv` (see `data/leads.example.csv`).
2. Check `get_fair_use` on the GetLeads MCP, then dry-run: `uv run python -m outbound.waterfall data/leads.csv --out out/leads_enriched.csv --dry-run`.
3. Run it in batches of 150: GetLeads (LinkedIn URL; charges only on a hit), then LeadMagic (name + domain), then Prospeo (LinkedIn URL + name + domain), then FullEnrich (bulk, async) on whatever is still missing. Change the order with `--providers`.
4. Every email is verified (MillionVerifier, BounceBan once if catch-all). `verified` stops the waterfall, `catch_all` and `unknown` are stored with their status and stop, `discard` tries the next provider, nothing left is `not_found`.
5. Read `out/leads_enriched.csv.report.md`. Only `verified` goes to Smartlead; the rest go to a LinkedIn-only track.

**Prompt to paste**
```
Read data/leads.csv, dedupe, run uv run python -m outbound.waterfall data/leads.csv --out out/leads_enriched.csv --batch 150 --dry-run
and show me the plan. After I approve, run it for real: stop at the first verified email per row, never build an
email from a naming pattern, write out/leads_enriched.csv (email, email_status, email_provider, verifier, mx_class, domain_match, miss_reason),
and report % verified / % catch-all / % unknown / % not found, hits per provider and spend.
Catch-all and unknown never go to Smartlead. Wait for my approval before pushing.
```

**Why it works:** no single vendor covers every region, so chaining them lifts coverage. GetLeads charges only on a hit, so the cheap first step costs nothing on misses, and the stop rule means you pay for the next provider only when needed.

**What you get:** `out/leads_enriched.csv` with every deduplicated row kept plus the seven email columns, and a report with coverage percentages and spend. Aim for bounces under 2%. Hand-check any row with `domain_match=no` before it goes anywhere: the email is real but probably belongs to a namesake at another company.

## Play 2 · Signal scoring (warm)

**Temperature:** warm. Something just changed at the company.

**Job:** rank your TAM by fresh buying signals so you work the hot accounts this week and nurture the rest. Closer signals and more signals mean higher intent.

**Steps**
1. Start from `data/tam.csv` (`company_domain,company_name`); build it with GetLeads `search_companies` if you have none. Signals only rank a list.
2. Collect third-party signals into `out/signals.csv` (`company_domain,signal_type,party,event_date,source_url,detail`): funding by discovery with Deepline `crustdata_v3_company_search` (companies that raised in the last 28 days in your size band and country, 0.02 credits per result; ICP-fit ones join the TAM) and, for accounts already in the TAM, `predictleads_company_financing_events` (0.56 credits per call) or GetLeads `list_funding_signals` (1 credit per record; often empty), reading each source link; hiring with Apify `harvestapi~linkedin-job-search` via `common.apify`, job changes with `count_contacts` then `search_contacts` (only accounts already at 40+), optional news with Deepline `predictleads_company_news_events` (0.56 credits per call).
3. Optional social intent with Deepline's search tools (no extra account): X `twitterapi_advanced_search` (0.003 credits per result), Reddit `scrapecreators_reddit_search` (0.02 per call), Hacker News `hackernews_search` and Bluesky `bluesky_search_posts` (free). Run your pain keywords, keep buyers asking for help in the last 14 days, map the author to a company, and add `social_intent` rows.
4. Add first-party rows (`data/crm_export.csv` closed-lost and stalled, `data/transcripts/`, Play 5 visits, Play 3 engagement on your posts) and second-party rows (partner-post engagement, Play 4 champions).
5. Score: `uv run python -m outbound.score_signals data/tam.csv --signals out/signals.csv --out out/accounts_scored.csv`. Weights are 40 first-party, 25 second-party, 10 third-party, capped at 100, from `config/signal_scoring.yaml` (edit it with your own reply and meeting data). Bands: `work_today` 80+, `sequence_this_week` 40 to 79, `nurture` below 40. Events outside their freshness window (for example funding within 28 days, hiring within 14, job change 14 to 45) are dropped.
6. For `work_today` accounts, `lookup_decision_makers(domain, limit 5)` and keep 2 buyers per account by your `CLAUDE.md` titles; run `outbound.waterfall` only on rows with no valid email. Show the table; nothing sends.

**Prompt to paste**
```
Run the Play 2 skill. Use data/tam.csv (build it with search_companies if missing). Collect funding (list_funding_signals, last 28 days,
verify each source link), hiring (Apify harvestapi~linkedin-job-search), job changes (count_contacts then search_contacts for 40+ accounts),
optional news and Deepline social intent (X, Reddit, HN, Bluesky) into out/signals.csv. Add first-party rows from data/crm_export.csv and data/transcripts/
and second-party rows from partner posts and Play 4 champions. Keep only signals inside the windows in config/signal_scoring.yaml, drop
duplicates, then run uv run python -m outbound.score_signals data/tam.csv --signals out/signals.csv --out out/accounts_scored.csv.
For work_today accounts find 2 buyers each by CLAUDE.md titles. State the cost before every paid step. Show me the table. Send nothing until I approve.
```

**Why it works:** Gong Labs (2023) found emails that reference buyer-journey actions get about 3x the replies and meetings. A scored list tells you which account has a real, recent reason to talk, and the first line can name it.

**What you get:** `out/accounts_scored.csv` with `company_domain,company_name,score,band,signal_count,signals` for every TAM row, band counts printed in the terminal, and two verified buyers per `work_today` account.

## Play 3 · LinkedIn post engagers (warm)

**Temperature:** warm. They just raised a hand on a post about your topic.

**Job:** turn the people who commented on or reacted to a post (yours, a partner's or a competitor's) into tiered outreach, within a day of a post that performs.

**Steps**
1. Input one post URL. For ongoing monitoring of your own and partner profiles: GetLeads `estimate_scrape_cost`, then `add_monitored_profile(linkedin_profile_url, billing_choice)`, then `list_profile_monitoring_leads` (paid from wallet cash).
2. Run `deepline plays describe prebuilt/linkedin-post-to-engagers-harvestapi` first, then `deepline plays run prebuilt/linkedin-post-to-engagers-harvestapi --input '{"post_url": "<url>"}' --max-credits N --run-id-file out/engagers_run_<post-id>.json` and `deepline runs export <run-id> --out out/engagers_<post-id>.csv`. Fallbacks: GetLeads `scrape_linkedin_post_once(post_url)` (wallet cash) or Apify `harvestapi~linkedin-post-reactions` / `harvestapi~linkedin-post-comments`. Columns: `first_name,last_name,linkedin_url,position,engagement_type (LIKE|comment)`.
3. Dedupe: `uv run python -m outbound.filter out/engagers_<post-id>.csv --out out/engagers_dedup.csv --dedupe-on linkedin_url` (count posts per person first if you pulled several).
4. Cheap-first enrich: test the buyer titles from `CLAUDE.md` against `position` with `outbound.filter --keep-regex`; only matching rows get Deepline `harvestapi_get_profile` (about 0.05 credits per profile; check `deepline tools describe harvestapi_get_profile`, and run it on one row first) and GetLeads `lookup_company`.
5. Tier with Claude (for more than 30 rows, tier in batches of 10 with a cheap sub-agent (Haiku), then spot-check 5): T1 ICP account + buyer title + engaged on more than one post or commented; T2 ICP account + buyer or influencer title; T3 ICP account, other roles; Out = outside the ICP. Writes `tier,tier_reason`.
6. Suppress against `data/crm_export.csv`. A T1 person a rep already owns becomes an alert line, not outreach.
7. Find emails for tiers 1 to 3 with `uv run python -m outbound.waterfall`.
8. Write one first line each from the post topic plus one recent company event (Play 2 signals if you have them). One sentence, no flattery.
9. Show the table and drafts. After approval: T1 to HeyReach via GetLeads `send_contacts_to_heyreach` (`dry_run` first) or `uv run python -m outbound.push_heyreach out/engagers_final.csv --list-id ID --dry-run` (direct API, `HEYREACH_API_KEY` in `.env`) and Smartlead with `push_smartlead --custom first_line`; T2 and T3 to Smartlead only. One email tool per lead.

**Prompt to paste**
```
Run the Play 3 skill. Post URL: <paste>. Read CLAUDE.md for the ICP and buyer titles. Run deepline plays describe
prebuilt/linkedin-post-to-engagers-harvestapi, then run it with --max-credits and export to out/engagers_<post-id>.csv.
Dedupe on linkedin_url with outbound.filter. Match buyer titles against position first and run harvestapi_get_profile only on
matching rows; get the company with lookup_company. Tier everyone (T1 ICP + buyer title + commented or multi-post, T2 ICP + buyer or
influencer, T3 ICP other roles, Out) with tier and tier_reason. Suppress against data/crm_export.csv; T1 people a rep owns become an
alert line. Find emails for tiers 1 to 3 with outbound.waterfall. Write one first line each from the post topic plus one recent
company event, no flattery. Show me the list and drafts. After I approve: T1 to HeyReach (send_contacts_to_heyreach, dry_run first)
and Smartlead, T2 and T3 to Smartlead only, one email tool per lead. Send nothing until I approve.
```

**Why it works:** someone who commented on your topic this week has already shown interest, and the message can name two real things: what they engaged with and what is happening at their company. Cheap-first enrichment means you pay for a profile only when the position (LinkedIn headline) already looks like a buyer.

**What you get:** `out/engagers_final.csv` with tiered, ICP-fit, unsuppressed engagers who have a verified email and a `first_line`, an alert line for any T1 a rep owns, and a drafts table to approve.

**Guardrail:** LinkedIn's User Agreement prohibits scraping and automated activity, and accounts that use such tools risk restriction. Keep volume low and prefer your own and partner posts.

## Play 4 · Champion reactivation (hot)

**Temperature:** hot. They already know and like you.

**Job:** reach past champions who just started a new job, while the move is fresh (14 to 45 days).

**Steps**
1. Put `name,email,linkedin_url,old_company,old_company_domain,role` in `data/champions.csv` (see `data/champions.example.csv`). Only people you actually helped.
2. Check for moves with Deepline in three commands: `deepline plays describe prebuilt/job-change-check`, then write a copy of the CSV with the play's own headers (`linkedin_url, company_domain` = the company on record, `full_name, email`; this play takes no column mapping) and run `deepline plays run prebuilt/job-change-check --csv out/champions_in.csv --max-credits N --run-id-file out/champions_run.json`, then `deepline runs export <run-id> --out out/champions_checked.csv` (run id from the run-id file). It costs 1.96 credits only per `moved` row. Statuses: `moved | no_change | left_company | unknown | profile_unavailable | no_new_company`.
3. Keep fresh movers: `uv run python -m outbound.filter out/champions_checked.csv --out out/movers.csv --json-col job_change --keep-regex 'job_change.status=^moved$' --days job_change.date=14..45 --neq job_change.new_company,old_company` (`--json-col` expands the nested `job_change` cell the export writes).
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

**Temperature:** hot. They are on your site right now.

**Job:** reach the companies that just looked at pricing, demo or case study pages, the same day, with copy that fits the page.

**Steps**
1. One time: GetLeads MCP `get_wallet_balance`, then `start_website_visitor_tracking(domain)`, paste the install snippet into `<head>`, `configure_website_pixel` (webhook and privacy), then `complete_website_pixel_setup` (needs auto top-up). Update your privacy policy and consent first. People are named mostly for US and Canadian visitors; elsewhere expect the company only.
2. Daily: `export_website_visitor_leads` (or `list_website_visitor_leads view=unique`) into `data/visitors_<date>.csv`. Check the header for the page column; `page` below is an example.
3. Keep high-intent pages: `uv run python -m outbound.filter data/visitors_<date>.csv --out out/visitors_intent.csv --keep-regex 'page=pricing|demo|case-stud|compar|vs-'`, then `--suppress data/crm_export.csv`.
4. Claude scores each company against `CLAUDE.md` and saves `out/visitors_icp.csv`. Add an empty `email_status` column to every row first (one `python -c` one-liner, see the skill). For ICP companies with no named person, `lookup_decision_makers` finds the buyer by your titles; append them as `email_status=verified`. The waterfall input needs `first_name,last_name,company_domain,linkedin_url`, so map the visitor export columns to those names (person name split to first/last, company website to `company_domain`, person LinkedIn to `linkedin_url`) before step 5.
5. Split with `outbound.filter` (`--keep-regex 'email_status=^verified$'` and `'email_status=^(?!verified)'`), run `uv run python -m outbound.waterfall` on the not-verified rows, and merge both into `out/visitors_final.csv`. Derive `page_topic` from the page URL (for example "pricing for multi-seat teams"); the copy never says you saw the visit.
6. Show the table. Day 1 is always a dry run: `uv run python -m outbound.push_smartlead out/visitors_final.csv --campaign-id ID --custom first_line,page_topic --dry-run`, plus `send_contacts_to_heyreach` with `dry_run: true`. After approval push for real. Smartlead gets only `verified` rows. HeyReach gets ICP rows that have a `linkedin_url`, whatever their email status (LinkedIn is the channel for catch_all, unknown and not_found rows, and a parallel touch for the others). Each lead gets email from one tool only; LinkedIn plus email for the same person is allowed.

`configure_website_visitors_smartlead` can auto-push to Smartlead, but it has no filter, no suppression and no approval step, so it is not the default.

**Prompt to paste**
```
Run the Play 5 skill. Export today's visitors with export_website_visitor_leads into data/visitors_<date>.csv, check the header
for the page column, keep pricing|demo|case-stud|compar|vs- pages with outbound.filter, suppress against data/crm_export.csv,
and score each company against CLAUDE.md into out/visitors_icp.csv. Add buyers from lookup_decision_makers as verified, split
verified from not-verified, run outbound.waterfall on the rest, merge into out/visitors_final.csv, and derive page_topic from the
page URL. Never mention that we saw the visit. Show me the table. Day 1 is a dry run only (push_smartlead --dry-run,
send_contacts_to_heyreach dry_run true). After I approve: Smartlead gets verified rows only, HeyReach gets ICP rows with a
linkedin_url, and each lead gets email from one tool only. Send nothing until I approve.
```

**Why it works:** intent is concentrated on a few pages. HockeyStack measured 3.8% form-fill on pricing pages against 1.1% site-wide. A suppressed, ICP-scored, verified list with a `page_topic` that fits the page beats blasting everyone the pixel catches.

**What you get:** `out/visitors_final.csv` of ICP-fit, unsuppressed visitors with a verified email and a `page_topic`, a dry-run payload to inspect, and `out/pushed_registry.csv` recording what went to Smartlead and when. Run it daily.

## Build order

1. Setup: keys, MCP and `CLAUDE.md` first; every Play depends on them.
2. Play 1: cheapest, and it proves the cost and suppression plumbing on a plain list.
3. Play 4: your own past champions are the hottest list with the least data work.
4. Play 5: hot intent; small volume, highest reply rate.
5. Play 2: scoring needs weights tuned against your results from Plays 1, 4 and 5.
6. Play 3: post scraping is the most variable cost; do it last with a tight cap.

## Rhythm

| Play | When |
|---|---|
| 1 Waterfall email finder | Every time you get a new list |
| 2 Signal scoring | Weekly |
| 3 LinkedIn post engagers | Within a day of every post that performs |
| 4 Champion reactivation | Every Monday |
| 5 Website visitors | Daily |

## Guardrails

- First 100 contacts, then inspect before scaling. Test every Play with one company or 5 rows first.
- Batches of 100 to 200 rows; `/compact` between batches.
- Approvals stay on for anything that sends. Every skill ends with a table, your approval, and only then a push.
- Spend caps: HARD caps are Deepline plays (`--max-credits`, derived from the estimate via `DEEPLINE_CREDIT_USD` in `common.py`) and Apify (`maxTotalChargeUsd`). ESTIMATE-based caps (the ledger aborts on its own estimate, the vendor does not enforce it) are GetLeads credits (set `GETLEADS_CREDIT_USD`) and Deepline `tools execute` calls. Also `estimate_scrape_cost` before any monitored profile; check `get_fair_use` and `get_wallet_balance` first. Never loop around a cap.
- Only `verified` emails reach Smartlead. Catch-all and unknown stay out of live sequences. One email tool per lead.
- Pushes are recorded in one shared `out/pushed_registry.csv` (read on every run, dry or real). To deliberately re-push a lead, delete its row from `out/pushed_registry.csv`. LinkedIn plus email for the same person is allowed; two email tools is not.
- `.cache/calls.jsonl` stores raw API responses, including emails, unencrypted and git-ignored. Delete it when a project ends.
- Suppression runs before every push: open opportunities, active sequences, recent touches and customers come from `data/crm_export.csv`.
- LinkedIn scraping (Play 3) and visitor identification (Play 5) carry platform and privacy risk. Read the guardrails in each skill.
- Secrets live in `.env` only. Never paste keys into prompts or commit them.

## Tool map

| Play | Tools |
|---|---|
| 1 | GetLeads → LeadMagic → Prospeo → FullEnrich (each via Deepline tools), verified by MillionVerifier / BounceBan (`outbound.waterfall`) |
| 2 | Crustdata funding discovery and PredictLeads events (Deepline), GetLeads `search_contacts`, Apify job search, Deepline X/Reddit/HN/Bluesky search, `outbound.score_signals` |
| 3 | Deepline `prebuilt/linkedin-post-to-engagers-harvestapi`, GetLeads `add_monitored_profile` |
| 4 | Deepline `prebuilt/job-change-check` |
| 5 | GetLeads website pixel and `export_website_visitor_leads` |
| Sending | Smartlead (email, `outbound.push_smartlead`), HeyReach (LinkedIn, `outbound.push_heyreach` or GetLeads `send_contacts_to_heyreach`) |
