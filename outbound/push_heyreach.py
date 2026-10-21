"""Play 3/4/5: push LinkedIn leads to HeyReach (direct REST), after the user's approval.

Contract verified 21 Oct 2026 against HeyReach's public API as encoded by the bcharleson/heyreach-cli project (built from HeyReach's
Postman collection) — no official HTML reference is fetchable:
  base   https://api.heyreach.io/api/public        header X-API-KEY        300 requests/minute
  list     POST /list/AddLeadsToListV2             {"listId": N, "leads": [lead, ...]}                        <= 100 per call
  campaign POST /campaign/AddLeadsToCampaignV2     {"campaignId": N, "accountLeadPairs": [{"lead": lead, "linkedInAccountId": N?}, ...],
                                                     "resumePausedCampaign": bool?, "resumeFinishedCampaign": bool?}  <= 100 per call
  lead = {"profileUrl" (required), "firstName", "lastName", "companyName", "position"}
  free check: GET /auth/CheckApiKey
Default route is a LIST: nothing is messaged until that list is attached to a campaign you start yourself. Adding straight to an
IN_PROGRESS campaign starts outreach. The response's count fields are not documented; the first batch's body is printed as-is.
A row's `pushed_to` naming heyreach, or a LinkedIn URL already in out/pushed_registry_heyreach.csv, is refused (no double sends).
The alternative route is GetLeads MCP `send_contacts_to_heyreach` (free; needs the HeyReach key connected inside GetLeads)."""
import argparse, contextlib, io, json, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx

from outbound import common as c

BASE = "https://api.heyreach.io/api/public"
REGISTRY = c.ROOT / "out" / "pushed_registry_heyreach.csv"
REG_COLS = ["linkedin_url", "pushed_to", "destination", "pushed_at", "source_file"]
BATCH = 100  # HeyReach's max leads per call


def post(path, payload, api_key):
    r = httpx.post(BASE + path, json=payload, headers={"X-API-KEY": api_key}, timeout=60)
    if r.status_code >= 400:  # the key is a header, never in the URL; keep the error short and key-free anyway
        raise RuntimeError(f"heyreach: HTTP {r.status_code} on {path}: {r.text[:300]}")
    return r.json() if r.text.strip() else {}


def _lead(r):
    lead = {"profileUrl": c._li(r["linkedin_url"]) and r["linkedin_url"].strip()}
    for src, dst in (("first_name", "firstName"), ("last_name", "lastName"), ("company_name", "companyName"), ("position", "position"), ("title", "position")):
        if r.get(src) and dst not in lead:
            lead[dst] = r[src]
    return lead


def push(rows, *, list_id=None, campaign_id=None, account_id=None, resume_paused=False, dry_run=False, api_key=None,
         registry=REGISTRY, source_file=""):
    """Return (pushed_rows, refused). Exactly one of list_id / campaign_id. Registry (by normalized LinkedIn URL) is read on every
    run, dry or real, and written as a union after each successful batch."""
    assert (list_id is None) != (campaign_id is None), "exactly one of list_id / campaign_id"
    prior = c.read_csv(registry) if registry and Path(registry).exists() else []
    done = {c._li(r.get("linkedin_url")) for r in prior}
    ok, refused = [], []
    for r in rows:
        li = c._li(r.get("linkedin_url"))
        tool = (r.get("pushed_to") or "").strip().lower()
        if not li:
            refused.append((r, "no_linkedin_url"))
        elif "heyreach" in tool or li in done:
            refused.append((r, "already_pushed:heyreach"))  # delete its registry row to re-push on purpose
        else:
            ok.append(r)
            done.add(li)  # the same profile twice in one file (case/trailing-slash variants) is pushed once
    dest = f"list:{list_id}" if list_id is not None else f"campaign:{campaign_id}"
    pushed, now = [], datetime.now(timezone.utc).isoformat(timespec="seconds")
    for i, chunk in enumerate(c.batches(ok, BATCH)):
        if list_id is not None:
            path, payload = "/list/AddLeadsToListV2", {"listId": int(list_id), "leads": [_lead(r) for r in chunk]}
        else:
            pairs = [{"lead": _lead(r), **({"linkedInAccountId": int(account_id)} if account_id else {})} for r in chunk]
            payload = {"campaignId": int(campaign_id), "accountLeadPairs": pairs}
            if resume_paused:
                payload["resumePausedCampaign"] = True
            path = "/campaign/AddLeadsToCampaignV2"
        c.spend(0.0, "heyreach")
        if dry_run:
            if i == 0:
                print(f"first payload (POST {BASE}{path}, X-API-KEY: <hidden>):\n" + json.dumps(payload, indent=2))
        else:
            try:
                body = post(path, payload, api_key or c.env("HEYREACH_API_KEY"))
            except httpx.RequestError as e:
                raise RuntimeError(f"heyreach: {type(e).__name__} on {path}; {len(pushed)} rows pushed this run") from None
            if i == 0:
                print(f"heyreach response (batch 1): {json.dumps(body)[:300]}")
        new = [{**r, "pushed_to": "heyreach", "destination": dest, "pushed_at": now, "source_file": source_file} for r in chunk]
        pushed += new
        if registry and not dry_run:
            prior = c.dedupe(prior + new, ["linkedin_url"])
            c.write_csv(registry, prior, REG_COLS)
    return pushed, refused


def main(argv=None):
    p = c.cli_common(argparse.ArgumentParser(description=__doc__))
    p.add_argument("leads", nargs="?")
    p.add_argument("--list-id", type=int, help="HeyReach list to add to (safe: nothing sends until a campaign uses the list)")
    p.add_argument("--campaign-id", type=int, help="HeyReach campaign to add to (an IN_PROGRESS campaign starts messaging these leads)")
    p.add_argument("--linkedin-account-id", type=int, help="sender account for campaign pairs (optional; HeyReach assigns otherwise)")
    p.add_argument("--resume-paused", action="store_true", help="campaign route only: set resumePausedCampaign=true")
    a = p.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.leads or (a.list_id is None) == (a.campaign_id is None):
        p.error("leads CSV and exactly one of --list-id / --campaign-id are required")
    c.apply_cli(a)
    rows = c.read_csv(a.leads)
    with contextlib.ExitStack():
        pushed, refused = push(rows, list_id=a.list_id, campaign_id=a.campaign_id, account_id=a.linkedin_account_id, resume_paused=a.resume_paused,
                               dry_run=a.dry_run, registry=a.out or REGISTRY, source_file=a.leads)
    for r, why in refused:
        print(f"refused {r.get('linkedin_url') or '<blank>'}: {why}")
    print(f"{'would push' if a.dry_run else 'pushed'} {len(pushed)} of {len(rows)} rows in {-(-len(pushed) // BATCH)} request(s); refused {len(refused)}; {c.report()}")
    return 0


def selftest():
    global post
    real_post, calls = post, []
    post = lambda path, payload, api_key: calls.append((path, payload, api_key)) or {"ok": True}
    try:
        c._reset()
        rows = [{"linkedin_url": f"https://www.linkedin.com/in/p{i}/", "first_name": f"F{i}", "last_name": "L", "position": "CRO", "company_name": "Co"} for i in range(130)]
        rows += [{"linkedin_url": "", "first_name": "x"}, {"linkedin_url": "https://www.linkedin.com/in/done/", "pushed_to": "smartlead,heyreach"},
                 {"linkedin_url": "https://www.linkedin.com/in/P0/"}]  # same person as p0 in a different case form -> pushed once
        d = Path(tempfile.mkdtemp()); reg = str(d / "r.csv"); buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            pushed, refused = push(rows, list_id=456, api_key="K", registry=reg)
        assert sorted(w for _, w in refused) == ["already_pushed:heyreach", "already_pushed:heyreach", "no_linkedin_url"]
        assert len(pushed) == 130 and len(calls) == 2 and [len(p["leads"]) for _, p, _ in calls] == [100, 30]
        assert calls[0][0] == "/list/AddLeadsToListV2" and calls[0][1]["listId"] == 456 and calls[0][2] == "K"
        lead = calls[0][1]["leads"][0]
        assert lead == {"profileUrl": "https://www.linkedin.com/in/p0/", "firstName": "F0", "lastName": "L", "companyName": "Co", "position": "CRO"}
        assert len(c.read_csv(reg)) == 130 and c.read_csv(reg)[0]["destination"] == "list:456"
        # second run: everything already in the registry is refused, nothing posted; registry never shrinks
        calls.clear()
        with contextlib.redirect_stdout(io.StringIO()):
            pushed2, refused2 = push(rows[:5], list_id=456, api_key="K", registry=reg)
        assert not pushed2 and not calls and all(w == "already_pushed:heyreach" for _, w in refused2) and len(c.read_csv(reg)) == 130
        # campaign route: accountLeadPairs with optional sender id and resume flag; dry run posts nothing and prints the payload
        calls.clear(); buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            pushed3, _ = push(rows[:2], campaign_id=7, account_id=99, resume_paused=True, api_key="K", registry=None)
        pl = calls[0][1]
        assert calls[0][0] == "/campaign/AddLeadsToCampaignV2" and pl["campaignId"] == 7 and pl["resumePausedCampaign"] is True
        assert pl["accountLeadPairs"][0]["linkedInAccountId"] == 99 and pl["accountLeadPairs"][0]["lead"]["profileUrl"].endswith("/in/p0/")
        calls.clear(); buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            pushed4, _ = push(rows[:2], campaign_id=7, api_key="K", registry=None, dry_run=True)
        assert not calls and len(pushed4) == 2 and "X-API-KEY: <hidden>" in buf.getvalue() and '"accountLeadPairs"' in buf.getvalue()
        # HTTP error text never carries the key
        post = real_post
        import outbound.push_heyreach as m
        orig = httpx.post
        class R: status_code, text = 401, "Unauthorized"
        httpx.post = lambda *a, **k: R()
        try:
            try:
                m.post("/list/AddLeadsToListV2", {}, "SECRETKEY"); raise AssertionError("no error raised")
            except RuntimeError as e:
                assert "SECRETKEY" not in str(e) and "HTTP 401" in str(e)
        finally:
            httpx.post = orig
    finally:
        post = real_post
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
