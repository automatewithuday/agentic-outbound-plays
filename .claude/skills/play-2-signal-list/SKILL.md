---
name: play-2-signal-list
description: Use when you want to rank your TAM by fresh buying signals (funding, hiring, job changes, news, social intent, your own CRM and engagement data) and work only the accounts that are hot this week
license: MIT
metadata:
  author: automatewithuday
  source: martechs.io
  version: "1.0"
  category: signals
---

# Play 2 · Signal scoring (warm)

## How to apply this skill

**Inputs**
- `CLAUDE.md` for the ICP, buyer titles and the pain keywords.
- `data/tam.csv` with `company_domain,company_name`. Signals only rank a list; they do not build one.
- `config/signal_scoring.yaml` (weights, freshness windows, bands, ListeningKit threshold). Edit it with your own reply and meeting data. Do not change it without telling the user.
- Optional: `data/crm_export.csv`, `data/transcripts/`, Play 5 visitor exports, Play 3 and Play 4 outputs.

**Compute**
- Collect signals with MCP tools and the CLI (Python does not collect). Write every signal to `out/signals.csv` with columns `company_domain,signal_type,party,event_date,source_url,detail`.
- `signal_type` is one of `job_change|funding|hiring|news|social_intent|website_visit|engagement|crm_closed_lost|transcript_mention`. `party` is `first|second|third`. `event_date` is `YYYY-MM-DD`.
- `uv run python -m outbound.score_signals` drops signals outside their freshness window, dedupes the same event from different sources, scores per party weight (capped at `max_score`) and assigns a band: `work_today` (80+), `sequence_this_week` (40 to 79), `nurture` (below).
- Closer signals mean higher intent, and more signals mean higher intent.

**Report**
- Signals collected per type, rows dropped by the scorer and why, accounts per band, the top accounts with their `signals` string, buyers found for `work_today`, and credits or dollars spent.

## Steps

1. TAM: confirm `data/tam.csv` exists. If not, build it with GetLeads MCP `search_companies`, filtered by the ICP in `CLAUDE.md` (use `count_companies` first, it is free). Start `out/signals.csv` with only the header row.
2. Funding (third party), two sources, both verified live on 21 Oct 2026:
   - Discovery of newly funded accounts that are not in the TAM yet: Deepline `crustdata_v3_company_search` (0.02 credits per result). Filters are an and-group: `{"filters": {"op": "and", "conditions": [{"field": "funding.last_fundraise_date", "type": "=>", "value": "<28 days ago>"}, {"field": "locations.country", "type": "=", "value": "USA"}, {"field": "headcount.total", "type": "=>", "value": 20}, {"field": "headcount.total", "type": "=<", "value": 500}]}, "sorts": [{"field": "funding.last_fundraise_date", "order": "desc"}], "limit": 20}`; run it with `deepline tools execute crustdata_v3_company_search --input '<json>' --json`. Read `companies[].basic_info.primary_domain`, `funding.last_fundraise_date`, `funding.last_round_type`, `funding.last_round_amount_usd`. Keep only ICP-fit companies, add them to `data/tam.csv`, and append `signal_type=funding, party=third` rows dated `last_fundraise_date`.
   - Confirmation for accounts already in the TAM: Deepline `predictleads_company_financing_events` (0.56 credits per call, so only for accounts you care about: `{"company_id_or_domain": "<domain>", "first_seen_at_from": "<28 days ago>"}`), or the free-when-empty GetLeads MCP `list_funding_signals(since, region, limit)` (1 credit per record returned; it returned 0 rows for 80 days in testing, so do not rely on it alone). Open each source link and confirm it is a real round; drop press-release noise.
3. Hiring (third party): Apify `harvestapi~linkedin-job-search`, run through `common.apify(actor, run_input, max_usd)` for the TAM domains, with `max_usd` taken from the user's cap. Check the actor's input schema on Apify first; the field names below are an example only. This is a paid run (real money, capped at $1 via `max_usd`): `uv run python -c "from outbound import common as c; print(len(c.apify('harvestapi~linkedin-job-search', {'companies': ['example.com'], 'postedLimit': '1w'}, 1.0)))"`. Count postings from the last 14 days per company and append one `hiring` row per company: `event_date` is the newest matching posting's `postedAt` date from the Apify output (as `YYYY-MM-DD`), `detail` is the number of postings in the window, and `source_url` is that posting's URL. Run `--dry-run`-style first: estimate, show the user, then run.
4. New exec or job change (third party), only for accounts that already score 40 or more after steps 2 and 3 (run the scorer once to find them): GetLeads `count_contacts` (free) first, then `search_contacts(domains, job_start_date_min, job_titles from CLAUDE.md, email_status: ["VALID"], max_per_company: 2)`. Append `signal_type=job_change, party=third`, `event_date` = the job start date.
5. News (third party, optional, only with `--news`, only for accounts at 40 or more): `deepline tools execute predictleads_company_news_events --input '<json>' --json`. It costs 0.56 credits per call; state the total before running. Append `signal_type=news, party=third`.
6. Social intent (third party, optional): Log by ListeningKit MCP. One-time setup: `claude mcp add listeningkit -- https://log.listeningkit.com/mcp --header "Authorization: Bearer <key>"`, or self-host from https://github.com/matthewdonsemail-lab/log. Add the pain keywords from `CLAUDE.md` with `add_keyword`, then `list_matches(min_score = listeningkit.min_score from the yaml, platform)` for each platform in the yaml, and `get_match` for detail. Platforms are Reddit, X and Facebook only. There is no LinkedIn. Claude maps the author or post to a company and confirms the domain with GetLeads `lookup_company`. Skip matches it cannot map. The row carries the post permalink as `source_url`.
7. First-party and second-party rows:
   - `first`: closed-lost and stalled rows in `data/crm_export.csv` (`crm_closed_lost`); `grep -ril "<domain>" data/transcripts/` for each TAM domain (`transcript_mention`, date from the file); Play 5 visitor exports (`website_visit`); engagement on your own posts from Play 3 (`engagement`).
   - `second`: engagement on partner posts (Play 3 pointed at partner profiles) and champions from Play 4 (`engagement`, or `job_change` for a champion who moved).
8. Score: `uv run python -m outbound.score_signals data/tam.csv --signals out/signals.csv --out out/accounts_scored.csv`. It prints counts per band and warns on stderr about dropped rows (blank dates, unknown types or parties, stale or too-early events).
9. For `work_today` accounts only: GetLeads `lookup_decision_makers(domain, limit 5)`, keep 2 per account whose title matches `CLAUDE.md`. These emails are always VALID; save them as `email_status=verified`. Buyers you already have without a valid email go to `uv run python -m outbound.waterfall out/buyers_need_email.csv --out out/buyers_enriched.csv --dry-run`, then for real after the user agrees (pass `--cap-usd` from the Spend caps section of `CLAUDE.md`).
10. Show the scored table (domain, score, band, signals, the 2 buyers). Wait for explicit approval. Nothing sends from this Play; approved accounts feed Play 1 to Play 5 sequences.

## Prompt to paste

```
Run the Play 2 skill. Read CLAUDE.md for the ICP, buyer titles and pain keywords. Use data/tam.csv; if it is missing, build it with
search_companies. For the accounts in the TAM, collect signals into out/signals.csv: funding with list_funding_signals (since 28 days ago,
limit 200, open each source link and keep only real rounds), hiring with Apify harvestapi~linkedin-job-search, job changes with
count_contacts then search_contacts only for accounts at 40+, news with predictleads_company_news_events if I pass --news, and
social intent from ListeningKit list_matches. Keep only signals inside the freshness windows in config/signal_scoring.yaml and drop
duplicates. Add first-party signals from data/crm_export.csv (closed-lost and stalled) and data/transcripts/, plus Play 5 visits and
Play 3 engagement; add second-party signals from partner-post engagement and Play 4 champions. Tag each with its party. Run
uv run python -m outbound.score_signals data/tam.csv --signals out/signals.csv --out out/accounts_scored.csv. For work_today
accounts, find 2 buyers each with lookup_decision_makers using the CLAUDE.md titles, and run the waterfall only on rows with no
valid email. Tell me the cost before each paid step. Show me the table. Send nothing until I approve.
```

## Guardrails

- Nothing sends without approval. This Play ends at a table.
- Paid calls need a cost statement first: `crustdata_v3_company_search` (0.02 credits per result), `predictleads_company_financing_events` and `predictleads_company_news_events` (0.56 credits per call each), `list_funding_signals` (1 credit per record), Apify (`maxTotalChargeUsd` from the cap). Respect the cap; never loop around it.
- Verify funding is a real round by reading the source link. Never invent a `source_url`.
- Weights, windows and bands live in `config/signal_scoring.yaml`. Propose changes; do not edit them silently.
- Use dates as `YYYY-MM-DD`. The scorer drops blank or malformed dates and unknown types or parties with a warning, so read stderr.
- Run steps 4 and 5 only for accounts at 40 or more, so you pay for enrichment only where it can change the band.
- ListeningKit covers Reddit, X and Facebook only. Do not claim LinkedIn social intent.
- Secrets stay in `.env`; never print them.

## Common mistakes

- Treating signals as a list builder. They rank the TAM; they do not replace it.
- Counting stale events: a funding round 60 days old is not a signal, and neither is a job change from this morning (the window starts at 14 days).
- Double counting one event from two sources. The scorer dedupes on domain, type and date; make the dates match.
- Spending on `search_contacts` or news for the whole TAM instead of the 40+ accounts.
- Mapping a social post to the wrong company. Confirm with `lookup_company`.
- Leaving out first-party rows. They carry the highest weight and cost nothing.
- Running the waterfall on contacts that came from `lookup_decision_makers`; those emails are already valid.
