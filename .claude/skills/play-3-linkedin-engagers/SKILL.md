---
name: play-3-linkedin-engagers
description: Use when you want to turn the people who commented on or reacted to a LinkedIn post (yours, a partner's or a competitor's) into tiered outreach, within a day of a post that performs
license: MIT
metadata:
  author: automatewithuday
  source: martechs.io
  version: "1.0"
  category: signals
---

# Play 3 · LinkedIn post engagers (warm)

## How to apply this skill

**Inputs**
- One post URL: your own, a partner's, or a competitor's. For ongoing monitoring of your own and partner profiles, a profile URL.
- `CLAUDE.md` for the ICP and the buyer titles. `data/crm_export.csv` for suppression.
- Optional: `out/accounts_scored.csv` from Play 2, for the company event in the first line.
- A Smartlead campaign id (`--campaign-id`) and a HeyReach campaign configured in GetLeads.

**Compute**
- Pull the engagers, drop duplicates, then spend money only on rows that survive a free check: the title regex runs on the `headline` column before any paid profile lookup.
- Tier each person against the ICP: T1 ICP account + buyer title + commented or engaged on more than one post; T2 ICP account + buyer or influencer title; T3 ICP account, other roles; Out = outside the ICP.
- Two context layers decide the message: the topic of the post they engaged with, and one recent event at their company.
- Engagement from the pull is only as fresh as the pull. Run this within a day of any post that performs.

**Report**
- Engagers pulled, rows kept per filter step, rows enriched, tier counts with reasons, T1 people already owned by a rep, email coverage after the waterfall, drafts table, credits and wallet cash spent.

## Steps

1. Input. One post URL. For ongoing monitoring of your own and partner profiles use the GetLeads MCP: `estimate_scrape_cost` first, then `add_monitored_profile(linkedin_profile_url, billing_choice)`, then read results with `list_profile_monitoring_leads`. This is paid from wallet cash (check `get_wallet_balance`), not plan credits.
2. Extract. Run `deepline plays describe prebuilt/linkedin-post-to-engagers-harvestapi` first and read the exact inputs and outputs. Then, with a credit ceiling (a named play has no useful `--dry-run`, so the cap is the guard):
   - `deepline plays run prebuilt/linkedin-post-to-engagers-harvestapi --input '{"post_url": "<url>"}' --max-credits N --run-id-file out/engagers_run_<post-id>.json` (the `--run-id-file` destination must not already exist, so use a fresh name per run).
   - `deepline runs export <run-id> --out out/engagers_<post-id>.csv` with the run id from the run-id file.
   - Fallbacks if Deepline fails: GetLeads `scrape_linkedin_post_once(post_url)` (wallet cash), or Apify `harvestapi~linkedin-post-reactions` and `harvestapi~linkedin-post-comments` through `common.apify` with a `maxTotalChargeUsd` cap. The actor input fields are unverified: check each actor's page before the first run.
   - Normalise to `name,linkedin_url,headline,engagement,comment_text`, where `engagement` is `comment` or `reaction`. Map whatever column names the export uses to these and say what you mapped. Add a `post_url` column.
3. Merge and dedupe. If you pulled several posts, stack the files and add `posts_engaged` (how many distinct posts each `linkedin_url` touched) before deduping, because T1 depends on it. Then `uv run python -m outbound.filter out/engagers_<post-id>.csv --out out/engagers_dedup.csv --dedupe-on linkedin_url`.
4. Cheap-first enrich. Split on the free `headline` title test, with the regex rebuilt from the current `CLAUDE.md` buyer titles (a missing column fails loudly): matching rows `uv run python -m outbound.filter out/engagers_dedup.csv --out out/engagers_titled.csv --keep-regex 'headline=(?i)\b(founder|ceo|vp sales|head of growth|head of marketing|head of revops|cro)\b'`, the rest `... --out out/engagers_other.csv --keep-regex 'headline=(?i)^(?!.*\b(founder|ceo|vp sales|head of growth|head of marketing|head of revops|cro)\b)'`. Only the titled rows get `deepline tools execute harvestapi_get_profile --input '{"profileUrl": "<linkedin_url>"}' --json` (about 0.05 credits per profile; check `deepline tools describe harvestapi_get_profile`; the input field name is unverified, so run it on one row first and read the error or output). Resolve each company with GetLeads `lookup_company` and add `company_name,company_domain`. The other rows get no paid lookup: Claude reads the company from the `headline` and keeps them only as T3 candidates when it is clearly an ICP account. Merge both into `out/engagers_enriched.csv`.
5. Tier. Claude reads each row against `CLAUDE.md` and writes `tier` (`1`, `2`, `3` or `out`) and `tier_reason` (one line). For more than 30 rows, tier in batches of 10 with a cheap sub-agent (Haiku), then spot-check 5. Save `out/engagers_tiered.csv`; drop `out` rows with `uv run python -m outbound.filter out/engagers_tiered.csv --out out/engagers_icp.csv --keep-regex 'tier=^[123]$'`.
6. Suppress. `uv run python -m outbound.filter out/engagers_icp.csv --out out/engagers_clean.csv --suppress data/crm_export.csv`. Any T1 row that dropped because a rep already owns it (open opportunity or active sequence in `out/engagers_clean.csv.dropped.csv`) becomes one alert line for the rep ("Name, company, engaged with <post>"), not outreach.
7. Email. The waterfall needs `first_name,last_name,company_domain,linkedin_url`: split `name`, use `company_domain`. Take tiers 1 to 3 (the file already holds only those): `uv run python -m outbound.waterfall out/engagers_clean.csv --out out/engagers_final.csv --dry-run`, then for real after the user agrees to the plan, passing `--cap-usd` from the Spend caps section of `CLAUDE.md`.
8. First line, one per row, from two things: the topic of the post they engaged with (read the post, and for a commenter the comment itself) and one recent event at their company (Play 2 signals if present, otherwise `lookup_company` or a news check). One sentence, no flattery, no "loved your comment". Save as `first_line`.
9. Show the table (name, title, company, tier, tier_reason, engagement, email status, first_line) and wait for explicit approval. T1: a human reads the post before it goes. After approval:
   - T1 on LinkedIn: GetLeads `send_contacts_to_heyreach` with `dry_run: true` first, show the result, then the real call.
   - T1 email, if `verified`: `uv run python -m outbound.push_smartlead out/engagers_final.csv --campaign-id ID --custom first_line --dry-run`, then for real (every push is recorded in `out/pushed_registry.csv`; to deliberately re-push a lead, delete its row from `out/pushed_registry.csv`). T2 and T3: Smartlead only, same command. Push T1 and T2/T3 with separate filtered files if they use different campaigns.
   - Each lead gets email from one tool only. Smartlead takes `verified` rows only; the others stay on LinkedIn or the not-found track.

## Prompt to paste

```
Run the Play 3 skill. Post URL: <paste>. Read CLAUDE.md for the ICP and buyer titles. Run deepline plays describe
prebuilt/linkedin-post-to-engagers-harvestapi, then deepline plays run it with --max-credits and export to
out/engagers_<post-id>.csv (name, linkedin_url, headline, engagement comment|reaction, comment_text). Dedupe on linkedin_url
with outbound.filter. Match the buyer titles against headline first and only run harvestapi_get_profile on matching rows;
get the company with lookup_company. Tier every person: T1 ICP account + buyer title + commented or engaged on more than one post,
T2 ICP account + buyer or influencer title, T3 ICP account other roles, Out otherwise; write tier and tier_reason (more than 30 rows:
batches of 10 with a Haiku sub-agent, then spot-check 5). Suppress against data/crm_export.csv; T1 people a rep already owns
become an alert line, not outreach. Find emails for tiers 1 to 3 with outbound.waterfall. Write one first line each from the post
topic plus one recent company event: one sentence, no flattery. Show me the list and drafts. After I approve: T1 to HeyReach via
send_contacts_to_heyreach (dry_run first) and Smartlead with push_smartlead --custom first_line, T2 and T3 to Smartlead only.
One email tool per lead. State every cost before the paid step. Send nothing until I approve.
```

## Guardrails

- Nothing sends without approval. Show the table and drafts first; a human reads the post before any T1 message goes.
- LinkedIn's User Agreement prohibits scraping and automated activity, and accounts that use such tools risk restriction. Use a pull you are comfortable with, keep volume low, and prefer your own and partner posts.
- Spend is capped: always `--max-credits` on Deepline (a named play has no useful `--dry-run`), `estimate_scrape_cost` before any monitored profile, `maxTotalChargeUsd` on Apify. Wallet cash is real money: check `get_wallet_balance` and report after. Never loop around a cap.
- Cheap-first: no paid profile lookup before the free `headline` title test.
- Smartlead gets `verified` rows only. One email tool per lead; `push_smartlead.py` refuses emails already in `out/pushed_registry.csv`.
- The first line never flatters and never says "I saw you engaged". It references the topic and a company event.
- Secrets stay in `.env`; never print them. The Smartlead call is unverified against `https://api.smartlead.ai/reference`; check the first dry-run payload.

## Common mistakes

- Running the profile lookup on every engager instead of the title-matching rows.
- Deduping before counting posts, so nobody ever reaches T1.
- Emailing a T1 person a rep already owns.
- Treating a reaction like a comment. A comment is the stronger signal; use `comment_text` in the line.
- Waiting a week. The signal cools fast: go within a day of the post.
- Flattering the person in the first line instead of naming the post topic and a company event.
- Sending the same lead to Smartlead and another email tool.
