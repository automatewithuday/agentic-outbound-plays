# Agentic Outbound Plays

Five outbound Plays in Claude Code, ordered cold to hot: Play 1 waterfall email finder, Play 2 signal scoring, Play 3 LinkedIn post engagers, Play 4 champion reactivation, Play 5 website visitors. Everything drafts; nothing sends without explicit approval. Skills in `.claude/skills/` read this file and pass values to scripts as CLI flags.

# ICP  (EDIT ME — the only section a new user must change; every Play qualifies against these lines)

- Industries: <e.g. B2B SaaS, fintech>
- Headcount: <e.g. 50-500>
- Countries: <e.g. US, UK, Germany>
- Buyer titles: <e.g. VP Sales, Head of Growth, Head of RevOps>  (Play 3 builds its title regex from this line)
- Pain keywords (Play 2 social intent searches these on X, Reddit, Hacker News, Bluesky): <e.g. "cold email reply rate", "need an SDR">
- Exclude: current customers, competitors, <e.g. agencies, companies under 10 people>

# Suppression

Before any push, remove: open opportunities, active sequences, anyone touched in the last 14 days, current customers.
Source: `data/crm_export.csv` with columns `email,domain,linkedin_url,stage,in_sequence,last_touched,is_customer` (see `data/crm_export.example.csv`). Match on email, linkedin_url or domain. Accepted values: `stage` is `open`, `proposal` or `negotiation` (any case) for an open opportunity; `in_sequence` and `is_customer` are truthy when `true`, `1` or `yes`; `last_touched` is ISO `YYYY-MM-DD` (a malformed date stops the run naming the CSV line).

# Sending

- Unknown and catch-all emails never go into a live sequence.
- Draft everything; send nothing without approval.
- Email from ONE tool only: Smartlead. LinkedIn via HeyReach.
- Copy never mentions a website visit.

# Tools

- GetLeads MCP: plan credits vs wallet cash are separate; run `get_fair_use` before big runs.
- Deepline CLI (`deepline`), Apify, Smartlead.
- HeyReach: through GetLeads (no code) or `outbound/push_heyreach.py` with `HEYREACH_API_KEY`.

# Spend caps  (defaults, EDIT ME)

- Play 1: $0.15/row
- Play 2: $25/run
- Play 3: $10/post
- Play 4: $5/run
- Play 5: $5/day

Pass these as `--cap-usd` (Play 1's is per row: multiply by rows). Always `--dry-run` first. Batches of 100-200 rows; `/compact` between batches.

# Conventions

- Run modules with `uv run python -m outbound.<module>`; never bare python/pip.
- Outputs go in `out/`; cache in `.cache/` (replays at $0).
- Every module supports `--selftest` (prints `OK`).
- Secrets live in `.env` only; never print them.
