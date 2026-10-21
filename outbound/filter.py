"""Generic CSV filter: --keep-regex, --days, --neq, --suppress, --dedupe-on. Offline; dropped rows go to <out>.dropped.csv."""
import argparse, io, json, re, sys, tempfile, contextlib
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from outbound import common as c


def _norm(s):
    return " ".join((s or "").lower().split())


def _kv(spec, flag):
    k, _, v = spec.partition("=")  # ponytail: column names containing '=' are unsupported
    if not k or not v:
        raise SystemExit(f"{flag} expects col=VALUE, got {spec!r}")
    return k, v


def _range(rng):
    lo, sep, hi = rng.partition("..")
    try:
        lo, hi = int(lo), int(hi)
    except ValueError:
        sep = ""
    if not sep:
        raise SystemExit(f"filter: --days expects col=MIN..MAX with integers, got {rng!r}")
    if lo > hi:
        raise SystemExit(f"filter: --days MIN > MAX ({lo}..{hi})")
    return lo, hi


def _pair(spec):
    a, _, b = spec.partition(",")
    if not a or not b or "," in b:
        raise SystemExit(f"filter: --neq expects colA,colB, got {spec!r}")
    return [a, b]


def expand_json_col(rows, col):
    """{"job_change": '{"status":"moved","date":"2026-01-01"}'} -> adds job_change.status, job_change.date (scalars only; nested
    objects/lists are left JSON-encoded). Empty or unparseable cells add nothing. Original column is kept."""
    out = []
    for r in rows:
        r = dict(r)
        try:
            obj = json.loads(r.get(col) or "")
        except ValueError:
            obj = None
        if isinstance(obj, dict):
            for k, v in obj.items():
                r[f"{col}.{k}"] = "" if v is None else (v if isinstance(v, str) else json.dumps(v))
        out.append(r)
    return out


def apply_filters(rows, keep_regex=(), days=(), neq=(), crm_rows=None, dedupe_on=None, today=None):
    """Return (kept, dropped, counts). Rules run in this order; a row is dropped by the first rule it fails.
    Column names are exact header matches, so dotted names like job_change.date work on flattened CSVs."""
    today = today or date.today()
    kept, dropped = list(rows), []

    def drop(rule, pred):
        nonlocal kept
        keep = []
        for r in kept:
            (keep if pred(r) else dropped).append(r if pred(r) else {**r, "drop_reason": rule})
        kept = keep

    for spec in keep_regex:
        col, rx = _kv(spec, "--keep-regex")
        drop(f"keep_regex:{col}", lambda r, col=col, rx=re.compile(rx): bool(rx.search((r.get(col) or "").strip())))
    for spec in days:
        col, rng = _kv(spec, "--days")
        lo, hi = _range(rng)

        def ok(r, col=col, lo=lo, hi=hi):
            try:
                d = date.fromisoformat((r.get(col) or "").strip()[:10])
            except ValueError:
                return False  # blank or unparseable date is never in range
            return today - timedelta(days=hi) <= d <= today - timedelta(days=lo)  # inclusive both ends

        drop(f"days:{col}", ok)
    for spec in neq:
        a, b = _pair(spec)
        drop(f"neq:{a},{b}", lambda r, a=a, b=b: not (_norm(r.get(a)) and _norm(r.get(a)) == _norm(r.get(b))))
    if crm_rows is not None:
        k, d = c.suppress(kept, crm_rows, today=today)
        kept, dropped = k, dropped + [{**r, "drop_reason": f"suppress:{r['suppress_reason']}"} for r in d]
    if dedupe_on:
        k = c.dedupe(kept, dedupe_on)
        ids = {id(r) for r in k}
        dropped += [{**r, "drop_reason": f"dedupe:{','.join(dedupe_on)}"} for r in kept if id(r) not in ids]
        kept = k
    return kept, dropped, Counter(r["drop_reason"] for r in dropped)


def main(argv=None):
    ap = c.cli_common(argparse.ArgumentParser(description=__doc__))  # --dry-run/--cap-usd are no-ops: no network here
    ap.add_argument("input", nargs="?")
    ap.add_argument("--keep-regex", action="append", default=[], metavar="col=REGEX")
    ap.add_argument("--days", action="append", default=[], metavar="col=MIN..MAX")
    ap.add_argument("--neq", action="append", default=[], metavar="colA,colB")
    ap.add_argument("--suppress", metavar="CRM.csv")
    ap.add_argument("--dedupe-on", metavar="col1,col2")
    ap.add_argument("--today", metavar="YYYY-MM-DD")
    ap.add_argument("--json-col", action="append", default=[], metavar="col",
                    help="expand a JSON-object cell into col.key columns first (Deepline exports nest results, e.g. job_change)")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.input or not a.out:
        ap.error("input CSV and --out are required")
    rows = c.read_csv(a.input)
    for col in a.json_col:
        rows = expand_json_col(rows, col)
    header = list(dict.fromkeys(k for r in rows for k in r))
    for spec in a.keep_regex + a.days:
        _kv(spec, "--keep-regex/--days")
    for spec in a.days:
        _range(spec.partition("=")[2])
    named = [_kv(s, "--keep-regex")[0] for s in a.keep_regex] + [_kv(s, "--days")[0] for s in a.days]
    for s in a.neq:
        named += _pair(s)
    named += a.dedupe_on.split(",") if a.dedupe_on else []
    for col in named:
        if rows and col not in header:
            raise SystemExit(f"filter: column '{col}' not in header: {header}")
    kept, dropped, counts = apply_filters(
        rows, a.keep_regex, a.days, a.neq, c.read_csv(a.suppress) if a.suppress else None,
        a.dedupe_on.split(",") if a.dedupe_on else None, date.fromisoformat(a.today) if a.today else None)
    cols = list(dict.fromkeys(k for r in rows for k in r))
    c.write_csv(a.out, kept, cols)
    c.write_csv(f"{a.out}.dropped.csv", dropped, cols + ["drop_reason", "suppress_reason"])
    print(f"kept {len(kept)} / dropped {len(dropped)} of {len(rows)}")
    for rule, n in counts.items():
        print(f"  dropped {n}: {rule}")
    return 0


def selftest():
    T = date(2026, 10, 21)
    ds = lambda n: (T - timedelta(days=n)).isoformat()
    mk = lambda **k: {"job_change.status": "moved", "job_change.date": ds(20), "job_change.new_company": "NewCo", "old_company": "OldCo", "email": "", **k}
    run = lambda rows, **k: apply_filters(rows, today=T, **k)
    reasons = lambda d: [r["drop_reason"] for r in d]

    # keep-regex alone (anchored, dotted header)
    k, d, n = run([mk(), mk(**{"job_change.status": "no_change"}), mk(**{"job_change.status": "moved_x"})], keep_regex=["job_change.status=^moved$"])
    assert len(k) == 1 and reasons(d) == ["keep_regex:job_change.status"] * 2 and n["keep_regex:job_change.status"] == 2
    # days alone: 14..45 inclusive at both boundaries, outside by one day dropped, blank/garbage dropped
    rows = [mk(**{"job_change.date": ds(x)}) for x in (13, 14, 45, 46)] + [mk(**{"job_change.date": ""}), mk(**{"job_change.date": "nope"}), mk(**{"job_change.date": ds(30) + "T10:00:00Z"})]
    k, d, _ = run(rows, days=["job_change.date=14..45"])
    assert [r["job_change.date"][:10] for r in k] == [ds(14), ds(45), ds(30)] and len(d) == 4 and set(reasons(d)) == {"days:job_change.date"}
    # neq alone: case/whitespace-insensitive; different kept
    k, d, _ = run([mk(old_company="  newco "), mk(old_company="NEWCO"), mk(old_company="Other")], neq=["job_change.new_company,old_company"])
    assert [r["old_company"] for r in k] == ["Other"] and reasons(d) == ["neq:job_change.new_company,old_company"] * 2
    # suppress alone
    crm = [{"email": "s@b.com", "in_sequence": "true"}]
    k, d, _ = run([mk(email="s@b.com"), mk(email="ok@z.com")], crm_rows=crm)
    assert [r["email"] for r in k] == ["ok@z.com"] and reasons(d) == ["suppress:in_sequence"]
    # dedupe alone: first wins
    k, d, _ = run([mk(email="a@x.com", n="1"), mk(email="A@x.com", n="2")], dedupe_on=["email"])
    assert [r["n"] for r in k] == ["1"] and reasons(d) == ["dedupe:email"]
    # combined: first failing rule is the reason, counts add up
    rows = [mk(email="1@x.com"), mk(email="2@x.com", **{"job_change.status": "left_company"}), mk(email="3@x.com", **{"job_change.date": ds(5)}),
            mk(email="4@x.com", old_company="newco"), mk(email="s@b.com"), mk(email="1@x.com")]
    k, d, n = run(rows, keep_regex=["job_change.status=^moved$"], days=["job_change.date=14..45"], neq=["job_change.new_company,old_company"], crm_rows=crm, dedupe_on=["email"])
    assert [r["email"] for r in k] == ["1@x.com"] and len(k) + len(d) == len(rows)
    assert reasons(d) == ["keep_regex:job_change.status", "days:job_change.date", "neq:job_change.new_company,old_company", "suppress:in_sequence", "dedupe:email"]
    # CLI end to end: files, dropped.csv carries drop_reason, summary printed
    td = Path(tempfile.mkdtemp())
    c.write_csv(td / "in.csv", [mk(email="1@x.com"), mk(email="2@x.com", **{"job_change.status": "no_change"})])
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert main([str(td / "in.csv"), "--out", str(td / "o.csv"), "--keep-regex", "job_change.status=^moved$", "--today", T.isoformat()]) == 0
    assert [r["email"] for r in c.read_csv(td / "o.csv")] == ["1@x.com"] and "kept 1 / dropped 1 of 2" in buf.getvalue()
    dr = c.read_csv(td / "o.csv.dropped.csv")
    assert len(dr) == 1 and dr[0]["drop_reason"] == "keep_regex:job_change.status" and dr[0]["email"] == "2@x.com"
    # fail loudly: missing column (neq would fail open), bad specs
    def bad(*args):
        try:
            main([str(td / "in.csv"), "--out", str(td / "o2.csv"), *args])
        except SystemExit as e:
            return str(e)
        raise AssertionError(f"no failure for {args}")
    assert "column 'new_compny' not in header" in bad("--neq", "job_change.new_company,new_compny")
    assert "column 'job_change.stat' not in header" in bad("--keep-regex", "job_change.stat=^moved$")
    assert "column 'nope' not in header" in bad("--days", "nope=1..2") and "column 'zz' not in header" in bad("--dedupe-on", "zz")
    assert "MIN..MAX" in bad("--days", "job_change.date=14") and "MIN..MAX" in bad("--days", "job_change.date=a..b")
    assert "MIN > MAX" in bad("--days", "job_change.date=45..14") and "colA,colB" in bad("--neq", "email")
    assert not (td / "o2.csv").exists()
    # --json-col expands a Deepline-style nested cell into dotted columns the other flags can read
    ex = expand_json_col([{"full_name": "T", "job_change": '{"status": "moved", "date": "2026-01-01", "new_company": "Zalando", "experiences": [1], "id": null}'},
                          {"full_name": "E", "job_change": ""}, {"full_name": "X", "job_change": "not json"}], "job_change")
    assert ex[0]["job_change.status"] == "moved" and ex[0]["job_change.new_company"] == "Zalando" and ex[0]["job_change.experiences"] == "[1]" and ex[0]["job_change.id"] == ""
    assert "job_change.status" not in ex[1] and "job_change.status" not in ex[2] and ex[0]["job_change"].startswith("{")
    d4 = Path(tempfile.mkdtemp()); src = d4 / "jc.csv"; dst = d4 / "mv.csv"
    c.write_csv(src, ex, ["full_name", "job_change"])
    with contextlib.redirect_stdout(io.StringIO()):
        main([str(src), "--json-col", "job_change", "--keep-regex", "job_change.status=^moved$", "--days", "job_change.date=14..400", "--today", "2026-10-21", "--out", str(dst)])
    assert [r["full_name"] for r in c.read_csv(dst)] == ["T"]
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
