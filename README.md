# Agentic Outbound Plays

Five outbound workflows ("Plays") that you run from Claude Code with a sentence. Each one turns a list you already have, or a signal the market just gave you, into a short list of real people with verified emails, a reason to write to them, and a draft you approve before anything is sent.

It is built for founders, sales and marketing people who want outbound that works without hiring an engineer, and without paying for a data platform. You bring your own API keys for a handful of data tools; the repo does the plumbing.

## What you get

- **Five Plays**, ordered cold to hot. Cold is a plain list of names. Hot is someone who was on your pricing page an hour ago, or a past customer who just started a new job.
- **Verified emails, not guesses.** A waterfall tries up to four providers in order, stops at the first verified hit, and never invents an address from a name pattern. Anything unverified is kept but flagged, and cannot reach your email tool.
- **A reason to write.** Every Play ends with a first line that names something real: the post they commented on, the round they just raised, the job they just started, the page they just read.
- **A draft, then your approval.** Nothing sends on its own. Each Play ends with a table you look at, and only after you say yes does anything go to Smartlead (email) or HeyReach (LinkedIn).
- **A spend cap on every paid call,** a cache so re-running a list costs nothing, and a dry-run mode that shows the plan before a cent is spent.
- **A suppression step before every push,** so customers, open deals and people you touched recently never get a cold email from you.

## How it works, in one picture

```
your list / a signal
      │
      ▼
 find the person ──► find a verified email ──► drop anyone you must not contact
      │                                               │
      ▼                                               ▼
 write a first line that names the reason ──► a table for you to approve ──► Smartlead / HeyReach
```

Claude Code drives it. You type something like "run Play 4 on my champions file", Claude follows the matching skill in `.claude/skills/`, calls the data tools, runs the small Python scripts in `outbound/`, and shows you the result. The scripts do the parts that must be exact: de-duplication, the waterfall stop rule, scoring, the push with its safety checks. Claude does the parts that need judgement: deciding whether a company fits your ICP, tiering people, writing the first line.

## The five Plays

| Play | Who it reaches | What you put in | What you get out | Typical cost |
|---|---|---|---|---|
| **1 · Email waterfall** | A cold list | A CSV with first name, last name, company domain, LinkedIn URL | The same list with a verified email, which provider found it, and a flag if the email belongs to a namesake at another company | About 3 cents per person found |
| **2 · Signal scoring** | Accounts where something just changed | Your target-account list | Every account scored 0 to 100 and banded: work today, sequence this week, nurture. Newly funded companies in your size band are discovered and added | A few cents per account per signal source |
| **3 · LinkedIn post engagers** | People who commented on or liked a post on your topic | One post URL | The engagers, tiered against your ICP, with verified emails and a first line that references the post | Under 10 cents for a post with 60 engagers, plus a few cents per email |
| **4 · Champion reactivation** | Past customers who just started a new job | A CSV of people you helped before | Only the ones who moved in the last 14 to 45 days, at a company that fits, with their new email and a "congrats on the new role" draft | About 20 cents per person who actually moved; nothing for the others |
| **5 · Website visitors** | Companies that just visited your pricing, demo or case-study pages | Your website, once a tracking pixel is installed | Identified visitors scored against your ICP, with a verified email and copy that fits the page they read (without ever saying you saw them) | 12.5 cents per newly identified person |

Costs are what we measured on real runs in October 2026 with the default providers. Your mileage depends on your lists and your plans with each vendor.

## What you need

| Account | Used for | Free tier? |
|---|---|---|
| [Claude Code](https://claude.com/claude-code) | Runs the Plays | Needs a Claude subscription |
| [GetLeads](https://app.getleads.io) | Emails from LinkedIn URLs, decision makers, company lookups, visitor pixel, HeyReach bridge | Yes, with credits |
| [Deepline](https://code.deepline.com) | One key for LeadMagic, Prospeo, FullEnrich, MillionVerifier, job-change checks, LinkedIn engagers, funding and news events, social search | Yes, with credits |
| [Apify](https://apify.com) | LinkedIn job postings (hiring signal) | Yes |
| [Smartlead](https://smartlead.ai) | Sends the emails you approve | Paid |
| [HeyReach](https://heyreach.io) | Sends the LinkedIn steps you approve | Paid; can also be driven through GetLeads with no key here |

You need [uv](https://docs.astral.sh/uv/) for Python and the Deepline command-line tool installed.

## Setup, five steps

1. Clone the repo and run `uv sync`.
2. Copy `.env.example` to `.env` and paste your keys. Keys live only in that file, which git ignores.
3. Connect GetLeads to Claude Code: open https://app.getleads.io, go to Settings → MCP, and run the `claude mcp add getleads ...` command shown there.
4. Install Deepline: https://code.deepline.com/INSTALL.md
5. Open `CLAUDE.md` and fill in the ICP block: your industries, company size, countries, buyer titles, a few pain phrases, and who to exclude. That block is the only thing you must edit; every Play qualifies people against it.

Then run `uv run python -m outbound.common --selftest`. It prints `OK` when the setup is sound, with no network calls.

## Running your first Play

Start with Play 1 on ten real rows. It is the cheapest Play and it proves the plumbing end to end.

Put ten people in `data/leads.csv` (copy the header from `data/leads.example.csv`), open Claude Code in this folder, and say:

```
Run Play 1 on data/leads.csv. Dry run first, show me the plan and the cost, then wait for my go.
```

Claude shows the planned calls and the estimated spend. Say go, and a minute later you have `out/leads_enriched.csv` with a verified email on most rows and a report telling you which provider found what and what it cost. Re-run the same command and it costs nothing: every call is cached.

From there, the order that works best:

1. **Play 4** next, if you have past customers. It is the warmest list you own and needs the least data.
2. **Play 5** once the pixel is on your site. Small volume, highest reply rate.
3. **Play 2** when you want a weekly ranked list of accounts to work.
4. **Play 3** after your next post that performs.

Every Play has a skill in `.claude/skills/` with the exact steps, and the [Playbook](docs/PLAYBOOK.md) spells them out with commands and a prompt you can paste.

## The safety rules, in plain words

- **Nothing sends without you.** Every Play ends with a table and waits. The push scripts refuse to run until you ask, and they do a dry run by default on day one of Play 5.
- **Only verified emails reach your email tool.** Catch-all and unknown addresses are kept for the LinkedIn track but blocked from Smartlead. An email that belongs to a namesake at another company is flagged and blocked too, because a verifier proves a mailbox exists, not that it is your prospect.
- **No one gets contacted twice.** A shared registry remembers every push. To deliberately re-send to someone, you delete their row.
- **One email tool per person.** LinkedIn plus email for the same person is fine; two email tools is not.
- **Your CRM wins.** Open deals, active sequences, customers and anyone touched in the last 14 days are removed before every push, from a simple CSV export.
- **Spend is capped.** Every paid call is estimated first and refused if it would blow the cap you set. Deepline and Apify enforce their caps on their side; the rest are estimates, and the README of each Play says which is which.
- **Some of this carries platform risk.** Scraping LinkedIn engagers and identifying website visitors have terms-of-service and privacy implications. Keep volumes low, prefer your own and partner posts, and update your privacy policy before the pixel goes live.

## A few words you will meet

- **Waterfall**: trying email providers one after another, cheapest first, stopping at the first verified hit.
- **Verified / catch-all / unknown**: a verifier confirmed the mailbox; the domain accepts all mail so nothing can be confirmed; the verifier could not tell. Only the first is safe to send to.
- **Domain match**: whether the email's domain is the company you expected. "No" usually means the provider found a different person with the same name, or your prospect has moved.
- **ICP**: your ideal customer profile, the block you fill in `CLAUDE.md`.
- **First-party, second-party, third-party signals**: things that happened with you (a visit to your site), with a partner (engagement on their post), or in public (a funding round). Closer signals score higher.
- **Suppression**: removing people you must not contact before anything is sent.

## What is in the repo

```
CLAUDE.md                    your rules: ICP, suppression, sending, spend caps
.claude/skills/play-*/       the five Plays, as Claude Code skills
outbound/                    small Python scripts: waterfall, filter, scoring, Smartlead push, HeyReach push
config/signal_scoring.yaml   weights, freshness windows and bands for Play 2
data/*.example.csv           the column layouts each Play expects
docs/PLAYBOOK.md             every Play step by step, with commands and prompts to paste
out/                         results land here (git-ignored)
.cache/                      cached API responses so re-runs are free (git-ignored; contains emails, delete when done)
```

Each script has a built-in self-check: `uv run python -m outbound.<name> --selftest` prints `OK` with no network and no spend.

MIT licensed. Built by [martechs.io](https://martechs.io).
