"""Push a leads CSV into a Smartlead campaign. Verified emails only, one email tool per lead.

Every real push is recorded by email in ONE shared registry, out/pushed_registry.csv (email,pushed_to,campaign_id,pushed_at,source_file),
read at the start of every run (real and dry) so no lead is emailed twice, from any input file. To deliberately re-push a lead,
delete its row from out/pushed_registry.csv.
A row's own `pushed_to` column: `smartlead` or any OTHER email tool is refused; `heyreach` (LinkedIn) never blocks an email push,
so LinkedIn plus email for the same person is allowed. --out overrides the registry path (used by the selftest).
A response that reports fewer accepted leads than sent stops the run with a non-zero exit and is NOT recorded."""
import argparse, contextlib, io, json, os, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx

from outbound import common as c

URL = "https://server.smartlead.ai/api/v1/campaigns/{id}/leads"  # from the brief; not verified against api.smartlead.ai/reference
REGISTRY = c.ROOT / "out" / "pushed_registry.csv"
REG_COLS = ["email", "pushed_to", "campaign_id", "pushed_at", "source_file"]
BATCH = 100  # Smartlead's max leads per request
SETTINGS = {"ignore_global_block_list": False, "ignore_unsubscribe_list": False, "ignore_duplicate_leads_in_other_campaign": False}


def post(url, payload, params=None):
    r = httpx.post(url, json=payload, params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def _ints(body, key=""):
    """Yield (name, int) for upload_count / total_leads anywhere in a JSON body; every other field is ignored."""
    if isinstance(body, dict):
        for k, v in body.items():
            yield from _ints(v, str(k).lower())
    elif isinstance(body, int) and not isinstance(body, bool) and key in ("upload_count", "total_leads"):
        yield key, body


def _lead(r, custom):
    return {"email": r["email"].strip(), "first_name": r.get("first_name", ""), "last_name": r.get("last_name", ""),
            "company_name": r.get("company_name") or r.get("company", ""),
            "custom_fields": {k: r.get(k, "") for k in custom}}


def push(rows, campaign_id, custom=(), allowed=("verified",), dry_run=False, api_key=None, registry=REGISTRY, source_file=""):
    """Return (pushed_rows, refused) where refused is [(row, reason)]. A failed batch, or a response reporting fewer accepted
    than sent, raises RuntimeError (no URL or key in it) and that batch is not recorded. `registry` accumulates every pushed
    email across runs and input files; its emails are skipped (read in dry runs too)."""
    ok, refused = [], []
    prior = c.read_csv(registry) if registry and Path(registry).exists() else []
    done = {(r.get("email") or "").strip().lower() for r in prior}
    for r in rows:
        tool = (r.get("pushed_to") or "").strip().lower()
        if not (r.get("email") or "").strip():
            refused.append((r, "no_email"))
        elif (r.get("email_status") or "").strip().lower() not in allowed:
            refused.append((r, f"status_{r.get('email_status') or 'missing'}"))
        elif tool == "smartlead" or r["email"].strip().lower() in done:
            refused.append((r, "already_pushed:smartlead"))  # any campaign: no double sends; delete its registry row to re-push on purpose
        elif tool and tool != "heyreach":  # heyreach is LinkedIn: never blocks an email push
            refused.append((r, f"already_in_{tool}"))
        else:
            ok.append(r)
    if n := sum(w == "already_pushed:smartlead" for _, w in refused):
        print(f"skipped {n} already-pushed rows (pushed_to column or {registry})")
    pushed, url, now = [], URL.format(id=campaign_id), datetime.now(timezone.utc).isoformat(timespec="seconds")
    for i, chunk in enumerate(c.batches(ok, BATCH)):
        payload = {"lead_list": [_lead(r, custom) for r in chunk], "settings": SETTINGS}
        c.spend(0.0, "smartlead")  # free per push; ledger keeps the call count
        if dry_run:
            if i == 0:
                print(f"first payload (POST {url}?api_key=<hidden>):\n" + json.dumps(payload, indent=2))
        else:
            try:
                body = post(url, payload, {"api_key": api_key or c.env("SMARTLEAD_API_KEY")})  # params, so errors never carry the key
            except httpx.HTTPStatusError as e:
                raise RuntimeError(f"smartlead: HTTP {e.response.status_code} for campaign {campaign_id}: {e.response.text[:300]}; {len(pushed)} rows pushed this run") from None
            except httpx.RequestError as e:
                raise RuntimeError(f"smartlead: {type(e).__name__} for campaign {campaign_id}; {len(pushed)} rows pushed this run") from None
            if i == 0:
                print(f"smartlead response (batch 1): {json.dumps(body)[:300]}")
            counts = list(_ints(body))
            if not counts:
                print("no upload_count in response; cannot verify accepted count")
            short = [(k, v) for k, v in counts if v < len(chunk)]
            if short:
                print(f"WARN accepted {short[0][1]} < sent {len(chunk)} ({short[0][0]})")
                raise RuntimeError(f"smartlead: batch {i + 1} (campaign {campaign_id}) accepted {short[0][1]} < sent {len(chunk)}; "
                                   f"batch NOT recorded as pushed; inspect the campaign; {len(pushed)} rows pushed this run")
        new = [{**r, "pushed_to": "smartlead", "campaign_id": campaign_id, "pushed_at": now, "source_file": source_file} for r in chunk]
        pushed += new
        if registry and not dry_run:
            prior = c.dedupe(prior + new, ["email"])  # union by email, never shrinks; a later failed batch keeps what went out
            c.write_csv(registry, prior, REG_COLS)
    return pushed, refused


def main():
    p = c.cli_common(argparse.ArgumentParser(description=__doc__))
    p.add_argument("leads", nargs="?")
    p.add_argument("--campaign-id")
    p.add_argument("--custom", default="", help="comma list of CSV columns sent as custom_fields, e.g. first_line,page_topic")
    p.add_argument("--only-status", default="verified", help="comma list of email_status values to push (default verified)")
    p.add_argument("--allow-status", default="", help="extra statuses to allow, e.g. unknown; never catch_all by default")
    a = p.parse_args()
    if a.selftest:
        return selftest()
    if not (a.leads and a.campaign_id):
        p.error("LEADS.csv and --campaign-id are required")
    c.apply_cli(a)
    split = lambda s: [x.strip().lower() for x in s.split(",") if x.strip()]
    rows = c.read_csv(a.leads)
    custom = [x.strip() for x in a.custom.split(",") if x.strip()]
    out = a.out or str(REGISTRY)
    try:
        pushed, refused = push(rows, a.campaign_id, custom, split(a.only_status) + split(a.allow_status), a.dry_run, registry=out, source_file=a.leads)
    except RuntimeError as e:
        sys.exit(f"{e}\nstopped mid-push; earlier batches are recorded in {out}; inspect before re-running (the same command skips them)")
    for r, why in refused:
        print(f"refused {r.get('email') or '<blank>'}: {why}")
    print(f"{'would push' if a.dry_run else 'pushed'} {len(pushed)} of {len(rows)} rows in {-(-len(pushed) // BATCH)} request(s); refused {len(refused)}; {c.report()}")
    if pushed and not a.dry_run:
        print(f"wrote {out}")


def selftest():
    calls = []
    os.environ.setdefault("SMARTLEAD_API_KEY", "K")
    global post
    real, post = post, lambda url, payload, params=None: calls.append((url, payload, params)) or {"ok": True}
    try:
        c._reset()
        rows = [{"email": f"p{i}@x.com", "first_name": "A", "last_name": "B", "company_name": "X", "email_status": "verified",
                 "page_topic": f"t{i}", "junk": "no"} for i in range(250)]
        rows += [{"email": "c@x.com", "email_status": "catch_all"}, {"email": "u@x.com", "email_status": "unknown"},
                 {"email": "h@x.com", "email_status": "verified", "pushed_to": "heyreach"},
                 {"email": "s@x.com", "email_status": "verified", "pushed_to": "smartlead"}, {"email": "", "email_status": "verified"},
                 {"email": "o@x.com", "email_status": "verified", "pushed_to": "otheremailtool"}]
        pushed, refused = push(rows, "42", ["page_topic"], ["verified"], api_key="K", registry=None)
        assert [len(p["lead_list"]) for _, p, _ in calls] == [100, 100, 51]  # BATCH enforced
        assert calls[0][0] == "https://server.smartlead.ai/api/v1/campaigns/42/leads" and calls[0][2] == {"api_key": "K"}
        assert calls[0][1]["lead_list"][3]["custom_fields"] == {"page_topic": "t3"} and calls[0][1]["settings"] == SETTINGS
        assert calls[0][1]["lead_list"][0]["company_name"] == "X"
        assert sorted(w for _, w in refused) == ["already_in_otheremailtool", "already_pushed:smartlead", "no_email", "status_catch_all", "status_unknown"]
        assert len(pushed) == 251 and "h@x.com" in [r["email"] for r in pushed]  # heyreach never blocks email
        assert pushed[0]["pushed_to"] == "smartlead" and pushed[0]["campaign_id"] == "42" and pushed[0]["pushed_at"]
        # accepted-count check: only upload_count / total_leads count; other fields never stop a push
        real_post = post
        for body, ok, note in (({"ok": True, "upload_count": 99}, False, False),
                               ({"ok": True, "upload_count": 100, "bounce_count": 0, "skipped_count": 0}, True, False),
                               ({"ok": True}, True, True)):
            post = lambda url, payload, params=None, body=body: body; c._reset(); buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    push(rows[:100], "42", api_key="K", registry=None)
                assert ok, body
            except RuntimeError:
                assert not ok, body
            assert ("no upload_count in response; cannot verify accepted count" in buf.getvalue()) == note, body
        post = real_post; calls.clear(); c._reset()
        # --allow-status lets unknown through, still not catch_all
        calls.clear(); c._reset()
        pushed, refused = push(rows[250:], "42", allowed=["verified", "unknown"], api_key="K", registry=None)
        assert [r["email"] for r in pushed] == ["u@x.com", "h@x.com"] and len(calls) == 1
        # errors carry no key; partial failure keeps batch 1 in the pushed file and exits non-zero
        def boom(url, payload, params=None):
            calls.append(1)
            if len(calls) == 2:
                req = httpx.Request("POST", url + "?api_key=SECRET")
                raise httpx.HTTPStatusError("400 for url " + str(req.url), request=req, response=httpx.Response(400, text="bad", request=req))
        d = Path(tempfile.mkdtemp()); src = d / "f.csv"; c.write_csv(src, rows[:250])
        calls.clear(); c._reset(); post = boom
        try:
            push(rows[:250], "42", api_key="SECRET", registry=str(d / "o.csv")); raise AssertionError("no raise")
        except RuntimeError as e:
            assert "SECRET" not in str(e) and "HTTP 400" in str(e) and "campaign 42" in str(e), str(e)
        assert len(c.read_csv(d / "o.csv")) == 100
        reg = str(d / "reg.csv"); sys.argv = ["x", str(src), "--campaign-id", "7", "--out", reg]; calls.clear(); c._reset()
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                main()
            raise AssertionError("no exit")
        except SystemExit as e:
            assert e.code != 0 and "100 rows" in str(e.code) and "SECRET" not in str(e.code)
        assert len(c.read_csv(reg)) == 100 and c.read_csv(reg)[0]["source_file"] == str(src) and list(c.read_csv(reg)[0]) == REG_COLS
        post = lambda url, payload, params=None: calls.append((url, payload, params)) or {"ok": True}
        calls.clear(); c._reset()  # run 2, same input: only the remaining 150 are sent, file is the union
        with contextlib.redirect_stdout(io.StringIO()):
            main()
        assert [len(p["lead_list"]) for _, p, _ in calls] == [100, 50]
        got = [r["email"] for r in c.read_csv(reg)]
        assert len(got) == 250 == len(set(got)) and got[:100] == [f"p{i}@x.com" for i in range(100)]
        # refusal via shared registry: another input file with the same email is refused; deleting the registry row re-allows it
        calls.clear(); c._reset()
        with contextlib.redirect_stdout(io.StringIO()):
            pushed, refused = push([{"email": "p3@x.com", "email_status": "verified"}], "9", registry=reg)
        assert not pushed and refused[0][1] == "already_pushed:smartlead" and not calls
        c.write_csv(reg, [r for r in c.read_csv(reg) if r["email"] != "p3@x.com"], REG_COLS)
        with contextlib.redirect_stdout(io.StringIO()):
            pushed, _ = push([{"email": "p3@x.com", "email_status": "verified"}], "9", registry=reg)
        assert len(pushed) == 1
        # short response: 99 accepted of 100 sent -> WARN, non-zero, batch not recorded
        post = lambda url, payload, params=None: {"ok": True, "upload_count": 99}
        d3 = Path(tempfile.mkdtemp()); reg3 = str(d3 / "r.csv"); buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                push(rows[:100], "42", api_key="K", registry=reg3)
            raise AssertionError("short response accepted")
        except RuntimeError as e:
            assert "batch 1" in str(e) and "99 < sent 100" in str(e)
        assert "WARN accepted 99 < sent 100" in buf.getvalue() and '"upload_count": 99' in buf.getvalue() and not Path(reg3).exists()
        post = lambda url, payload, params=None: {"ok": True, "upload_count": 100, "skipped_count": 0}
        with contextlib.redirect_stdout(io.StringIO()):
            push(rows[:100], "42", api_key="K", registry=reg3)
        assert len(c.read_csv(reg3)) == 100
        post = lambda url, payload, params=None: calls.append((url, payload, params)) or {"ok": True}
        # dry-run: no POST
        calls.clear(); c._reset(dry=True)
        with contextlib.redirect_stdout(io.StringIO()):
            pushed, _ = push(rows[:3], "42", dry_run=True, registry=None)
        assert not calls and len(pushed) == 3
        # pushed file round trip
        d = Path(tempfile.mkdtemp()); src = d / "l.csv"; c.write_csv(src, rows[:2])
        reg2 = str(d / "reg2.csv"); sys.argv = ["x", str(src), "--campaign-id", "7", "--out", reg2]; c._reset()
        with contextlib.redirect_stdout(io.StringIO()):
            main()
        assert [r["pushed_to"] for r in c.read_csv(reg2)] == ["smartlead"] * 2
    finally:
        post = real
        c._reset()
    print("OK")


if __name__ == "__main__":
    main()
