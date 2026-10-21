---
name: play-4-champion-reactivation
description: Use when you want to find past champions who changed jobs in the last 14 to 45 days and draft a congrats email to each, every Monday
license: MIT
metadata:
  author: automatewithuday
  source: martechs.io
  version: "1.0"
  category: signals
---

# Play 4 · Champion reactivation (hot)

## How to apply this skill

**Inputs**
- `data/champions.csv` with columns `name,email,linkedin_url,old_company,old_company_domain,role` (see `data/champions.example.csv`). Keep only people you actually helped.
- `CLAUDE.md` for the ICP and the buyer titles. `data/crm_export.csv` for suppression.

**Compute**
- Deepline `prebuilt/job-change-check` checks each LinkedIn profile. It needs `linkedin_url` plus an anchor: `email` or the company domain on record. Cost is 1.96 credits only per `moved` row.
- Output field `job_change.status` is one of `moved | no_change | left_company | unknown | profile_unavailable | no_new_company`. Other fields: `job_change.date`, `job_change.new_company`, `job_change.new_title`, `job_change.company_domain`.
- `outbound/filter.py` keeps only movers whose move is 14 to 45 days old and whose new company differs from the old one.
- A move younger than 14 days is too early, older than 45 days has gone cold. 91% of past champions have not come back on their own three months into a new job (UserGems 2023), and new executives convert 2.5x better in their first three months.

**Report**
- Counts per `job_change.status`, movers kept and dropped per rule, ICP verdicts, drafts table, credits spent.

## Steps

1. Check the input: `data/champions.csv` exists, every row has `linkedin_url` and `email` or `old_company_domain`. Remove anyone you did not clearly help.
2. Run the check in three commands. Input column names depend on the play, so first run `deepline plays describe prebuilt/job-change-check` and read the required input columns and output fields. Then test on 5 rows (`head -6 data/champions.csv > data/champions_test.csv`) and run, with a credit ceiling because `--dry-run` on a named play only shows the execution plan:
   - This play does NOT accept a `columns` mapping (verified: "Unknown input key ... columns"). Write a copy of the CSV with the play's own header names first: `linkedin_url`, `company_domain` (= the company you have on record, i.e. `old_company_domain`), `full_name`, `email`. One line does it: `uv run python -c "from outbound.common import *; r=read_csv('data/champions.csv'); write_csv('out/champions_in.csv',[{'linkedin_url':x['linkedin_url'],'company_domain':x['old_company_domain'],'full_name':x['name'],'work_email':x['email'],'old_company':x['old_company'],'role':x['role']} for x in r])"`. Use the `work_email` header, not `email`: a generic `email` whose domain differs from `company_domain` is treated as personal and the provider rejects it ("Bad email ... is a professional email", observed live).
   - `deepline plays run prebuilt/job-change-check --csv out/champions_in.csv --max-credits N --run-id-file out/champions_run.json` (the `--run-id-file` destination must not already exist, so use a fresh name per run).
   - `deepline runs export <run-id> --out out/champions_checked.csv` with the run id from `out/champions_run.json` (optionally `--dataset <selector>`; see `deepline runs export -h`).
   - Check the headers include `job_change.status` and `job_change.date` before step 3. Then repeat on the full `data/champions.csv`.
3. Filter to fresh movers. The export stores the result as one JSON cell named `job_change`, so expand it first with `--json-col`: `uv run python -m outbound.filter out/champions_checked.csv --out out/movers.csv --json-col job_change --keep-regex 'job_change.status=^moved$' --days job_change.date=14..45 --neq job_change.new_company,old_company`. Dropped rows land in `out/movers.csv.dropped.csv` with `drop_reason`. Verified live: a January move was dropped by the 14-45 window, as intended.
4. ICP check per mover: GetLeads MCP `lookup_company` on `job_change.company_domain`. Judge fit against the ICP in `CLAUDE.md`. Drop non-ICP with a one-line reason.
5. New email: `uv run python -m outbound.waterfall out/movers.csv --out out/movers_enriched.csv --dry-run`, then for real after the user agrees to the plan, passing `--cap-usd` from the Spend caps section of `CLAUDE.md`. The waterfall needs `first_name,last_name,company_domain,linkedin_url`: map `name` to first and last, and `job_change.company_domain` to `company_domain`. If a mover's `role` is not `buyer`, also call GetLeads MCP `lookup_decision_makers(domain, limit 5)` on the new domain, filter by the titles in `CLAUDE.md`, and add the budget owner as a second contact.
6. Suppress: `uv run python -m outbound.filter out/movers_enriched.csv --out out/movers_final.csv --suppress data/crm_export.csv`. Open opportunities, sequences, customers and recent touches drop out.
7. Draft one email per champion. The opening line is exactly `Congrats on {{new_company}}. Remember when we helped you at {{old_company}}?` Then two short lines. No account details, no usage data, no contract terms.
8. Show the drafts table (name, new company, new title, move date, ICP reason, email, draft) and wait for explicit approval. Send nothing. After approval, email goes through Smartlead (`push_smartlead.py`; every push is recorded in `out/pushed_registry.csv`, and to deliberately re-push a lead, delete its row from `out/pushed_registry.csv`) and LinkedIn through GetLeads MCP `send_contacts_to_heyreach`.

## Prompt to paste

```
Run the Play 4 skill every Monday. Read data/champions.csv (name, email, linkedin_url, old_company, old_company_domain, role)
and CLAUDE.md. Check each champion with deepline plays run prebuilt/job-change-check (test 5 rows first, always --max-credits).
Keep only status moved, with a move date 14 to 45 days old and a new company that differs from the old one:
uv run python -m outbound.filter ... --keep-regex 'job_change.status=^moved$' --days job_change.date=14..45 --neq job_change.new_company,old_company
For each mover run lookup_company on the new domain and drop anyone outside the ICP in CLAUDE.md, with a one-line reason.
Find the champion's new email with uv run python -m outbound.waterfall. If the champion is not the buyer, use lookup_decision_makers
(limit 5) and add the budget owner. Suppress against data/crm_export.csv.
Draft one email per champion that opens exactly: Congrats on {{new_company}}. Remember when we helped you at {{old_company}}?
then two short lines. No account details, no usage data, no contract terms. Only people we actually helped.
Show me every draft in a table and send nothing until I approve.
```

## Guardrails

- Nothing sends without approval. Show every draft first.
- Spend is capped: always `--max-credits` on the Deepline call (`--dry-run` is not supported for prebuilt plays) and test on 5 rows first. Report the credits used; never loop around a cap.
- Never put account details, usage data, pricing or contract terms in a draft.
- Only champions you actually helped. A bad past experience stays out of the CSV.
- Suppression runs last, after the new email is known, so a champion already in a sequence is never double-contacted.
- Secrets stay in `.env`; never print them.

## Common mistakes

- Acting on moves younger than 14 days or older than 45 days.
- Skipping the `--neq` rule and congratulating someone who "moved" to the same company.
- Sending to non-ICP new employers because the champion is friendly.
- Treating `unknown` or `profile_unavailable` as moved. Only `moved` is a signal.
- Reusing the old company's email address instead of finding the new one.
- Writing the draft from the deal file (price, seats, usage) instead of the shared history.
