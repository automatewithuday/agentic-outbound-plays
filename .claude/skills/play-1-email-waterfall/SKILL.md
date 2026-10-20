---
name: play-1-email-waterfall
description: Use when you have a list of people (name, company domain, LinkedIn URL) and need verified work emails before anything goes into Smartlead
license: MIT
metadata:
  author: automatewithuday
  source: martechs.io
  version: "1.0"
  category: list-building
---

# Play 1 · Email waterfall (cold)

## How to apply this skill

**Inputs**
- `data/leads.csv` with columns `first_name,last_name,company_domain,linkedin_url` (see `data/leads.example.csv`).
- Optional: a per-run spend cap in USD (`--cap-usd`, a total). Default is 15 cents per row after dedupe.

**Compute**
- `outbound/waterfall.py` dedupes (LinkedIn URL, then name + domain), then per batch tries GetLeads, then Deepline `prebuilt/person-to-email-batch`, then (only with `--deep`) FullEnrich. Every candidate is verified (MillionVerifier; BounceBan once if catch-all).
- Stop rule: `verified` keep and stop. `catch_all` keep with status and stop. `unknown` keep with status and stop. `discard` drop the candidate and try the next provider. Nothing left: `not_found`. Emails are never built from a name pattern.

**Report**
- `<out>.report.md`: rows in/after dedupe, % verified / catch_all / unknown / not_found, hits per provider, verifier calls, spend.

## Steps

1. Check balance and fair use: call the GetLeads MCP tool `get_fair_use`. Stop and tell the user if the daily or monthly allowance cannot cover the row count.
2. Plan the run: `uv run python -m outbound.waterfall data/leads.csv --out out/leads_enriched.csv --dry-run`. Show the planned calls and cost. A dry run writes only `<out>.dryrun.csv` / `<out>.dryrun.report.md`, never the real output.
3. Test on the first 10 rows (`head -11 data/leads.csv > data/leads_test.csv`), real run, inspect the output, then continue.
4. Real run in batches: `uv run python -m outbound.waterfall data/leads.csv --out out/leads_enriched.csv --batch 150 [--cap-usd N]`. `/compact` between big runs. Re-runs replay cached calls at $0.
5. Read `out/leads_enriched.csv.report.md`. If not_found is above 30%, say so plainly and ask before adding `--deep`.
6. Split the result: `email_status = verified` is the only set eligible for Smartlead. `catch_all` and `unknown` go to a separate LinkedIn-only track (HeyReach), never Smartlead. `not_found` also goes to the LinkedIn track.
7. Show a table (counts per status and provider, 5 sample rows per status, spend) and wait for explicit approval. Only then push `verified` rows to Smartlead. Nothing sends without approval.

## Prompt to paste

```
Read data/leads.csv (first_name, last_name, company_domain, linkedin_url). Run the Play 1 skill:
check get_fair_use first, then run
uv run python -m outbound.waterfall data/leads.csv --out out/leads_enriched.csv --batch 150 --dry-run
and show me the plan. After I approve, run it for real. It dedupes first, finds emails per row,
stops at the first verified one, and never builds an email from a naming pattern.
Output goes to out/leads_enriched.csv with email, email_status, email_provider, verifier, mx_class, miss_reason.
Report % verified, % catch_all, % unknown, % not found, hits per provider and spend.
Catch-all and unknown go to the LinkedIn-only track, never Smartlead. Show me the table and wait for approval before pushing anything.
```

## Guardrails

- Always `--dry-run` first; a real run needs the user's go-ahead.
- Spend is capped by the ledger; a cap abort keeps every processed row and marks the rest `cap_aborted`. Report it, never loop around the cap.
- Catch-all and unknown never enter a live Smartlead sequence (see `CLAUDE.md` Sending).
- Secrets stay in `.env`; never print them.

## Common mistakes

- Guessing emails from a name pattern (first.last@domain). The script refuses to; do not add it by hand.
- Turning on `--deep` (FullEnrich) by default. It costs more and charges for catch-all results; use it only for the leftover not_found rows.
- Skipping dedupe, so the same person is paid for twice.
- Sending `catch_all` or `unknown` rows to Smartlead because the count looks small.
- Running the full list before looking at the first 10 rows.
