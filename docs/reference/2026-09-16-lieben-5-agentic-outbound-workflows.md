# Michel Lieben — Here's how to Generate Leads With 5 Agentic Outbound Workflows in Claude Code
Source: https://x.com/MichLieben/status/2100264228947107996
Captured 21 Oct 2026; author Michel Lieben, CEO ColdIQ; this repo's Play 1-5 map to the article's Workflow 1-5

## Appendix A — Article text (captured 21 Oct 2026 from logged-in Chrome)

Source: https://x.com/MichLieben/status/2100264228947107996 — Michel Lieben (@MichLieben), CEO ColdIQ. "Here's how to Generate Leads With 5 Agentic Outbound Workflows in Claude Code". 4,085 views at capture. The article says "Workflow"; our repo says "Play". The article's ColdIQ / Instantly / lemlist / Trigify references map to GetLeads+Deepline+Apify / Smartlead / HeyReach / GetLeads monitoring in the plan above. Save to `docs/reference/2026-09-16-lieben-5-agentic-outbound-workflows.md` in Phase 0.

### Framework
Funnel behind his agency booked 100+ meetings/month for 3 years. Prospects who had seen them 3+ times converted 2-3x better on identical copy. Five workflows by audience temperature:
- Cold: never heard of you — W1 Waterfall email finder
- Warm: buying signals, LinkedIn post engagers — W2 Signal-based list builder, W3 LinkedIn engagement → outreach
- Hot: past champions who changed jobs, website visitors — W4 Job-change champion reactivation, W5 Website visitor → email sequence
All run from Claude Code through the ColdIQ MCP. "The warmer the audience, the less your first email has to explain."

### Setup
1. `claude mcp add coldiq --scope user -e COLDIQ_API_KEY=<key> -- npx -y @coldiq/mcp@latest`
2. `claude mcp list` → ✔ Connected; test by asking for ONE ICP company before a full list.
3. CLAUDE.md (<200 lines):
```
# ICP
- Industries: B2B SaaS, fintech
- Headcount: 50-500
- Countries: US, UK, Germany
- Buyer titles: VP Sales, Head of Growth, Head of RevOps
- Exclude: current customers, competitors, agencies
# Suppression
- Remove open opportunities, active sequences and anyone touched in the last 14 days
# Sending
- Unknown and catch-all emails never go into a live sequence
- Draft everything, send nothing without my approval
```
Keep approvals on for anything that sends.

### W1 — Waterfall email finder (cold)
Job: stop settling for 40% email coverage; 80% doubles reachable leads. Coverage is the ceiling for W2-W5.
- Input CSV: first_name, last_name, company_domain, linkedin_url. Dedupe first.
- Providers: FullEnrich (20+ vendor waterfall) | own: Prospeo, GetLeads, LeadMagic, Apollo | ColdIQ find_email default Findymail → LeadMagic → Prospeo → Apollo, pin Limadata/Icypeas/Wiza. Hand-built: cheapest → priciest.
- Stop rule: verified → keep & stop; catch-all/risky/unknown → store with status, never live; not found → next provider. Map each vendor's status labels before chaining.
- Prompt: read leads.csv, dedupe, batches of 150, find_email per row, stop at first verified, never build email from naming pattern, write leads_enriched.csv (+email, status, provider), report % verified / % catch-all-unknown / % not found / hits per provider.
- Batches 100-200 rows, /compact between. Bounces < 2%.
- ColdIQ charges only on found valid email (Sep 2026); FullEnrich charges for catch-all.

### W2 — Signal-based list builder (warm)
Recorded run: 25 raw PredictLeads funding events → 7 real → buyers at 5 cos → waterfall 5/5 found, 4 verified, 91 credits. Rules: closer signal = higher intent; more signals = higher intent.
1. Map full TAM (search_companies, find_people vs CLAUDE.md). Signals only rank a list.
2. First-party (8): own-post LinkedIn engagement, nurture opens/clicks/replies, product usage, gated content, call transcripts (Claap/lemlist), CRM closed-lost & stalled, meeting forms, website visitors (W5).
3. Second-party (5): G2 Buyer Intent, champion tracking (W4), team/partner post engagement (W3), Crossbeam overlap, LinkedIn Campaign Manager Companies view.
4. Third-party (11): lookalikes, funding (PredictLeads / Explorium), Bombora search trends, technographics, LinkedIn Ad Library, person data, custom scraping, job openings, web changes, news events, firmographics. Freshness: job change 14-45d, funding 2-4wk, hiring 1-2wk.
5. Score:
```yaml
# signal_scoring.yaml
weights: {first_party: 40, second_party: 25, third_party: 10}
freshness: {job_change_days: 14-45, funding_weeks: 2-4, hiring_weeks: 1-2}
bands: {work_today: 80+, sequence_this_week: 40-79, nurture: below 40}
```
6. Prompt: per account in tam.csv call find_signals (funding, hiring, job_change, news); keep inside freshness; verify real, drop dupes; add first-party from crm_export.csv and /transcripts; tag ring; score; accounts_scored.csv (score, band, signals); for 80+ find 2 buyers by CLAUDE.md titles.
Gong Labs 2023: emails referencing buyer-journey actions ≈3x replies/meetings.

### W3 — LinkedIn engagement → outreach (warm)
Two context layers per message: company event + content engaged with. Likes/comments pullable; profile views manual.
1. Monitor with Limadata/Trigify; pull with extract_post_engagement (expires 12h → enrich same run).
2. Dedupe. 3. enrich_person / enrich_company.
4. Tier vs CLAUDE.md + post + company news: T1 ICP + buyer title + commented or multi-post; T2 ICP + buyer/influencer; T3 ICP other; Out.
5. CRM: remove open opps, active sequences, touched < 14d; T1 owned by a rep → alert rep.
6. Waterfall (W1 rule). 7. T1 multichannel lemlist (human reads post first); T2/T3 Instantly. Post topic decides first line.
Prompt: post_url → extract → dedupe/enrich → tier → suppress → find_email → first line from (post topic + one recent company event) → show list+drafts → after approval T1 lemlist <id>, T2/3 Instantly <id>.
Trade-off: LinkedIn UA prohibits scraping/automation; restriction risk.

### W4 — Job-change champion reactivation (hot)
UserGems 2023: 91% of past champions hadn't returned on their own 3 months into a new job. Pew: ~2.5% of US workers switch employers monthly.
1. Export champions (folk recommended): name, email, linkedin_url, old company, deal role. Keep only good experiences.
2. Job-change signals via ColdIQ (GET /v1/signalbase/job-change-signals, personLinkedinUrl), match on URL. PredictLeads news for exec hires. Act only on moves 14-45 days old.
3. enrich_company new employer, score vs CLAUDE.md, drop non-ICP.
4. Champion's new email via waterfall; buyer via find_people if champion lacks budget.
5. Email: "Congrats on [NewCo]. Remember when we helped you at [OldCo]?" Only to people you actually helped; no account details.
Skill `.claude/skills/champion-tracker/SKILL.md`, `/champion-tracker` every Monday; show every draft, send nothing.
UserGems: new execs convert 2.5x better in first 3 months.

### W5 — Website visitor → email sequence (hot)
A visit gives timing, not an opener; stack a second signal. Copy never mentions the visit.
01 Identify: ColdIQ Visitor ID (setup_website_visitors → pixel per domain). Alternatives Knock2.ai, Warm AI. Update privacy policy/consent first.
02 Enrich company, score vs CLAUDE.md; keep intent pages (pricing, demo, case studies, comparisons); remove customers & open opps. Dry-run day 1.
03 find_people with buyer titles. 04 Waterfall.
05 Push to Instantly (email) + lemlist (LinkedIn visit → invite → message); each lead gets email from ONE tool. Pass page_topic custom variable:
```
POST https://api.instantly.ai/api/v2/leads  Authorization: Bearer <KEY>
{"campaign":"<uuid>","email":"jane@acme.com","first_name":"Jane","company_name":"Acme","custom_variables":{"page_topic":"pricing for multi-seat teams"}}
```
HockeyStack: pricing pages 3.8% form-fill vs 1.1% site-wide.

### Run all 5 this week
Build order: MCP + CLAUDE.md → W1 → W4 → W5 → W2 → W3.
Rhythm: W1 per new list; W2 weekly; W3 within a day of a performing post; W4 Mondays; W5 daily.
Guardrails: first 100 contacts then inspect; batches 100-200 with /compact; approvals on for anything that sends.
Disclosure: ColdIQ is the author's company; free 300 credits.
