"""Play 1: email waterfall. GetLeads -> Deepline (-> FullEnrich with --deep), verify, stop rule. Never guesses emails from name patterns."""
import argparse, contextlib, io, sys, tempfile
from pathlib import Path

from outbound import common as c

GETLEADS_CREDIT_USD = 0.0  # set to your plan's per-credit price (charged per hit only)
DEEPLINE_FIND_USD = 0.05   # per-row estimates for the ledger/dry-run; tune to your Deepline bill
VERIFY_USD = 0.003
BOUNCEBAN_USD = 0.02
FULLENRICH_USD = 0.10
PER_ROW_CAP_USD = 0.15     # default total cap = rows x this, when --cap-usd is not given
OUT_COLS = ["email", "email_status", "email_provider", "verifier", "mx_class", "miss_reason"]
# vendor verdicts the shared map lacks: millionverifier says "ok"; bounceban says deliverable/undeliverable
_EXTRA = {"ok": "valid", "deliverable": "valid", "undeliverable": "invalid", "risky": "catch_all"}


def _norm(raw):
    r = str(raw or "").strip().lower()
    return c.normalize_status(_EXTRA.get(r, r))


def _first(d, *keys):
    for k in keys:
        if d.get(k):
            return d[k]
    return None


def _items(out, *keys):
    """Pull the row list out of a CLI/REST JSON payload (shape unverified: list, or dict holding a list)."""
    if isinstance(out, list):
        return out
    for k in (*keys, "rows", "results", "data", "output"):
        v = (out or {}).get(k) if isinstance(out, dict) else None
        if isinstance(v, list):
            return v
        if isinstance(v, dict):
            return _items(v, *keys)
    return []


def find_getleads(rows):
    """One candidate dict (or {}) per row, aligned. Candidate: email, provider, raw_status, miss_reason."""
    out = c.getleads("POST", "/api/v1/enrich/from-linkedin",
                     json={"items": [{"linkedin_url": r["linkedin_url"]} for r in rows], "limit_per_item": 1},
                     usd=0.0, label="getleads:enrich")
    res = _items(out, "results")
    cands = []
    for i in range(len(rows)):
        d = (res[i].get("data") or {}) if i < len(res) and res[i].get("success") else {}  # ponytail: aligned by position, GetLeads echoes order
        em = _first(d, "email", "work_email", "professional_email")
        if not em and isinstance(d.get("emails"), list) and d["emails"]:
            e0 = d["emails"][0]
            em = e0.get("email") if isinstance(e0, dict) else e0
        if em:
            c.spend(GETLEADS_CREDIT_USD, "getleads:credit")  # 1 credit per success only
            cands.append({"email": em, "provider": "getleads", "raw_status": _first(d, "email_status", "status")})
        else:
            cands.append({})
    return cands


def find_deepline(rows):
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "in.csv"
        c.write_csv(p, rows, ["first_name", "last_name", "company_domain", "linkedin_url"])
        out = c.deepline_play("prebuilt/person-to-email-batch", csv_path=p, usd_estimate=DEEPLINE_FIND_USD * len(rows))
    return _align(rows, _items(out), "deepline")


def find_fullenrich(rows):
    """--deep. Async job; deepline_action blocks until terminal. Params/shape per provider-playbooks/fullenrich.md (unverified)."""
    data = [{"first_name": r["first_name"], "last_name": r["last_name"], "domain": r["company_domain"],
             "linkedin_url": r.get("linkedin_url") or None, "enrich_fields": ["contact.emails"]} for r in rows]
    out = c.deepline_action("fullenrich_bulk_enrich", {"name": "play-1", "data": data}, FULLENRICH_USD * len(rows))
    return _align(rows, _items(out, "datas"), "fullenrich")


def _align(rows, res, default_provider):
    cands = []
    for i in range(len(rows)):
        d = res[i] if i < len(res) and isinstance(res[i], dict) else {}  # ponytail: positional; swap to key match if the play reorders
        em = _first(d, "email", "most_probable_work_email")
        if isinstance(em, dict):
            em = em.get("email")
        cands.append({"email": em, "provider": d.get("email_source") or default_provider,
                      "raw_status": _first(d, "email_validated", "email_status"), "miss_reason": d.get("miss_reason"),
                      "mx_class": d.get("email_route")} if em else {"miss_reason": d.get("miss_reason")})
    return cands


def verify(email):
    """MillionVerifier; catch_all -> BounceBan once. Returns (status, verifier)."""
    mv = c.deepline_action("millionverifier_verify_email", {"email": email}, VERIFY_USD) or {}
    st = _norm(_first(mv, "email_status", "status", "result"))
    if st != "catch_all":
        return st, "millionverifier"
    bb = c.deepline_action("bounceban_verify_single", {"email": email}, BOUNCEBAN_USD) or {}
    # ponytail: BounceBan may answer status=verifying; we keep catch_all rather than poll (never goes live either way)
    b = _norm(_first(bb, "email_status", "result"))
    return (b if b in ("verified", "discard") else "catch_all"), "millionverifier+bounceban"


def _resolve(cand):
    """Candidate -> (status, verifier). Provider-declared valid skips the verifier."""
    st = _norm(cand.get("raw_status"))
    if st == "verified":
        return st, "provider"
    return verify(cand["email"])


def run(rows, finders):
    """rows -> output rows (same order, never dropped). finders: [(name, fn)]; stops at the first non-discard verdict."""
    res = [{**r, "email": "", "email_status": "not_found", "email_provider": "", "verifier": "", "mx_class": "", "miss_reason": ""} for r in rows]
    pending = list(range(len(rows)))
    try:
        for name, fn in finders:
            if not pending:
                break
            sub = [rows[i] for i in pending if name != "getleads" or rows[i].get("linkedin_url")]
            idx = [i for i in pending if name != "getleads" or rows[i].get("linkedin_url")]
            if not sub:
                continue
            for i, cand in zip(idx, fn(sub)):
                if not cand or not cand.get("email"):
                    if cand and cand.get("miss_reason"):
                        res[i]["miss_reason"] = str(cand["miss_reason"])
                    continue
                st, ver = _resolve(cand)
                if st == "discard":
                    res[i]["miss_reason"] = f"{name}:discarded"
                    continue
                res[i].update(email=cand["email"], email_status=st, email_provider=cand.get("provider") or name,
                              verifier=ver, mx_class=cand.get("mx_class") or "", miss_reason="")
                pending.remove(i)
    except c.SpendCapExceeded as e:
        for i in pending:
            res[i]["miss_reason"] = "cap_aborted"
        print(f"CAP: {e}", file=sys.stderr)
        return res, True
    return res, False


def summarize(n_in, n_dedup, out, aborted):
    n = len(out) or 1
    pct = {k: 100 * sum(r["email_status"] == k for r in out) / n for k in c.STATUS}
    prov = {}
    for r in out:
        if r["email"]:
            prov[r["email_provider"]] = prov.get(r["email_provider"], 0) + 1
    vcalls = sum(1 for k in c.SPENT["calls"] if "millionverifier" in k["label"] or "bounceban" in k["label"])
    lines = ["# Play 1 report", "", f"- rows in: {n_in}, after dedupe: {n_dedup} (removed {n_in - n_dedup})",
             *[f"- {k}: {pct[k]:.1f}%" for k in c.STATUS],
             "- hits per provider: " + (", ".join(f"{k} {v}" for k, v in sorted(prov.items())) or "none"),
             f"- verifier calls: {vcalls}", f"- spend: {c.report()}"]
    if c.SPENT["dry_run"]:
        lines.append("- DRY RUN: nothing was called, so the percentages above are meaningless")
    if aborted:
        lines.append("- ABORTED by spend cap: unprocessed rows are not_found with miss_reason=cap_aborted")
    lines.append("- Send only `verified` to Smartlead; `catch_all`/`unknown` go to the LinkedIn-only track.")
    return "\n".join(lines) + "\n", pct


def main(argv=None):
    ap = c.cli_common(argparse.ArgumentParser(description=__doc__))
    ap.add_argument("input", nargs="?")
    ap.add_argument("--batch", type=int, default=150)
    ap.add_argument("--deep", action="store_true", help="also try FullEnrich (charges for catch-all; off by default)")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.input or not a.out:
        ap.error("input CSV and --out are required")
    c.apply_cli(a)
    rows = c.read_csv(a.input)
    ded = c.dedupe(c.dedupe(rows, ["linkedin_url"]), ["first_name", "last_name", "company_domain"])
    print(f"dedupe: {len(rows)} -> {len(ded)} rows ({len(rows) - len(ded)} removed)")
    if a.cap_usd is None:
        c.set_cap(len(ded) * PER_ROW_CAP_USD)
    finders = [("getleads", find_getleads), ("deepline", find_deepline)] + ([("fullenrich", find_fullenrich)] if a.deep else [])
    out, aborted = [], False
    for b in c.batches(ded, a.batch):
        if aborted:  # rows are never dropped
            out += [{**r, "email": "", "email_status": "not_found", "email_provider": "", "verifier": "", "mx_class": "", "miss_reason": "cap_aborted"} for r in b]
            continue
        if a.dry_run:
            c.spend(VERIFY_USD * len(b), "deepline:verify(est)")
        res, aborted = run(b, finders)
        out += res
    cols = list(dict.fromkeys([k for r in ded for k in r] + OUT_COLS))
    c.write_csv(a.out, out, cols)
    text, _ = summarize(len(rows), len(ded), out, aborted)
    Path(str(a.out) + ".report.md").write_text(text)
    print(text, end="")
    return 0


def selftest():
    global find_getleads, find_deepline, verify
    real = (find_getleads, find_deepline, verify)
    mk = lambda n: [{"first_name": f"f{i}", "last_name": "l", "company_domain": f"d{i}.com", "linkedin_url": f"li{i}"} for i in range(n)]
    calls = []

    def fake(table):  # finder returning {row first_name: candidate}
        return lambda rows: [table.get(r["first_name"], {}) for r in rows]

    def go(rows, gl, dl, ver, cap=None):
        global find_getleads, find_deepline, verify
        c._reset(cap=cap)
        calls.clear()
        find_getleads, find_deepline = fake(gl), fake(dl)
        verify = lambda e: (calls.append(e), ver[e])[1]
        return run(rows, [("getleads", find_getleads), ("deepline", find_deepline)])

    V, CA, U, D = ("verified", "millionverifier"), ("catch_all", "x"), ("unknown", "millionverifier"), ("discard", "x")
    cand = lambda e, p="getleads": {"email": e, "provider": p}
    # valid first provider stops: deepline never asked about f0
    out, ab = go(mk(1), {"f0": cand("a@x.com")}, {"f0": cand("WRONG@x.com")}, {"a@x.com": V})
    assert out[0]["email"] == "a@x.com" and out[0]["email_status"] == "verified" and out[0]["email_provider"] == "getleads" and calls == ["a@x.com"] and not ab
    # unknown stops
    out, _ = go(mk(1), {"f0": cand("u@x.com")}, {"f0": cand("WRONG@x.com")}, {"u@x.com": U})
    assert out[0]["email_status"] == "unknown" and calls == ["u@x.com"]
    # discard -> fall through -> second provider hit
    out, _ = go(mk(1), {"f0": cand("bad@x.com")}, {"f0": cand("good@y.com", "prospeo")}, {"bad@x.com": D, "good@y.com": V})
    assert out[0]["email"] == "good@y.com" and out[0]["email_provider"] == "prospeo" and out[0]["miss_reason"] == "" and calls == ["bad@x.com", "good@y.com"]
    # exhausted -> not_found, never constructed, rows kept
    out, _ = go(mk(2), {}, {"f1": {"miss_reason": "no_match"}}, {})
    assert [r["email_status"] for r in out] == ["not_found"] * 2 and out[1]["miss_reason"] == "no_match" and out[0]["email"] == ""
    # row without linkedin_url skips getleads but still reaches deepline
    rows = mk(1); rows[0]["linkedin_url"] = ""
    out, _ = go(rows, {"f0": cand("no@x.com")}, {"f0": cand("d@x.com", "p")}, {"d@x.com": V})
    assert out[0]["email"] == "d@x.com"
    # provider-declared valid skips the verifier
    out, _ = go(mk(1), {"f0": {**cand("v@x.com"), "raw_status": "valid"}}, {}, {})
    assert out[0]["verifier"] == "provider" and calls == []
    # real verify(): catch-all calls BounceBan exactly once; plain valid never does
    find_getleads, find_deepline, verify = real
    seen = []
    orig = c.deepline_action
    def fa(aid, params, usd):
        seen.append(aid)
        return {"status": "catch_all"} if aid.startswith("million") else {"status": "risky"}
    c.deepline_action = fa
    try:
        c._reset()
        assert verify("c@x.com") == ("catch_all", "millionverifier+bounceban") and seen == ["millionverifier_verify_email", "bounceban_verify_single"]
        seen.clear(); c.deepline_action = lambda a, p, u: seen.append(a) or {"status": "ok"}
        assert verify("o@x.com") == ("verified", "millionverifier") and len(seen) == 1
    finally:
        c.deepline_action = orig
    # cap abort mid-batch keeps processed rows, output has every row
    def capped(rows):
        c.spend(0.1, "x")
        return [cand(f"{r['first_name']}@x.com") for r in rows]
    c._reset(cap=0.05)
    find_getleads = lambda rows: [cand("done@x.com")] + [None] * (len(rows) - 1)
    find_deepline = capped
    verify = lambda e: ("verified", "m")
    with contextlib.redirect_stderr(io.StringIO()):
        out, ab = run(mk(3), [("getleads", find_getleads), ("deepline", find_deepline)])
    assert ab and len(out) == 3 and out[0]["email"] == "done@x.com" and out[1]["miss_reason"] == "cap_aborted" and out[2]["email_status"] == "not_found"
    find_getleads, find_deepline, verify = real
    # dedupe before spend + report sums to 100
    rows = mk(2) + [dict(mk(1)[0])] + [{**mk(2)[1], "linkedin_url": ""}]
    ded = c.dedupe(c.dedupe(rows, ["linkedin_url"]), ["first_name", "last_name", "company_domain"])
    assert len(ded) == 2
    out = [{"email": "a", "email_status": s, "email_provider": "p"} for s in ("verified", "catch_all", "unknown", "not_found", "verified", "not_found", "verified")]
    text, pct = summarize(9, 7, out, False)
    assert abs(sum(pct.values()) - 100) < 1e-9 and "removed 2" in text
    # dry-run end to end: planned, nothing spent, every row kept
    td = Path(tempfile.mkdtemp())
    c.write_csv(td / "in.csv", mk(3) + mk(1))
    c._reset()
    with contextlib.redirect_stdout(io.StringIO()):
        assert main([str(td / "in.csv"), "--out", str(td / "o.csv"), "--dry-run"]) == 0
    assert c.SPENT["usd"] == 0.0 and len(c.read_csv(td / "o.csv")) == 3 and (td / "o.csv.report.md").exists()
    c._reset()
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
