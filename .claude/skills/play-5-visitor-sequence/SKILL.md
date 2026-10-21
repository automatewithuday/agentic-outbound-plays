---
name: play-5-visitor-sequence
description: Use when you want to turn high-intent website visitors (pricing, demo, case study pages) into a daily email and LinkedIn sequence, with page-specific copy
license: MIT
metadata:
  author: automatewithuday
  source: martechs.io
  version: "1.0"
  category: signals
---

# Play 5 · Website visitor → email sequence (hot)

## How to apply this skill

**Inputs**
- `CLAUDE.md` for the ICP and the buyer titles. `data/crm_export.csv` for suppression.
- Your site domain, a Smartlead campaign id (`--campaign-id`), and a HeyReach campaign configured in GetLeads.
- GetLeads wallet funds. Visitor identification is paid from the prepaid wallet, not from plan credits.

**Compute**
- One-time setup installs the GetLeads pixel on your site (steps 1 to 5).
- Each day: export identified visitors, keep only high-intent pages, drop anyone already in your CRM, score companies against the ICP, find a named buyer where the visit gave only a company, make sure every row has a verified email, and derive a `page_topic` from the page URL.
- Pages like pricing, demo, case studies and comparisons carry the intent. HockeyStack saw 3.8% form-fill on pricing pages against 1.1% site-wide.
- People are named mostly for US and Canadian visitors. Elsewhere expect the company only, which is why `lookup_decision_makers` is part of the loop.

**Report**
- Visits exported, rows kept per filter step, ICP verdicts, rows needing a buyer lookup, email coverage after the waterfall, and a table of company, person, page, `page_topic`, email status. State wallet balance and spend.

## Steps

One-time setup (skip once the pixel is live):

1. GetLeads MCP `get_wallet_balance`. Stop if it is empty and add funds first.
2. `start_website_visitor_tracking(domain)`. It returns the pixel and install snippet and does NOT mark it live.
3. Give the snippet to whoever owns the site and have it pasted into `<head>`. Update your privacy policy and cookie consent before go-live.
4. `configure_website_pixel` with the webhook and privacy settings.
5. `complete_website_pixel_setup`. It requires auto top-up to be on (`configure_auto_topup`, or the `create_topup_link` checkout).

Daily loop:

6. `export_website_visitor_leads` (or `list_website_visitor_leads(domain, limit 200, view: "unique")`). Save as `data/visitors_<date>.csv`.
7. Open the header of the first export and find the column holding the page URL. The column names are not documented, so do not assume. `page` is the example below; replace it with the real name. If the export has no page column, say so in the report and keep all visits.
8. Keep high-intent pages: `uv run python -m outbound.filter data/visitors_<date>.csv --out out/visitors_intent.csv --keep-regex 'page=pricing|demo|case-stud|compar|vs-'`.
9. Suppress: `uv run python -m outbound.filter out/visitors_intent.csv --out out/visitors_clean.csv --suppress data/crm_export.csv`. Open opportunities, sequences, customers and recent touches drop out.
10. Score each company against the ICP in `CLAUDE.md`. Drop non-ICP with a one-line reason. Save the survivors as `out/visitors_icp.csv`.
11. Bootstrap the status column first: add an empty `email_status` column to every export row with `uv run python -c "from outbound import common as c; r=c.read_csv('out/visitors_icp.csv'); c.write_csv('out/visitors_icp.csv', [{**x, 'email_status': x.get('email_status', '')} for x in r])"`. The waterfall input needs `first_name,last_name,company_domain,linkedin_url`, so map the visitor export columns to those names before step 13: person first and last name (split a single full-name column) to `first_name`,`last_name`; the company website/domain column to `company_domain`; the person's LinkedIn profile column to `linkedin_url` (check the real header; the names are not documented). Then, for ICP companies with no named person: `lookup_decision_makers(domain, limit 5)` and keep the contacts whose title matches `CLAUDE.md`. The tool description says "Always VALID emails", so append these buyer rows to `out/visitors_icp.csv` with the same columns and `email_status=verified`, `email_provider=getleads_dm`, `verifier=getleads`.
12. Split on email status (relies on the empty `email_status` column from step 11). Verified rows: `uv run python -m outbound.filter out/visitors_icp.csv --keep-regex 'email_status=^verified$' --out out/visitors_verified.csv`. The rest: `uv run python -m outbound.filter out/visitors_icp.csv --keep-regex 'email_status=^(?!verified)' --out out/visitors_need_email.csv`.
13. Find emails for the rest: `uv run python -m outbound.waterfall out/visitors_need_email.csv --out out/visitors_enriched.csv --dry-run`, then for real after the user agrees to the plan, passing `--cap-usd` from the Spend caps section of `CLAUDE.md`. Merge into one file: `uv run python -c "from outbound import common as c; c.write_csv('out/visitors_final.csv', c.read_csv('out/visitors_verified.csv') + c.read_csv('out/visitors_enriched.csv'))"`.
14. Add a `page_topic` column to `out/visitors_final.csv` per row from the page URL, for example `/pricing?seats=10` becomes `pricing for multi-seat teams`. The copy never says "I saw you visit". When a second signal exists (a Play 2 score, a Play 3 engagement), use it for the opener and let `page_topic` shape the offer.
15. Show the table and wait for explicit approval. **Day 1 is always a dry run**: `uv run python -m outbound.push_smartlead out/visitors_final.csv --campaign-id ID --custom first_line,page_topic --dry-run`. It prints the first payload and which rows were refused.
16. After approval, push for real: `uv run python -m outbound.push_smartlead out/visitors_final.csv --campaign-id ID --custom first_line,page_topic` (records each batch in `out/pushed_registry.csv`, shared by all Plays). Then LinkedIn: `send_contacts_to_heyreach` with `dry_run: true` on the rows that have a `linkedin_url`, show the result, then the real call. Smartlead gets only `verified` rows. HeyReach gets ICP rows that have a `linkedin_url`, whatever their email status (LinkedIn is the channel for catch_all, unknown and not_found rows, and a parallel touch for the others). Each lead gets email from one tool only; LinkedIn plus email for the same person is allowed.

## Prompt to paste

```
Run the Play 5 skill every day. Read CLAUDE.md for the ICP and titles. Export visitors with export_website_visitor_leads
(or list_website_visitor_leads view unique) into data/visitors_<date>.csv. Check the export header for the page column,
then keep high-intent pages: uv run python -m outbound.filter ... --keep-regex 'page=pricing|demo|case-stud|compar|vs-'.
Suppress against data/crm_export.csv. Score each company against the ICP, drop the rest with a one-line reason, save out/visitors_icp.csv.
For ICP companies without a named person, run lookup_decision_makers with the CLAUDE.md titles and append those buyers to
out/visitors_icp.csv as email_status verified. Split verified from not-verified with outbound.filter (--keep-regex 'email_status=^verified$'
and 'email_status=^(?!verified)'), run outbound.waterfall on the not-verified rows, and merge both into out/visitors_final.csv.
Derive page_topic from the page URL, and never mention that we saw the visit. Show me the table.
Day 1 is a dry run only: uv run python -m outbound.push_smartlead out/visitors_final.csv --campaign-id ID --custom first_line,page_topic --dry-run,
then send_contacts_to_heyreach with dry_run true. After I approve, push to Smartlead (verified only) and send ICP rows
with a linkedin_url to HeyReach. Each lead gets email from one tool only. Send nothing until I approve.
```

## Guardrails

- Nothing sends without approval. Show the table first. Day 1 is always `--dry-run`.
- The copy never reveals the visit. `page_topic` informs the offer only.
- Update the privacy policy and consent before the pixel goes live. Respect the privacy settings in `configure_website_pixel`.
- Only `verified` goes to Smartlead. `catch_all` and `unknown` are refused by `push_smartlead.py` unless you pass `--allow-status`, and never allow `catch_all`. `--only-status catch_all` is an explicit override and must never be used for a live sequence.
- `out/pushed_registry.csv` (email, pushed_to, campaign_id, pushed_at, source_file) is read at the start of every run, dry or real, and an email in it is refused, so nothing is sent twice from any file. To deliberately re-push a lead, delete its row from `out/pushed_registry.csv`. If a push fails partway, inspect, then re-run the same command; batches already recorded are skipped. If Smartlead's response says `added_count` is below what was sent, the batch is still recorded and a WARN names the gap: Smartlead skips leads on its block, unsubscribe or bounce lists or already in another campaign, and none of those should ever be resent. Check `skipped_count` in the terminal output.
- One email tool per lead. A row whose `pushed_to` names another email tool is refused; `heyreach` never blocks an email push (LinkedIn plus email for the same person is allowed).
- `configure_website_visitors_smartlead` is GetLeads' auto-push to Smartlead. It is not the default here: it has no page filter, no CRM suppression and no approval step, so it would email everyone the pixel identifies.
- Wallet spend is real money. Check `get_wallet_balance` first and report the balance after.
- Secrets stay in `.env`; never print them. The Smartlead call is unverified against `https://api.smartlead.ai/reference`; check the first dry-run payload against it.

## Common mistakes

- Pushing every identified visit instead of the high-intent pages.
- Assuming the export column is called `page`. Read the header first.
- Expecting a named person for every visit outside the US and Canada.
- Writing "saw you on our pricing page" in the email.
- Skipping suppression and emailing an open opportunity or a customer.
- Using the same lead in Smartlead and another email tool.
- Turning on the auto-push because it is quicker, then losing the filter and the approval.
