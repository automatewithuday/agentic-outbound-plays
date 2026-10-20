"""Play 2 scorer: TAM + signals.csv -> accounts_scored.csv. Offline; collection happens in the skill via MCP tools."""
import argparse, contextlib, io, sys, tempfile
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import yaml

from outbound import common as c

ROOT = Path(__file__).resolve().parent.parent
# No freshness window: these never go stale on their own (a closed-lost deal or a transcript mention stays relevant).
NO_WINDOW = ("crm_closed_lost", "transcript_mention")
PARTIES = {"first": "first_party", "second": "second_party", "third": "third_party"}


def _dom(s):
    return (s or "").strip().lower()


def score(tam, signals, cfg, today):
    """Return (rows, warnings). Window is inclusive [min, max] days before `today`."""
    warn, tam_doms = Counter(), {_dom(r["company_domain"]) for r in tam}
    fresh, seen = [], {}
    for s in signals:
        d, t, p = _dom(s.get("company_domain")), (s.get("signal_type") or "").strip(), (s.get("party") or "").strip()
        if t not in cfg["freshness_days"] and t not in NO_WINDOW:
            warn["unknown signal_type"] += 1
            continue
        if p not in PARTIES:
            warn["unknown party"] += 1
            continue
        try:
            age = (today - date.fromisoformat((s.get("event_date") or "").strip())).days
        except ValueError:
            warn["blank/malformed event_date"] += 1
            continue
        if t not in NO_WINDOW and not cfg["freshness_days"][t][0] <= age <= cfg["freshness_days"][t][1]:
            warn["outside freshness window"] += 1
            continue
        if d not in tam_doms:
            warn["domain not in TAM"] += 1
            continue
        key = (d, t, s["event_date"].strip())
        if key in seen:  # same event from another source: keep the first, but prefer one that has a source_url
            warn["duplicate"] += 1
            if not seen[key]["source_url"] and s.get("source_url"):
                seen[key].update(source_url=s["source_url"], party=p)
            continue
        seen[key] = dict(d=d, type=t, party=p, date=s["event_date"].strip(), source_url=(s.get("source_url") or "").strip())
        fresh.append(seen[key])
    by = {}
    for f in fresh:
        by.setdefault(f["d"], []).append(f)
    b = cfg["bands"]
    out = []
    for r in tam:
        fs = by.get(_dom(r["company_domain"]), [])
        sc = min(cfg["max_score"], sum(cfg["weights"][PARTIES[f["party"]]] for f in fs))
        band = "work_today" if sc >= b["work_today"] else "sequence_this_week" if sc >= b["sequence_this_week"] else "nurture"
        out.append({"company_domain": r["company_domain"], "company_name": r.get("company_name", ""), "score": sc, "band": band,
                    "signal_count": len(fs), "signals": " | ".join(f"{f['type']}@{f['date']}<{f['source_url']}>" for f in fs)})
    return out, warn


def main(argv=None):
    ap = c.cli_common(argparse.ArgumentParser(description=__doc__))  # --dry-run/--cap-usd are no-ops: no network here
    ap.add_argument("tam", nargs="?")
    ap.add_argument("--signals")
    ap.add_argument("--config", default=str(ROOT / "config" / "signal_scoring.yaml"))
    ap.add_argument("--today", metavar="YYYY-MM-DD")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not (a.tam and a.signals and a.out):
        ap.error("tam CSV, --signals and --out are required")
    c.apply_cli(a)
    cfg = yaml.safe_load(Path(a.config).read_text())
    rows, warn = score(c.read_csv(a.tam), c.read_csv(a.signals), cfg, date.fromisoformat(a.today) if a.today else date.today())
    for k, n in warn.items():
        print(f"score_signals: dropped {n} signal row(s): {k}", file=sys.stderr)
    c.write_csv(a.out, rows, ["company_domain", "company_name", "score", "band", "signal_count", "signals"])
    n = Counter(r["band"] for r in rows)
    print(f"work_today {n['work_today']} / sequence_this_week {n['sequence_this_week']} / nurture {n['nurture']} of {len(rows)} -> {a.out}")
    return 0


def selftest():
    T = date(2026, 6, 30)
    cfg = yaml.safe_load((ROOT / "config" / "signal_scoring.yaml").read_text())
    ago = lambda n: (T - timedelta(days=n)).isoformat()
    tam = [{"company_domain": f"{x}.com", "company_name": x.upper()} for x in "abcdefgh"]
    sig = lambda d, t, p, n, u="", ev=None: {"company_domain": d, "signal_type": t, "party": p, "event_date": ev or ago(n), "source_url": u, "detail": ""}

    def run(sigs):
        rows, w = score(tam, sigs, cfg, T)
        return {r["company_domain"]: r for r in rows}, w

    # window boundaries, both ends, inclusive (funding is [14, 28])
    r, w = run([sig("a.com", "funding", "third", n) for n in (13, 14)] + [sig("b.com", "funding", "third", n) for n in (28, 29)])
    assert r["a.com"]["signal_count"] == 1 and r["a.com"]["signals"].startswith(f"funding@{ago(14)}")
    assert r["b.com"]["signal_count"] == 1 and r["b.com"]["signals"].startswith(f"funding@{ago(28)}")
    assert w["outside freshness window"] == 2
    # future date is outside a [0, N] window too
    assert run([sig("a.com", "news", "third", -1)])[0]["a.com"]["signal_count"] == 0
    # dedupe across sources: same (domain, type, date) -> one signal, first with a source_url wins
    r, w = run([sig("c.com", "funding", "third", 20, ""), sig("c.com", "funding", "third", 20, "http://x/1"), sig("c.com", "funding", "third", 20, "http://x/2")])
    assert r["c.com"]["signal_count"] == 1 and r["c.com"]["score"] == 10 and r["c.com"]["signals"] == f"funding@{ago(20)}<http://x/1>", r["c.com"]
    # cap at max_score: 3 first-party + 1 third = 130 -> 100
    r, _ = run([sig("d.com", "engagement", "first", n) for n in (1, 2, 3)] + [sig("d.com", "news", "third", 1)])
    assert r["d.com"]["score"] == 100 and r["d.com"]["signal_count"] == 4 and r["d.com"]["band"] == "work_today"
    # band edges: exactly 80 and exactly 40
    r, _ = run([sig("e.com", "engagement", "first", 1), sig("e.com", "website_visit", "first", 1), sig("f.com", "engagement", "first", 1)])
    assert (r["e.com"]["score"], r["e.com"]["band"]) == (80, "work_today") and (r["f.com"]["score"], r["f.com"]["band"]) == (40, "sequence_this_week")
    r, _ = run([sig("g.com", "news", "second", 1), sig("g.com", "hiring", "third", 8), sig("g.com", "news", "third", 2)])  # 25+10+10 = 45
    assert r["g.com"]["score"] == 45 and r["g.com"]["band"] == "sequence_this_week"
    r, _ = run([sig("g.com", "news", "second", 1), sig("g.com", "hiring", "third", 8)])  # 35 -> just under
    assert (r["g.com"]["score"], r["g.com"]["band"]) == (35, "nurture")
    # no windows for closed-lost / transcript; empty signals -> nurture, score 0, row kept
    r, _ = run([sig("a.com", "crm_closed_lost", "first", 400)])
    assert r["a.com"]["score"] == 40 and r["h.com"]["score"] == 0 and r["h.com"]["band"] == "nurture" and r["h.com"]["signals"] == ""
    assert run([])[0]["h.com"]["signal_count"] == 0 and len(run([])[0]) == 8
    # bad rows never crash: blank/malformed date, unknown type/party, domain outside TAM
    r, w = run([sig("a.com", "funding", "third", 0, ev=" "), sig("a.com", "funding", "third", 0, ev="31/12/2026"), sig("a.com", "g2_intent", "third", 1),
                sig("a.com", "news", "fourth", 1), sig("zzz.com", "news", "third", 1)])
    assert r["a.com"]["score"] == 0 and w["blank/malformed event_date"] == 2 and w["unknown signal_type"] == 1 and w["unknown party"] == 1 and w["domain not in TAM"] == 1
    # CLI end to end
    td = Path(tempfile.mkdtemp())
    c.write_csv(td / "tam.csv", tam)
    c.write_csv(td / "s.csv", [sig("a.com", "engagement", "first", 1, "http://p/1"), sig("a.com", "funding", "third", 14), sig("a.com", "news", "third", 1)])
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert main([str(td / "tam.csv"), "--signals", str(td / "s.csv"), "--out", str(td / "o.csv"), "--today", T.isoformat()]) == 0
    o = c.read_csv(td / "o.csv")
    assert list(o[0]) == ["company_domain", "company_name", "score", "band", "signal_count", "signals"] and len(o) == 8
    assert (o[0]["score"], o[0]["band"], o[0]["signal_count"]) == ("60", "sequence_this_week", "3") and " | " in o[0]["signals"]
    assert "sequence_this_week 1 / nurture 7" in buf.getvalue() and "work_today 0" in buf.getvalue(), buf.getvalue()
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
