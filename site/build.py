#!/usr/bin/env python3
"""Build the static results site into _site/.

Inputs: results/**/results.json (timings), bench/tools.py (TOOLS, PLANNED_GUI) and site/catalog.py (every known
disk analyzer, benchmarked or not). Everything is rendered generically, so new tools, GUI apps and PLANNED_GUI
reasons show up without touching this file.

Pages: index.html (leaderboard), tools/<id>.html (one per benchmarked tool), catalog.html (all programs),
details.html (runs, datasets, charts, correctness), methodology.html, badges.html, results/ (raw JSON).
The OS / cache-view switches are CSS-only radio tabs; assets/site.js only adds deep links, memory and the theme toggle.
"""
import glob, html, json, math, os, re, shutil, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "_site")
sys.path.insert(0, os.path.join(ROOT, "bench"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tools import TOOLS, PLANNED_GUI
from catalog import CATALOG
E = html.escape
REPO = "https://github.com/mikewirth/diskscan-bench"
BASE_URL = "https://mikewirth.github.io/diskscan-bench"

def load():
    runs = []
    for f in sorted(glob.glob(os.path.join(ROOT, "results", "*", "*", "results.json"))):
        r = json.load(open(f)); rel = os.path.relpath(f, ROOT)
        r["_path"] = rel; r["_date"] = rel.split(os.sep)[1]; r["_label"] = rel.split(os.sep)[2]
        runs.append(r)
    latest = {}
    for r in runs:  # latest full run per runner label, else latest smoke
        k = r["_label"]; cur = latest.get(k)
        rank = lambda x: (x["profile"] == "full", x["_date"], x["generated_utc"])
        if cur is None or rank(r) > rank(cur): latest[k] = r
    return runs, latest

# ---------------- formatting ----------------
def fmt_t(s):
    if s is None: return "–"
    return f"{s*1000:.1f} ms" if s < 1 else f"{s:.2f} s"

def fmt_b(b):
    if b is None: return "–"
    for u in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(b) < 1024 or u == "TiB": return f"{b:.1f} {u}" if u != "B" else f"{b} B"
        b /= 1024

def short_ver(v):
    v = v or ""
    if v.startswith("BSD"): return "BSD"
    m = re.search(r"git \w+|\d+(?:\.\d+)+", v)
    return m.group(0) if m else ""

def split_name(n):
    """'pdu (parallel-disk-usage)' -> ('pdu', 'parallel-disk-usage')"""
    m = re.match(r"^(.*?)\s*\((.*)\)\s*$", n)
    return (m.group(1), m.group(2)) if m else (n, "")

def norm(n):
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\(.*?\)", "", n.lower()))

PLAT_NAME = {"macos": "macOS", "linux": "Linux", "windows": "Windows"}
PLATS = ("macos", "linux", "windows")
KIND = {"cli": "CLI", "tui": "TUI", "gui": "GUI"}
SEMANTICS = {  # refwalk.py quantities, in words
    "alloc_du": "allocated incl. directories, hard links once (du -s)",
    "alloc_files_dedup": "allocated, without directory blocks",
    "alloc_nodedup": "allocated, hard links counted twice",
    "alloc_files_nodedup": "allocated, no directory blocks, hard links twice",
    "logical_dedup": "apparent size, hard links once",
    "logical": "apparent size, hard links counted twice",
    "logical_with_dirs": "apparent size incl. directories, hard links twice",
    "logical_with_dirs_dedup": "apparent size incl. directories",
}

# ---------------- scoring (see docs/methodology.md "Leaderboard score") ----------------
# Datasets held out of scoring pending investigation (shown on the details page, documented in methodology).
EXCLUDE_SCORING = {("macos", "node_modules"): "BSD du and the reference walker agree, but all 7 other tools report exactly 2.3% less; under investigation (likely APFS clone/compression accounting from npm's clonefile installs)"}
BASELINE = {"linux": "du", "macos": "du", "windows": "du-sysinternals"}

def suspect_datasets(r):
    """Reference is suspect when no tool matches it within 0.1% while >=3 tools agree with each other."""
    out = {ds for (pl, ds) in EXCLUDE_SCORING if pl == r["runner"]["platform"] and ds in r["datasets"]}
    for ds in r["datasets"]:
        rs = [x for x in r["results"] if x["dataset"] == ds and x.get("track", "cli") == "cli" and x.get("correctness")]
        PREC = {t["id"]: t.get("precision") for t in TOOLS}
        exact = [x for x in rs if PREC.get(x["tool"]) in ("exact", "kib") and x["correctness"]["status"] == "agrees" and abs(x["correctness"].get("diff_pct") or 0) < 0.1]
        if exact: continue  # some exact tool matches the reference -> reference is fine
        vals = [x["reported_bytes"] for x in rs if x["correctness"]["status"] == "disagrees" and x.get("reported_bytes")]
        for v in vals:
            if sum(1 for w in vals if abs(w - v) <= 0.001 * v) >= 3:
                out.add(ds); break
    return out

def valid(m):
    return m and m.get("median_s") and not m.get("invalid") and not m.get("error")

def scores(r, track, modes=("cold", "warm")):
    """Speed score = geometric mean over (dataset, cache mode) of baseline_median / tool_median.
    The official score uses both modes; modes=("cold",) / ("warm",) give the per-cache views."""
    plat = r["runner"]["platform"]; base = BASELINE[plat]; bad = suspect_datasets(r)
    rows = [x for x in r["results"] if x.get("track", "cli") == track]
    allres = r["results"]
    cells = [(ds, m) for ds in r["datasets"] if ds not in bad for m in modes
             if valid((next((x for x in allres if x["tool"] == base and x["dataset"] == ds), {}) or {}).get(m))]
    out = []
    for tid in dict.fromkeys(x["tool"] for x in rows):
        ratios, warn = [], []
        for ds, m in cells:
            bx = next(x for x in allres if x["tool"] == base and x["dataset"] == ds)
            tx = next((x for x in rows if x["tool"] == tid and x["dataset"] == ds), None)
            if tx and valid(tx.get(m)):
                ratios.append(bx[m]["median_s"] / tx[m]["median_s"])
        for x in rows:
            if x["tool"] == tid and x["dataset"] not in bad and (x.get("correctness") or {}).get("status") == "disagrees":
                warn.append(f'{x["dataset"]} {x["correctness"]["diff_pct"]:+.1f}%')
        if not ratios or len(ratios) < 0.5 * len(cells): continue
        geo = math.exp(sum(map(math.log, ratios)) / len(ratios))
        def med(mode):
            xs = [x[mode]["median_s"] for x in rows if x["tool"] == tid and x["dataset"] not in bad and valid(x.get(mode))]
            return math.exp(sum(map(math.log, xs)) / len(xs)) if xs else None
        out.append(dict(tool=tid, score=geo, n=len(ratios), cells=len(cells), warn=warn, cold=med("cold"), warm=med("warm")))
    out.sort(key=lambda d: -d["score"])
    return out, base, bad

# ---------------- catalog: site/catalog.py merged with bench/tools.py ----------------
def planned_gui():
    """PLANNED_GUI entries as dicts (accepts (platform, name, reason) tuples or dicts)."""
    out = []
    for p in PLANNED_GUI:
        if isinstance(p, dict): out.append(dict(platform=p.get("platform", "all"), name=p["name"], reason=p.get("reason", "")))
        else: out.append(dict(platform=p[0], name=p[1], reason=p[2]))
    return out

def infer_tag(reason):
    s = reason.lower()
    for keys, tag in ((("eula", "licen", "commercial", "personal use"), "License"),
                      (("never exits", "completion", "exit mode", "scan-and-exit"), "No completion signal"),
                      (("ui automation", "accessibility", "at-spi"), "Needs UI automation"),
                      (("excluded",), "Excluded"), (("internally", "same engine"), "Same engine")):
        if any(k in s for k in keys): return tag
    return "Planned"

def build_catalog(latest):
    """-> list of programs, each with .status[plat] = dict(state=bench|planned|not, tag, reason, ...)."""
    by_plat = {}
    for label, r in sorted(latest.items()):
        by_plat.setdefault(r["runner"]["platform"], r)
    entries = [dict(e, tools=[], status={}) for e in CATALOG]
    byid = {e["id"]: e for e in entries}
    byname = {}
    for e in entries:
        for n in [e["name"]] + e.get("aliases", []): byname.setdefault(norm(n), e)
    for t in TOOLS:  # every registry tool belongs to exactly one catalog entry (auto-created if missing)
        e = byid.get(t["id"]) or byname.get(norm(t["name"]))
        if not e:
            e = dict(id=t["id"], name=split_name(t["name"])[0], url=t.get("homepage", ""), platforms=list(t["platforms"]),
                     kind=t.get("track", "cli"), license="", blurb="", tools=[], status={})
            entries.append(e); byid[e["id"]] = e; byname[norm(t["name"])] = e
        e["tools"].append(t)
    pg = planned_gui()
    for p in pg:
        e = byname.get(norm(p["name"]))
        if not e:
            e = dict(id=re.sub(r"[^a-z0-9]+", "-", p["name"].lower()).strip("-"), name=p["name"], url="",
                     platforms=list(PLATS) if p["platform"] == "all" else [p["platform"]],
                     kind="tui" if "tui" in p["name"].lower() else "gui", license="", blurb="", tools=[], status={})
            entries.append(e); byname[norm(p["name"])] = e
        e.setdefault("planned", []).append(p)
    for e in entries:
        plats = set(e.get("platforms", []))
        for t in e["tools"]: plats |= set(t["platforms"])
        for p in e.get("planned", []): plats |= set(PLATS) if p["platform"] == "all" else {p["platform"]}
        e["platforms"] = [p for p in PLATS if p in plats]
        for plat in e["platforms"]:
            r = by_plat.get(plat)
            hit = [t for t in e["tools"] if r and any(x["tool"] == t["id"] for x in r["results"])]
            reg = [t for t in e["tools"] if plat in t["platforms"]]
            plan = [p for p in e.get("planned", []) if p["platform"] in (plat, "all")]
            if hit:
                e["status"][plat] = dict(state="bench", tool=hit[0]["id"], track=hit[0].get("track", "cli"))
            elif reg:
                t = reg[0]
                e["status"][plat] = dict(state="planned", tag="Pending",
                                         reason=t.get("notes") if t.get("status") in ("pending", "planned") or t.get("optional") else
                                         "In the benchmark harness; waiting for its first published run on this OS.")
            elif plan:
                why = plan[0]["reason"]; tag = e.get("tag") or infer_tag(why)
                e["status"][plat] = dict(state="not" if why.lower().startswith("excluded") else "planned", tag=tag, reason=why)
            else:
                rs = e.get("reason_by_os", {})
                e["status"][plat] = dict(state="not", tag=e.get("tag", "Not benchmarked"),
                                         reason=rs.get(plat, e.get("reason", "Not evaluated yet.")))
    entries.sort(key=lambda e: e["name"].lower())
    return entries

# ---------------- HTML building blocks ----------------
DARK = ("--bg:#0a0c11;--surface:#11141b;--surface2:#171b24;--fg:#e8eaf0;--mut:#a0a8b8;--line:#242a37;--acc:#a7a3ff;--acc-ink:#c9c6ff;"
        "--acc-soft:rgba(129,120,255,.14);--gui:#3fd7c2;--gui-soft:rgba(45,212,191,.12);--gold:#f5c542;--gold-ink:#ffd666;--gold-soft:rgba(245,197,66,.12);"
        "--ok:#4ade80;--ok-soft:rgba(74,222,128,.12);--warn:#fbbf24;--warn-soft:rgba(251,191,36,.12);--bar0:#7c74ff;--bar1:#b39dff;"
        "--shadow:0 1px 0 rgba(255,255,255,.03) inset,0 8px 30px rgba(0,0,0,.35);color-scheme:dark")
CSS = """
:root{--bg:#f6f7fb;--surface:#fff;--surface2:#f2f4f9;--fg:#0e1220;--mut:#535b6d;--line:#e2e5ee;--acc:#4f46e5;--acc-ink:#3730a3;--acc-soft:#eef0ff;
--gui:#0f766e;--gui-soft:#e3f5f2;--gold:#f0b400;--gold-ink:#8a5a00;--gold-soft:#fff7dc;--ok:#137a3b;--ok-soft:#e6f6ec;--warn:#b45309;--warn-soft:#fff3e2;
--bar0:#4f46e5;--bar1:#8b5cf6;--shadow:0 1px 2px rgba(16,24,40,.04),0 6px 24px rgba(16,24,40,.06);--r:16px;color-scheme:light}
[data-theme=dark]{%DARK%}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){%DARK%}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;scroll-padding-top:80px}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Inter,Roboto,"Helvetica Neue",Arial,sans-serif;-webkit-font-smoothing:antialiased}
a{color:var(--acc);text-decoration:none;text-underline-offset:3px}a:hover{text-decoration:underline}
:focus-visible{outline:2px solid var(--acc);outline-offset:2px;border-radius:6px}
code,pre,.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;font-size:.86em}
code{background:var(--surface2);border:1px solid var(--line);padding:.08em .4em;border-radius:6px}
pre{background:var(--surface2);border:1px solid var(--line);border-radius:10px;padding:12px 14px;overflow-x:auto;line-height:1.5}pre code{background:none;border:0;padding:0}
h1,h2,h3,h4{line-height:1.2;letter-spacing:-.02em;margin:0}
.skip{position:absolute;left:-999px;top:8px;background:var(--surface);padding:8px 12px;border-radius:8px;z-index:20}.skip:focus{left:8px}
.vh{position:absolute!important;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0;opacity:0}
.wrap{max-width:1120px;margin:0 auto;padding:0 24px}
/* header */
.top{position:sticky;top:0;z-index:10;background:color-mix(in srgb,var(--bg) 82%,transparent);backdrop-filter:saturate(1.6) blur(14px);-webkit-backdrop-filter:saturate(1.6) blur(14px);border-bottom:1px solid var(--line)}
.top .wrap{display:flex;align-items:center;gap:22px;height:62px}
.brand{display:flex;align-items:center;gap:10px;font-weight:750;font-size:17px;letter-spacing:-.02em;color:var(--fg);white-space:nowrap}.brand:hover{text-decoration:none}
.brand svg{flex:none}
.nav{display:flex;gap:4px;flex:1;min-width:0;overflow-x:auto;scrollbar-width:none}.nav::-webkit-scrollbar{display:none}
.nav a{color:var(--mut);font-size:14.5px;font-weight:550;padding:7px 11px;border-radius:9px;white-space:nowrap}.nav a:hover{color:var(--fg);background:var(--surface2);text-decoration:none}
.nav a[aria-current=page]{color:var(--fg);background:var(--surface2)}
.nav .gh{margin-left:auto}
.themebtn{flex:none;width:38px;height:38px;border-radius:10px;border:1px solid var(--line);background:var(--surface);color:var(--fg);cursor:pointer;display:grid;place-items:center}
.themebtn:hover{background:var(--surface2)}.themebtn[hidden]{display:none}
/* hero */
.hero{padding:56px 0 30px;display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:40px;align-items:center}
.winners{display:grid;gap:10px}.wl{margin:0 0 2px;font-size:12px;font-weight:650;text-transform:uppercase;letter-spacing:.08em;color:var(--mut)}
.wcard{display:grid;grid-template-columns:1fr auto;grid-template-rows:auto auto;align-items:center;gap:2px 12px;padding:14px 18px;color:var(--fg)}
.wcard:hover{text-decoration:none;border-color:var(--gold)}.wcard .os{grid-column:1/3;font-size:12.5px;font-weight:650;color:var(--mut);text-transform:uppercase;letter-spacing:.07em}
.wcard .wn{display:flex;align-items:center;gap:10px;font-size:19px}.wcard .rk{width:26px;height:26px;font-size:13px}
.wcard .ws{font-size:24px;font-weight:800;letter-spacing:-.02em;font-variant-numeric:tabular-nums}.wcard .ws small{font-size:13px;color:var(--mut);font-weight:700;margin-left:2px}
.eyebrow{display:inline-flex;align-items:center;gap:8px;font-size:13px;font-weight:650;color:var(--acc-ink);background:var(--acc-soft);padding:5px 12px;border-radius:999px;margin-bottom:18px}
.eyebrow .dot{width:7px;height:7px;border-radius:50%;background:var(--ok);box-shadow:0 0 0 3px var(--ok-soft)}
.hero h1{font-size:clamp(34px,5.4vw,58px);font-weight:800;letter-spacing:-.035em;max-width:16ch}
.hero h1 em{font-style:normal;background:linear-gradient(90deg,var(--bar0),var(--bar1));-webkit-background-clip:text;background-clip:text;color:transparent}
.lede{font-size:clamp(16px,1.6vw,19px);color:var(--mut);max-width:62ch;margin:16px 0 0}
.stats{display:flex;flex-wrap:wrap;gap:10px;margin-top:26px;padding:0;list-style:none}
.stats li{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:9px 14px;font-size:14px;color:var(--mut)}
.stats b{color:var(--fg);font-size:17px;margin-right:4px;font-variant-numeric:tabular-nums}
.page-h{padding:44px 0 18px}.page-h h1{font-size:clamp(28px,4vw,42px);font-weight:800;letter-spacing:-.03em}.page-h .lede{margin-top:10px}
/* callouts */
.callout{display:flex;gap:12px;align-items:flex-start;background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:12px 16px;font-size:14px;color:var(--mut);margin:0 0 14px}
.callout b{color:var(--fg)}.callout svg{flex:none;margin-top:2px}
.callout.disc{border-left:4px solid var(--gold)}.callout.gui{border-left:4px solid var(--gui);background:var(--gui-soft);color:var(--fg)}
/* cards & sections */
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--shadow)}
.section{margin:44px 0}.section>h2{font-size:24px;margin-bottom:6px}.section>.sub{color:var(--mut);margin:0 0 16px}
/* segmented tabs (radio + label, CSS only) */
.ctl{display:flex;flex-wrap:wrap;gap:10px 14px;align-items:center;justify-content:space-between;padding:14px;border-bottom:1px solid var(--line)}
.seg{display:inline-flex;background:var(--surface2);border:1px solid var(--line);border-radius:12px;padding:3px;gap:2px;max-width:100%;overflow-x:auto}
.seg label{cursor:pointer;padding:7px 14px;border-radius:9px;font-size:14.5px;font-weight:600;color:var(--mut);white-space:nowrap;user-select:none;display:inline-flex;align-items:center;gap:7px}
.seg label:hover{color:var(--fg)}
.seg label .n{font-size:12px;font-weight:650;color:var(--mut);background:var(--surface);border:1px solid var(--line);border-radius:999px;padding:0 7px}
.seg.small label{font-size:13.5px;padding:6px 11px}
.seg-l{font-size:12px;font-weight:650;color:var(--mut);text-transform:uppercase;letter-spacing:.07em;margin-right:4px}
.ctl-g{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.osp,.view{display:none}
%TABCSS%
/* leaderboard */
.panel-in{padding:6px 22px 22px}
.champ{display:flex;align-items:center;gap:14px;padding:18px 0 4px}
.champ .cup{flex:none;width:46px;height:46px;border-radius:14px;display:grid;place-items:center;background:var(--gold-soft);color:var(--gold-ink)}
.champ p{margin:0;font-size:18px;line-height:1.35}.champ p small{display:block;font-size:14px;color:var(--mut)}
.track{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin:22px 0 2px}
.track h3{font-size:19px}.track .hint{color:var(--mut);font-size:14px}
.pill{display:inline-flex;align-items:center;gap:5px;font-size:12px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;border-radius:999px;padding:2px 9px;background:var(--acc-soft);color:var(--acc-ink);white-space:nowrap}
.pill.gui{background:var(--gui-soft);color:var(--gui)}.pill.tui{background:var(--surface2);color:var(--mut)}
table.lb{width:100%;border-collapse:collapse;margin-top:8px}
.lb th{font-size:12px;font-weight:650;color:var(--mut);text-transform:uppercase;letter-spacing:.07em;text-align:left;padding:10px 12px;border-bottom:1px solid var(--line);white-space:nowrap}
.lb td{padding:13px 12px;border-bottom:1px solid var(--line);vertical-align:middle}
.lb tr:last-child td{border-bottom:0}
.lb tbody tr{transition:background .12s}.lb tbody tr:hover{background:var(--surface2)}
.lb .num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.lb td.r{width:56px}
.rk{display:inline-grid;place-items:center;width:32px;height:32px;border-radius:50%;font-weight:800;font-size:15px;color:var(--mut);background:var(--surface2);font-variant-numeric:tabular-nums}
.rk.g1{background:linear-gradient(135deg,#ffd75e,#f0a500);color:#4a3200;box-shadow:0 2px 10px rgba(240,165,0,.35)}
.rk.g2{background:linear-gradient(135deg,#eef1f6,#b9c1cf);color:#2b3240}.rk.g3{background:linear-gradient(135deg,#f3d2b4,#c9874e);color:#4a2a0e}
.lb tr.first td{background:var(--gold-soft)}
.tn{font-weight:650;font-size:16px;color:var(--fg)}.tn:hover{color:var(--acc)}
.tsub{color:var(--mut);font-size:13px;margin-left:6px}.tver{color:var(--mut);font-size:12.5px;font-variant-numeric:tabular-nums}
.tag{display:inline-block;font-size:11.5px;font-weight:650;border-radius:6px;padding:1px 7px;margin-left:6px;background:var(--surface2);color:var(--mut);border:1px solid var(--line);vertical-align:1px}
.tag.md{border-color:var(--gold);color:var(--gold-ink);background:var(--gold-soft)}
.lb td.sc{width:44%}
.scw{display:flex;align-items:center;gap:14px}
.bar{position:relative;flex:1;height:10px;border-radius:99px;background:var(--surface2);min-width:60px}
.bar i{position:absolute;left:0;top:0;bottom:0;border-radius:99px;background:linear-gradient(90deg,var(--bar0),var(--bar1))}
.first .bar i{background:linear-gradient(90deg,#f0a500,#ffd75e)}
.gui-b .bar i{background:linear-gradient(90deg,var(--gui),color-mix(in srgb,var(--gui) 55%,#fff))}
.bar b{position:absolute;top:-4px;bottom:-4px;width:2px;background:var(--fg);opacity:.35;border-radius:2px}
.sv{font-size:21px;font-weight:800;letter-spacing:-.02em;font-variant-numeric:tabular-nums;min-width:74px;text-align:right}.sv small{font-size:14px;font-weight:700;color:var(--mut)}
.tm{color:var(--mut);font-size:14px}
.acc{display:inline-flex;align-items:center;gap:5px;font-size:13.5px;font-weight:600;white-space:nowrap}
.acc.ok{color:var(--ok)}.acc.w{color:var(--warn)}
.foot{color:var(--mut);font-size:13px;margin:12px 0 0}
.empty{color:var(--mut);background:var(--surface2);border-radius:12px;padding:16px;margin-top:12px;font-size:14.5px}
.gui-box{margin-top:30px;border:1px solid color-mix(in srgb,var(--gui) 35%,var(--line));border-radius:14px;padding:4px 18px 16px;background:linear-gradient(180deg,var(--gui-soft),transparent 120px)}
/* planned list */
.plist{list-style:none;padding:0;margin:10px 0 0;display:grid;gap:8px}
.plist details{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:0}
.plist summary{cursor:pointer;padding:10px 14px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;font-weight:600;list-style:none}
.plist summary::-webkit-details-marker{display:none}
.plist summary::after{content:"";margin-left:auto;width:8px;height:8px;border-right:2px solid var(--mut);border-bottom:2px solid var(--mut);transform:rotate(45deg);transition:transform .15s}
.plist details[open] summary::after{transform:rotate(-135deg)}
.plist details p{margin:0;padding:0 14px 12px;color:var(--mut);font-size:14.5px}
/* status badges */
.st{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;font-weight:700;border-radius:999px;padding:2px 10px;white-space:nowrap}
.st::before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor}
.st.bench{background:var(--ok-soft);color:var(--ok)}.st.planned{background:var(--acc-soft);color:var(--acc-ink)}.st.not{background:var(--surface2);color:var(--mut);border:1px solid var(--line)}
.why{font-size:12.5px;font-weight:700;color:var(--warn);background:var(--warn-soft);border-radius:6px;padding:1px 8px;white-space:nowrap}
/* explainer */
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
.step{padding:20px}.step .n{display:inline-grid;place-items:center;width:30px;height:30px;border-radius:9px;background:var(--acc-soft);color:var(--acc-ink);font-weight:800;margin-bottom:10px}
.step h3{font-size:17px;margin-bottom:6px}.step p{margin:0;color:var(--mut);font-size:14.5px}
.links{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
.lk{display:block;padding:18px;color:var(--fg)}.lk:hover{text-decoration:none;border-color:var(--acc)}
.lk b{display:block;font-size:16px;margin-bottom:4px}.lk span{color:var(--mut);font-size:14px}.lk b::after{content:" →";color:var(--acc)}
/* catalog */
.cgroup{margin:8px 0 28px}.cgroup h3{font-size:18px;display:flex;align-items:center;gap:10px;margin:18px 0 12px}
.cgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px}
.prog{padding:16px 18px;display:flex;flex-direction:column;gap:8px}
.prog .ph{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.prog .ph a.name,.prog .ph span.name{font-weight:700;font-size:16.5px;color:var(--fg)}
.prog .ph .st{margin-left:auto}
.prog .meta{display:flex;flex-wrap:wrap;gap:6px 12px;font-size:13px;color:var(--mut)}
.prog .blurb{margin:0;font-size:14.5px;color:var(--mut)}
.prog .reason{margin:0;font-size:14px;background:var(--surface2);border-radius:10px;padding:9px 12px}
.prog .reason .why{margin-right:6px}
.prog .res{font-size:14px;font-weight:600}
.bgrid2{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:10px}
.bprog{display:grid;grid-template-columns:1fr auto;gap:2px 10px;padding:12px 16px;color:var(--fg);align-items:center}.bprog:hover{text-decoration:none;border-color:var(--acc)}
.bprog .bn{font-weight:700;display:flex;gap:8px;align-items:center}.bprog .br{grid-row:2;font-size:13px;color:var(--mut)}
.bprog .ws{grid-row:1/3;grid-column:2;font-size:22px;font-weight:800;font-variant-numeric:tabular-nums}.bprog .ws small{font-size:13px;color:var(--mut)}
.clist{list-style:none;margin:0;padding:0;border:1px solid var(--line);border-radius:14px;overflow:hidden;background:var(--surface)}
.crow{display:grid;grid-template-columns:minmax(0,5fr) minmax(0,7fr);gap:8px 26px;padding:14px 18px;border-top:1px solid var(--line)}.crow:first-child{border-top:0}
.crow .ph{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.crow .name{font-weight:700;font-size:16px;color:var(--fg)}a.name:hover{color:var(--acc)}
.crow .meta{display:flex;flex-wrap:wrap;gap:4px 10px;font-size:13px;color:var(--mut);margin-top:4px;align-items:center}
.crow .blurb{margin:6px 0 0;font-size:14px;color:var(--mut)}
.crow .reason{margin:0;font-size:14.5px;align-self:center}.crow .reason .why{margin-right:4px}
@media (max-width:760px){.crow{grid-template-columns:1fr}}
/* generic tables */
.tscroll{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid var(--line);border-radius:12px;background:var(--surface)}
table.dt{border-collapse:collapse;width:100%;font-size:14px}
.dt th{font-size:12px;font-weight:650;color:var(--mut);text-transform:uppercase;letter-spacing:.06em;text-align:right;padding:10px 12px;border-bottom:1px solid var(--line);background:var(--surface2);white-space:nowrap}
.dt td{padding:9px 12px;border-bottom:1px solid var(--line);text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.dt th:first-child,.dt td:first-child{text-align:left}.dt td.l,.dt th.l{text-align:left;white-space:normal}
.dt tr:last-child td{border-bottom:0}.dt .sd{color:var(--mut);font-size:12.5px}
.ok{color:var(--ok)}.bad{color:var(--warn)}.mut{color:var(--mut)}
/* tool page */
.th{display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap}
.th .facts{display:flex;flex-wrap:wrap;gap:8px 18px;color:var(--mut);font-size:14.5px;margin-top:12px}
.rcards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:22px 0 8px}
.rcard{padding:16px 18px;color:var(--fg)}.rcard:hover{text-decoration:none;border-color:var(--acc)}
.rcard .os{font-size:13px;font-weight:650;color:var(--mut);text-transform:uppercase;letter-spacing:.07em}
.rcard .big{font-size:30px;font-weight:800;letter-spacing:-.03em;font-variant-numeric:tabular-nums}.rcard .big small{font-size:16px;color:var(--mut);font-weight:700}
.rcard .of{font-size:14px;color:var(--mut)}
.kv{display:grid;grid-template-columns:max-content 1fr;gap:6px 18px;font-size:14.5px;margin:14px 0}
.kv dt{color:var(--mut)}.kv dd{margin:0;min-width:0;overflow-wrap:anywhere}
.ossec{padding:22px;margin:18px 0}.ossec>h2{font-size:22px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.ossec h3{font-size:16px;margin:22px 0 10px}
/* charts */
.charts{display:grid;grid-template-columns:1fr 1fr;gap:12px 28px}
.chart{width:100%;height:auto;font-size:12px;fill:var(--fg);overflow:visible}
.chart .ct{font-weight:650;font-size:12.5px;fill:var(--mut)}.chart .bk{fill:var(--surface2)}
.chart .b{fill:var(--bar0)}.chart .b.f{fill:var(--warn)}.chart .b.g{fill:var(--gui)}.chart .sd{stroke:var(--fg);stroke-width:1.2;opacity:.55}
.dshead{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin:26px 0 8px}.dshead h4{font-size:16px}.dshead span{color:var(--mut);font-size:13.5px}
details.more{margin:10px 0}details.more>summary{cursor:pointer;color:var(--acc);font-weight:600;font-size:14px}
/* prose (methodology) */
.doc{display:grid;grid-template-columns:220px minmax(0,1fr);gap:40px;align-items:start}
.toc{position:sticky;top:84px;font-size:14px}.toc ul{list-style:none;padding:0;margin:0}.toc li{margin:2px 0}.toc ul ul{padding-left:12px}
.toc a{color:var(--mut);display:block;padding:3px 8px;border-radius:6px}.toc a:hover{color:var(--fg);background:var(--surface2);text-decoration:none}
.toc .tl{font-size:12px;font-weight:650;text-transform:uppercase;letter-spacing:.07em;color:var(--mut);margin:0 0 6px 8px}
.prose{padding:8px 34px 30px;max-width:none}.prose h1{display:none}
.prose h2{font-size:23px;margin:34px 0 10px;padding-top:6px}.prose h3{font-size:18px;margin:24px 0 8px}
.prose p,.prose li{color:color-mix(in srgb,var(--fg) 86%,var(--bg))}.prose li{margin:4px 0}
.prose table{border-collapse:collapse;width:100%;font-size:14px;margin:14px 0;display:block;overflow-x:auto}
.prose th,.prose td{border-bottom:1px solid var(--line);padding:8px 10px;text-align:left;vertical-align:top}.prose th{background:var(--surface2);font-size:12.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--mut)}
/* badges */
.bgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:12px}
.bcard{padding:16px}.bcard h3{font-size:16px;margin-bottom:10px;display:flex;gap:8px;align-items:center}.bcard img{display:block;margin:6px 0 10px;max-width:100%}
.bcard pre{font-size:12px;white-space:pre-wrap;word-break:break-all;margin:0}
footer.ft{border-top:1px solid var(--line);margin-top:64px;padding:26px 0 44px;color:var(--mut);font-size:13.5px}
footer.ft .wrap{display:flex;flex-wrap:wrap;gap:8px 22px;justify-content:space-between}footer.ft a{color:var(--mut);text-decoration:underline}
@media (max-width:900px){.hero{grid-template-columns:1fr;gap:26px}.winners{grid-template-columns:repeat(3,1fr)}.wl{grid-column:1/-1}.grid3,.links{grid-template-columns:1fr 1fr}.doc{grid-template-columns:1fr}.toc{display:none}.charts{grid-template-columns:1fr}.lb td.sc{width:auto}}
@media (max-width:640px){
 .wrap{padding:0 16px}.top .wrap{height:auto;flex-wrap:wrap;gap:4px 10px;padding-top:10px;padding-bottom:6px}.nav{order:3;flex-basis:100%;margin:0 -8px}.themebtn{margin-left:auto}
 .nav .gh{margin-left:0}.hero{padding:34px 0 18px}.winners{gap:8px;grid-template-columns:1fr}.wcard{padding:10px 14px;grid-template-columns:78px 1fr auto;grid-template-rows:auto}.wcard .os{grid-column:auto;font-size:12px}.wcard .wn{font-size:16px;gap:8px}.wcard .ws{font-size:19px}
 .stats{gap:6px;margin-top:18px}.grid3,.links{grid-template-columns:1fr}
 .panel-in{padding:4px 12px 16px}.ctl{padding:12px}.ctl-g{width:100%}.seg-l{display:none}.seg{width:100%}.seg label{flex:1;justify-content:center;padding:7px 8px}
 .hide-sm{display:none}.lb th,.lb td{padding:11px 6px}.lb td.r{width:40px}.rk{width:28px;height:28px;font-size:14px}
 .scw{gap:8px}.sv{font-size:18px;min-width:60px}.tsub{display:none}.bar{height:8px}
 .lb .tcell{min-width:0}.tn{font-size:15px}.champ p{font-size:16px}.prose{padding:4px 18px 22px}.ossec{padding:16px}.cgrid{grid-template-columns:1fr}
 .stats li{padding:7px 11px;font-size:13px}.stats b{font-size:15px}
}
@media (min-width:641px){.show-sm{display:none}}
@media print{.top,.ctl,.themebtn{display:none}.osp,.view.view-all{display:block!important}}
"""

def tab_css():
    """CSS for radio tabs: OS panels (#os-*) and cache views (#v-*), plus active/focus label styles."""
    o = []
    for p in PLATS:
        o.append(f"#os-{p}:checked~.boards .osp-{p}{{display:block}}")
        o.append(f"#os-{p}:checked~.ctl label[for=os-{p}],#os-{p}:checked~.ctl .seg label[for=os-{p}]{{background:var(--surface);color:var(--fg);box-shadow:0 1px 3px rgba(0,0,0,.12)}}")
        o.append(f"#os-{p}:focus-visible~.ctl label[for=os-{p}]{{outline:2px solid var(--acc);outline-offset:1px}}")
    for v in ("all", "cold", "warm"):
        o.append(f"#v-{v}:checked~.boards .view-{v}{{display:block}}")
        o.append(f"#v-{v}:checked~.ctl label[for=v-{v}]{{background:var(--surface);color:var(--fg);box-shadow:0 1px 3px rgba(0,0,0,.12)}}")
        o.append(f"#v-{v}:focus-visible~.ctl label[for=v-{v}]{{outline:2px solid var(--acc);outline-offset:1px}}")
    return "\n".join(o)

JS = """(function(){var d=document,h=d.documentElement,ls;try{ls=window.localStorage}catch(e){}
function get(k){try{return ls&&ls.getItem(k)}catch(e){}}function set(k,v){try{ls&&ls.setItem(k,v)}catch(e){}}
var b=d.getElementById('theme');if(b){b.hidden=false;b.addEventListener('click',function(){var dark=h.dataset.theme?h.dataset.theme==='dark':matchMedia('(prefers-color-scheme: dark)').matches;
h.dataset.theme=dark?'light':'dark';set('dsb-theme',h.dataset.theme);});}
function group(name,key,useHash,scroll){var ins=[].slice.call(d.querySelectorAll('input[name='+name+']'));if(!ins.length)return;
var hv=useHash?decodeURIComponent(location.hash.slice(1)):'',pick=null,sv=get(key);
ins.forEach(function(i){if(hv&&(i.value===hv||(' '+(i.dataset.alias||'')+' ').indexOf(' '+hv+' ')>=0))pick=i;});
if(pick)set(key,pick.value);if(pick&&scroll){var sec=pick.closest('section');if(sec)sec.scrollIntoView({behavior:'smooth'});}
if(!pick&&sv)ins.forEach(function(i){if(i.value===sv)pick=i;});if(pick)pick.checked=true;
if(!scroll)ins.forEach(function(i){i.addEventListener('change',function(){set(key,i.value);if(useHash&&history.replaceState)history.replaceState(null,'','#'+i.value);});});}
group('os','dsb-os',true);group('view','dsb-view',false);
window.addEventListener('hashchange',function(){group('os','dsb-os',true,true);});})();
"""

ICON_LOGO = ('<svg width="30" height="30" viewBox="0 0 32 32" aria-hidden="true"><defs><linearGradient id="lg" x1="0" y1="0" x2="1" y2="1">'
             '<stop offset="0" stop-color="#6366f1"/><stop offset="1" stop-color="#a855f7"/></linearGradient></defs>'
             '<rect width="32" height="32" rx="9" fill="url(#lg)"/><rect x="7" y="17" width="4.2" height="8" rx="1.6" fill="#fff" opacity=".75"/>'
             '<rect x="13.9" y="12" width="4.2" height="13" rx="1.6" fill="#fff" opacity=".88"/><rect x="20.8" y="7" width="4.2" height="18" rx="1.6" fill="#fff"/></svg>')
ICON_THEME = ('<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">'
              '<circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 0 0 18z" fill="currentColor"/></svg>')
ICON_INFO = ('<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">'
             '<circle cx="12" cy="12" r="9.5"/><path d="M12 11v6M12 7.5v.01" stroke-linecap="round"/></svg>')
ICON_CUP = ('<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            '<path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0z"/><path d="M17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3"/></svg>')
ICON_OK = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>'
ICON_WARN = '<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2.5 1.5 21h21zM11 9h2v6h-2zm0 8h2v2h-2z"/></svg>'
FAVICON = ("data:image/svg+xml," + ICON_LOGO.replace('aria-hidden="true"', 'xmlns="http://www.w3.org/2000/svg"').replace('"', "'")
           .replace("#", "%23").replace("<", "%3C").replace(">", "%3E"))

NAV = [("index.html", "Leaderboard"), ("catalog.html", "All programs"), ("details.html", "Data & runs"),
       ("methodology.html", "Methodology"), ("badges.html", "Badges")]

def page(title, body, root="", active="", desc="Open, reproducible benchmark of disk-usage scanners and disk analyzers on macOS, Linux and Windows."):
    nav = "".join(f'<a href="{root}{h}"{" aria-current=page" if h == active else ""}>{t}</a>' for h, t in NAV)
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{E(title)}</title><meta name="description" content="{E(desc)}"><meta name="color-scheme" content="light dark">'
            f'<meta property="og:title" content="{E(title)}"><meta property="og:description" content="{E(desc)}"><meta property="og:type" content="website">'
            f'<meta name="theme-color" content="#4f46e5"><link rel="icon" href="{FAVICON}"><link rel="stylesheet" href="{root}assets/site.css">'
            f'<script>try{{var t=localStorage.getItem("dsb-theme");if(t)document.documentElement.dataset.theme=t}}catch(e){{}}</script>'
            f'<script src="{root}assets/site.js" defer></script></head><body>'
            f'<a class="skip" href="#main">Skip to content</a>'
            f'<header class="top"><div class="wrap"><a class="brand" href="{root}index.html">{ICON_LOGO}<span>diskscan-bench</span></a>'
            f'<nav class="nav" aria-label="Main">{nav}<a class="gh" href="{REPO}">GitHub ↗</a></nav>'
            f'<button class="themebtn" id="theme" type="button" aria-label="Toggle dark mode" title="Toggle dark mode" hidden>{ICON_THEME}</button></div></header>'
            f'<main id="main" class="wrap">{body}</main>'
            f'<footer class="ft"><div class="wrap"><span>Code MIT OR Apache-2.0 · results <a href="{root}results/">CC-BY-4.0 raw JSON</a> · '
            f'maintained by the maker of NullDisk (<a href="{root}methodology.html#nulldisk">disclosure</a>)</span>'
            f'<span><a href="{REPO}">Source</a> · <a href="{REPO}/issues/new?template=submit-tool.yml">Submit a tool</a> · '
            f'<a href="{REPO}/blob/main/CONTRIBUTING.md">Tune your flags</a></span></div></footer></body></html>')

def disclosure(root=""):
    return (f'<p class="callout disc">{ICON_INFO}<span><b>Disclosure:</b> diskscan-bench is maintained by Michael Wirth, who also makes '
            '<a href="https://nulldisk.app">NullDisk</a>, a commercial macOS disk analyzer whose CLI is one of the benchmarked tools. '
            'Everything (harness, flags, datasets, raw data) is public, and tool authors can tune their own flags via pull request.</span></p>')

def noise(root=""):
    return (f'<p class="callout">{ICON_INFO}<span><b>Indicative numbers.</b> Runs use GitHub-hosted runners (shared VMs, virtualised disks). '
            'Compare tools within one OS and run, not across runs or as absolute hardware truth. '
            f'<a href="{root}methodology.html">Methodology</a></span></p>')

def rank_badge(i):
    return f'<span class="rk{" g%d" % i if i <= 3 else ""}" aria-label="Rank {i}">{i}</span>'

def kind_pill(k):
    return f'<span class="pill {E(k)}">{KIND.get(k, k.upper())}</span>'

def status_badge(state):
    return {"bench": '<span class="st bench">Benchmarked</span>', "planned": '<span class="st planned">Planned</span>',
            "not": '<span class="st not">Not benchmarked</span>'}[state]

def bars(rows, title, gui=False):
    """rows: [(label, median, stddev, flag)] -> responsive inline SVG horizontal bar chart (fastest first)."""
    rows = [r for r in rows if r[1] is not None]
    if not rows: return ""
    rows.sort(key=lambda r: r[1]); mx = max(r[1] + (r[2] or 0) for r in rows) or 1
    W, lw, h, rw = 520, 150, 24, 74; H = 26 + h * len(rows); pw = W - lw - rw
    o = [f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="{E(title)}"><title>{E(title)}</title><text x="0" y="14" class="ct">{E(title)}</text>']
    for i, (lab, med, sd, flag) in enumerate(rows):
        y = 24 + i * h; w = pw * med / mx
        o.append(f'<text x="{lw-8}" y="{y+15}" text-anchor="end">{E(lab)}{" *" if flag else ""}</text>'
                 f'<rect x="{lw}" y="{y+4}" width="{pw}" height="{h-9}" rx="4" class="bk"/>'
                 f'<rect x="{lw}" y="{y+4}" width="{max(w,2):.1f}" height="{h-9}" rx="4" class="b{" f" if flag else (" g" if gui else "")}"/>')
        if sd:
            x1 = lw + pw * max(med - sd, 0) / mx; x2 = lw + pw * (med + sd) / mx
            o.append(f'<line x1="{x1:.1f}" x2="{x2:.1f}" y1="{y+11.5}" y2="{y+11.5}" class="sd"/>')
        o.append(f'<text x="{lw+pw+8}" y="{y+15}">{fmt_t(med)}</text>')
    o.append("</svg>")
    return "".join(o)

def badge(left, right, color="#4c7"):
    lw, rw = 7 * len(left) + 12, 7 * len(right) + 12
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{lw+rw}" height="20" role="img" aria-label="{E(left)}: {E(right)}">'
            f'<clipPath id="r"><rect width="{lw+rw}" height="20" rx="3"/></clipPath><g clip-path="url(#r)">'
            f'<rect width="{lw}" height="20" fill="#3b3f4a"/><rect x="{lw}" width="{rw}" height="20" fill="{color}"/></g>'
            f'<g fill="#fff" font-family="Verdana,DejaVu Sans,sans-serif" font-size="11">'
            f'<text x="6" y="14">{E(left)}</text><text x="{lw+6}" y="14">{E(right)}</text></g></svg>')

def rich(t):
    """Escape text and render `backticks` as inline code."""
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", E(t or ""))

def ratio_cls(x): return "ok" if x >= 1 else "mut"

# ---------------- pages ----------------
class Site:
    def __init__(self):
        self.runs, self.latest = load()
        self.by_plat = {}
        for label, r in sorted(self.latest.items()):
            self.by_plat.setdefault(r["runner"]["platform"], (label, r))
        self.order = [p for p in PLATS if p in self.by_plat]
        self.default_os = "linux" if "linux" in self.order else (self.order[0] if self.order else "linux")
        self.catalog = build_catalog(self.latest)
        self.cat_by_tool = {t["id"]: e for e in self.catalog for t in e["tools"]}
        # official (both modes) ranking per platform/track, used everywhere a rank is quoted
        self.rank = {}
        for p in self.order:
            label, r = self.by_plat[p]
            for track in self.tracks(r):
                sc, base, bad = scores(r, track)
                for i, d in enumerate(sc, 1):
                    self.rank[(p, d["tool"])] = dict(d, rank=i, of=len(sc), track=track, base=base, label=label)

    def tracks(self, r):
        ts = list(dict.fromkeys(x.get("track", "cli") for x in r["results"]))
        return sorted(ts, key=lambda t: (t != "cli", t))

    def tool_name(self, r, tid):
        return (r["tools"].get(tid) or {}).get("name", tid)

    def write(self, rel, s):
        f = os.path.join(OUT, rel); os.makedirs(os.path.dirname(f), exist_ok=True)
        open(f, "w").write(s)

    # ---------- leaderboard ----------
    def os_radios(self, counts=None):
        o = []
        for p in self.order:
            label = self.by_plat[p][0]
            o.append(f'<input class="vh" type="radio" name="os" id="os-{p}" value="{p}" data-alias="{E(label)}"'
                     f'{" checked" if p == self.default_os else ""}>')
        return "".join(o)

    def os_seg(self, counts=None):
        return ('<div class="ctl-g"><span class="seg-l" id="os-l">OS</span><div class="seg" role="group" aria-labelledby="os-l">' +
                "".join(f'<label for="os-{p}">{PLAT_NAME[p]}{f" <span class=n>{counts[p]}</span>" if counts else ""}</label>' for p in self.order) +
                "</div></div>")

    def board(self, p, r, track, view):
        modes = {"all": ("cold", "warm"), "cold": ("cold",), "warm": ("warm",)}[view]
        if view != "all" and not r["cache_modes"].get(view):
            return (f'<p class="empty">Cold-cache runs aren\'t measured on {PLAT_NAME[p]} yet ({E(r.get("cold_method", ""))}). '
                    f'Switch to <i>Overall</i> or <i>Warm cache</i>.</p>')
        sc, base, bad = scores(r, track, modes)
        if not sc: return '<p class="empty">No ranked results in this view.</p>'
        tv = r["tools"]; top = sc[0]["score"]; gui = track != "cli"
        tcols = tuple((m, m.title()) for m in ("cold", "warm") if r["cache_modes"].get(m)) if view == "all" else ((view, "Time"),)
        h = [f'<table class="lb{" gui-b" if gui else ""}"><thead><tr><th scope="col">#</th><th scope="col">{"App" if gui else "Tool"}</th>'
             f'<th scope="col">Speed vs <span class="mono">{E(split_name(self.tool_name(r, base))[0])}</span></th>' +
             "".join(f'<th scope="col" class="num hide-sm">{t}</th>' for _, t in tcols) +
             '<th scope="col" class="hide-sm">Accuracy</th></tr></thead><tbody>']
        for i, d in enumerate(sc, 1):
            t = tv.get(d["tool"], {"name": d["tool"]}); nm, sub = split_name(t["name"]); ver = short_ver(t.get("version"))
            tags = ""
            if d["tool"] == base: tags += '<span class="tag">baseline</span>'
            if d["tool"] == "nulldisk": tags += '<span class="tag md" title="Made by this benchmark\'s maintainer">maintainer\'s tool</span>'
            acc = (f'<a class="acc w" href="tools/{E(d["tool"])}.html#{p}-correctness" title="{E("Differs from reference: " + "; ".join(d["warn"]))}">{ICON_WARN}Differs</a>'
                   if d["warn"] else f'<span class="acc ok" title="Totals match the reference walker">{ICON_OK}Exact</span>')
            acc_sm = f' <a class="acc w show-sm" href="tools/{E(d["tool"])}.html#{p}-correctness" aria-label="Accuracy differs">{ICON_WARN}</a>' if d["warn"] else ""
            bw = 100 * d["score"] / top
            mark = f'<b style="left:{100 / top:.1f}%" title="{E(base)} = 1.00×"></b>' if top > 1.05 and d["tool"] != base else ""
            h.append(f'<tr class="{"first" if i == 1 else ""}"><td class="r">{rank_badge(i)}</td>'
                     f'<td class="tcell"><a class="tn" href="tools/{E(d["tool"])}.html#{p}">{E(nm)}</a>{f"<span class=tsub>{E(sub)}</span>" if sub else ""}{acc_sm}'
                     f'<div class="tver">{E(ver)}{tags}</div></td>'
                     f'<td class="sc"><div class="scw"><div class="bar" aria-hidden="true"><i style="width:{bw:.1f}%"></i>{mark}</div>'
                     f'<span class="sv">{d["score"]:.2f}<small>×</small></span></div></td>' +
                     "".join(f'<td class="num hide-sm tm">{fmt_t(d[m])}</td>' for m, _ in tcols) +
                     f'<td class="hide-sm">{acc}</td></tr>')
        h.append("</tbody></table>")
        cells = sc[0]["cells"]
        h.append(f'<p class="foot">Score = geometric mean of <span class="mono">{E(base)}</span> time ÷ tool time over {cells} dataset × cache '
                 f'cell{"s" if cells != 1 else ""}; {E(split_name(self.tool_name(r, base))[0])} = 1.00×, higher is faster. '
                 'Times = geometric mean of the median times. '
                 + (f'Held out of scoring (reference under review): {E(", ".join(sorted(bad)))}. ' if bad else "")
                 + "</p>")
        return "".join(h)

    def champion(self, p, r):
        sc, base, bad = scores(r, "cli")
        if not sc: return ""
        d = sc[0]; nm = split_name(self.tool_name(r, d["tool"]))[0]; bn = split_name(self.tool_name(r, base))[0]
        if d["tool"] == base: line = f"<b>{E(nm)}</b> leads on {PLAT_NAME[p]}"
        else: line = f'<b><a href="tools/{E(d["tool"])}.html#{p}">{E(nm)}</a></b> is the fastest CLI scanner on {PLAT_NAME[p]}: <b>{d["score"]:.2f}×</b> the speed of {E(bn)}'
        ri = r["runner"]
        return (f'<div class="champ"><div class="cup">{ICON_CUP}</div><p>{line}'
                f'<small>{E(r["_date"])} · {E(str(ri.get("cpu_model")))} · {ri.get("cpus")} vCPU · {E(str(ri.get("filesystem")))} · '
                f'<a href="details.html#{p}">run details</a></small></p></div>')

    def planned_list(self, p, gui_only=True):
        items = [(e, e["status"][p]) for e in self.catalog if p in e["status"] and e["status"][p]["state"] != "bench"
                 and (e.get("kind") == "gui" or not gui_only)]
        items = [x for x in items if x[1]["state"] == "planned" or x[0].get("planned")]
        if not items: return ""
        return ('<ul class="plist">' + "".join(
            f'<li><details><summary>{E(e["name"])} <span class="why">{E(s["tag"])}</span>{status_badge(s["state"])}</summary><p>{rich(s["reason"])}</p></details></li>'
            for e, s in items) + "</ul>")

    def leaderboard(self):
        n_bench = len({d for (p, d) in self.rank})
        n_cat = len(self.catalog)
        dates = sorted(r["_date"] for _, r in self.by_plat.values())
        nds = len({ds for _, r in self.by_plat.values() for ds in r["datasets"]})
        win = []
        for p in self.order:
            label, r = self.by_plat[p]; sc, base, _ = scores(r, "cli")
            if sc:
                d = sc[0]
                win.append(f'<a class="card wcard" href="#{p}">'
                           f'<span class="os">{PLAT_NAME[p]}</span><span class="wn">{rank_badge(1)}<b>{E(split_name(self.tool_name(r, d["tool"]))[0])}</b></span>'
                           f'<span class="ws">{d["score"]:.2f}<small>× du</small></span></a>')
        h = [f'<section class="hero"><div class="hero-t"><span class="eyebrow"><span class="dot"></span>Latest run {E(dates[-1] if dates else "–")}</span>'
             '<h1>Which disk scanner is <em>fastest?</em></h1>'
             '<p class="lede">We time command-line scanners and GUI disk analyzers on the same files on macOS, Linux and Windows, '
             'with cold and warm caches, and check every reported total against a reference walker.</p>'
             f'<ul class="stats"><li><b>{n_bench}</b>tools ranked</li><li><b>{n_cat}</b>programs catalogued</li>'
             f'<li><b>{len(self.order)}</b>operating systems</li><li><b>{nds}</b>datasets</li></ul></div>'
             + (f'<div class="winners"><p class="wl">Fastest CLI scanner per OS</p>{"".join(win)}</div>' if win else "") + '</section>',
             disclosure()]
        h.append('<section class="card" aria-label="Leaderboard">' + self.os_radios() +
                 '<input class="vh" type="radio" name="view" id="v-all" value="all" checked>'
                 '<input class="vh" type="radio" name="view" id="v-cold" value="cold">'
                 '<input class="vh" type="radio" name="view" id="v-warm" value="warm">'
                 '<div class="ctl">' + self.os_seg() +
                 '<div class="ctl-g"><span class="seg-l" id="v-l">Cache</span><div class="seg small" role="group" aria-labelledby="v-l">'
                 '<label for="v-all">Overall</label><label for="v-cold">Cold</label><label for="v-warm">Warm</label></div></div></div>'
                 '<div class="boards">')
        for p in self.order:
            label, r = self.by_plat[p]
            h.append(f'<div class="osp osp-{p}"><div class="panel-in">{self.champion(p, r)}')
            tracks = self.tracks(r)
            for track in [t for t in tracks if t == "cli"]:
                h.append('<div class="track"><h3>Command-line tools</h3><span class="hint">ranked against each other</span></div>')
                for v in ("all", "cold", "warm"):
                    h.append(f'<div class="view view-{v}">{self.board(p, r, track, v)}</div>')
            gtracks = [t for t in tracks if t != "cli"]
            plan = self.planned_list(p)
            h.append('<div class="gui-box"><div class="track"><h3>GUI apps</h3><span class="pill gui">separate ranking</span></div>'
                     f'<p class="callout gui">{ICON_INFO}<span><b>Only compare GUI apps with each other.</b> GUI times run from app launch until '
                     'the app\'s own export finishes and it exits, so they include start-up and are not comparable with the CLI table above.</span></p>')
            for track in gtracks:
                for v in ("all", "cold", "warm"):
                    h.append(f'<div class="view view-{v}">{self.board(p, r, track, v)}</div>')
            if not gtracks:
                h.append(f'<p class="empty">No GUI app on {PLAT_NAME[p]} can be scripted to scan and exit on hosted runners yet. Planned:</p>')
            elif plan:
                h.append('<p class="foot" style="margin-top:18px"><b>Not yet benchmarked here:</b></p>')
            h.append(plan)
            n_not = sum(1 for e in self.catalog if p in e["status"] and e["status"][p]["state"] != "bench")
            h.append(f'<p class="foot">{n_not} known {PLAT_NAME[p]} programs aren\'t benchmarked yet. '
                     f'<a href="catalog.html#{p}">See every program and why →</a></p></div>')
            h.append("</div></div>")
        h.append("</div></section>")
        h.append(noise())
        h.append('<section class="section"><h2>How the score works</h2><p class="sub">One number per tool, computed the same way on every OS.</p><div class="grid3">'
                 '<div class="card step"><span class="n">1</span><h3>Same files, every tool</h3><p>Seeded synthetic trees (150k tiny files, deep chains, huge folders, hard links, sparse files) '
                 'plus real-world node_modules and the Linux kernel source.</p></div>'
                 '<div class="card step"><span class="n">2</span><h3>Relative to <code>du</code></h3><p>Each cell is <i>du time ÷ tool time</i>; the score is the geometric mean over every dataset '
                 'with cold and warm cache. 2.00× = twice as fast as du.</p></div>'
                 '<div class="card step"><span class="n">3</span><h3>Totals are checked</h3><p>Every reported size is compared with a reference walker. '
                 'Differences are flagged (usually a definition, e.g. hard links), never hidden.</p></div></div></section>')
        h.append('<section class="section"><h2>Explore</h2><div class="links">'
                 f'<a class="card lk" href="catalog.html"><b>All programs</b><span>{n_cat} disk analyzers, incl. the ones we can\'t benchmark, and why.</span></a>'
                 '<a class="card lk" href="details.html"><b>Data &amp; runs</b><span>Per-dataset charts, runner specs, correctness tables.</span></a>'
                 '<a class="card lk" href="methodology.html"><b>Methodology</b><span>Cache modes, datasets, scoring and correctness rules.</span></a>'
                 '<a class="card lk" href="badges.html"><b>Badges</b><span>Embed your tool\'s rank in a README.</span></a></div></section>')
        self.write("index.html", page("diskscan-bench: disk-usage scanner leaderboard", "".join(h), active="index.html"))

    # ---------- tool detail pages ----------
    def tool_pages(self):
        tids = list(dict.fromkeys(x["tool"] for _, r in self.by_plat.values() for x in r["results"]))
        for tid in tids:
            e = self.cat_by_tool.get(tid, {}); reg = next((t for t in TOOLS if t["id"] == tid), {})
            first = next(r["tools"][tid] for _, r in self.by_plat.values() if tid in r["tools"])
            nm, sub = split_name(first["name"]); track = first.get("track", "cli")
            plats = [p for p in self.order if tid in self.by_plat[p][1]["tools"]]
            h = [f'<section class="page-h"><div class="th"><div style="flex:1;min-width:260px"><p style="margin:0 0 8px"><a href="../index.html">← Leaderboard</a></p>'
                 f'<h1>{E(nm)} {kind_pill(e.get("kind") or track)}</h1>' + (f'<p class="lede">{rich(e["blurb"])}</p>' if e.get("blurb") else (f'<p class="lede">{E(sub)}</p>' if sub else "")) +
                 '<div class="facts">' + (f'<span><a href="{E(first.get("homepage") or e.get("url", ""))}">Homepage ↗</a></span>' if (first.get("homepage") or e.get("url")) else "") +
                 (f'<span>License: {E(e["license"])}</span>' if e.get("license") else "") +
                 f'<span>{"GUI track" if track != "cli" else "CLI track"}</span><span>Runs on: {", ".join(PLAT_NAME[p] for p in plats)}</span></div></div></div></section>']
            if tid == "nulldisk": h.append(disclosure("../"))
            if track != "cli":
                h.append(f'<p class="callout gui">{ICON_INFO}<span><b>GUI track.</b> Times run from app launch until its export finishes and it exits; '
                         'compare only with other GUI apps.</span></p>')
            h.append('<div class="rcards">')
            for p in plats:
                rk = self.rank.get((p, tid))
                if rk:
                    h.append(f'<a class="card rcard" href="#{p}"><div class="os">{PLAT_NAME[p]} · {"GUI" if rk["track"] != "cli" else "CLI"}</div>'
                             f'<div class="big">#{rk["rank"]} <small>of {rk["of"]}</small></div><div class="of">{rk["score"]:.2f}× vs {E(rk["base"])}'
                             f'{" · ⚠ totals differ" if rk["warn"] else " · ✓ exact"}</div></a>')
                else:
                    h.append(f'<a class="card rcard" href="#{p}"><div class="os">{PLAT_NAME[p]}</div><div class="big">–</div><div class="of">not ranked (too few valid cells)</div></a>')
            h.append("</div>")
            for p in plats:
                label, r = self.by_plat[p]; t = r["tools"][tid]; base = BASELINE[p]; bad = suspect_datasets(r)
                cmd = " ".join(t["cmd"])
                h.append(f'<section class="card ossec" id="{p}"><h2>{PLAT_NAME[p]} <span class="tver">{E(r["_date"])} · {E(label)}</span></h2>'
                         '<dl class="kv">'
                         f'<dt>Version</dt><dd>{E(re.sub(r"^version:\s*", "", str(t.get("version") or "–"), flags=re.I))}' + (f' <span class="mut">(pinned {E(str(t["pin"]))})</span>' if t.get("pin") else "") + '</dd>'
                         f'<dt>Command</dt><dd><code>{E(cmd)}</code></dd>'
                         f'<dt>Reports</dt><dd>{E(t.get("metric") or "–")} bytes</dd>'
                         + (f'<dt>Method</dt><dd>{E(t["method"])}</dd>' if t.get("method") else "")
                         + (f'<dt>Notes</dt><dd>{E(t["notes"])}</dd>' if t.get("notes") else "")
                         + f'<dt>Runner</dt><dd>{E(str(r["runner"].get("cpu_model")))}, {r["runner"].get("cpus")} vCPU, {E(str(r["runner"].get("filesystem")))} · '
                         f'<a href="../{E(r["_path"])}">raw JSON</a></dd></dl>')
                rows = [x for x in r["results"] if x["tool"] == tid]
                bmap = {x["dataset"]: x for x in r["results"] if x["tool"] == base}
                ms = [m for m in ("cold", "warm") if r["cache_modes"].get(m)]
                h.append('<h3>Times per dataset</h3><div class="tscroll"><table class="dt"><thead><tr><th>Dataset</th>' +
                         "".join(f'<th>{m.title()} median</th>' for m in ms) + "".join(f'<th>{m.title()} vs {E(base)}</th>' for m in ms) +
                         '<th>Peak RSS</th></tr></thead><tbody>')
                for x in rows:
                    ds = x["dataset"]; bx = bmap.get(ds, {})
                    def tcell(m):
                        mm = x.get(m) or {}
                        if not valid(mm): return '<td class="mut">' + ("n/a" if not r["cache_modes"].get(m) else "invalid" if mm else "–") + "</td>"
                        return f'<td>{fmt_t(mm["median_s"])} <span class="sd">±{fmt_t(mm.get("stddev_s"))}</span></td>'
                    def rcell(m):
                        if valid(x.get(m)) and valid(bx.get(m)):
                            q = bx[m]["median_s"] / x[m]["median_s"]; return f'<td class="{ratio_cls(q)}">{q:.2f}×</td>'
                        return '<td class="mut">–</td>'
                    held = f' <span class="tag" title="held out of scoring">not scored</span>' if ds in bad else ""
                    h.append(f'<tr><td><span class="mono">{E(ds)}</span>{held}</td>{"".join(map(tcell, ms))}{"".join(map(rcell, ms))}<td>{fmt_b(x.get("peak_rss_bytes"))}</td></tr>')
                h.append('</tbody></table></div>' + ("" if "cold" in ms else f'<p class="foot">Cold cache isn\'t measured on {PLAT_NAME[p]} yet.</p>'))
                h.append(f'<h3 id="{p}-correctness">Correctness</h3><div class="tscroll"><table class="dt"><thead><tr><th>Dataset</th><th>Reported</th><th>Reference</th>'
                         '<th>Diff</th><th class="l">Verdict</th></tr></thead><tbody>')
                for x in rows:
                    c = x.get("correctness") or {}
                    if c.get("status") == "agrees": v = f'<span class="ok">✓ matches</span>'
                    elif c.get("status") == "disagrees":
                        cs = c.get("closest_semantics"); v = '<span class="bad">⚠ differs</span>' + (f' <span class="mut">· closest: {E(SEMANTICS.get(cs, str(cs)))}</span>' if cs else "")
                        if x["dataset"] in bad: v += ' <span class="mut">· dataset held out of scoring</span>'
                    else: v = f'<span class="mut">{E(c.get("note", c.get("status", "–")))}</span>'
                    dp = c.get("diff_pct")
                    h.append(f'<tr><td><span class="mono">{E(x["dataset"])}</span></td><td>{fmt_b(x.get("reported_bytes"))}</td><td>{fmt_b(c.get("reference_value"))}</td>'
                             f'<td>{"–" if dp is None else f"{dp:+.2f}%"}</td><td class="l">{v}</td></tr>')
                h.append('</tbody></table></div>')
                ref = "logical_dedup" if p == "windows" else "alloc_du"
                h.append(f'<p class="foot">Reference = <span class="mono">{ref}</span> ({E(SEMANTICS[ref])}). Within 0.1% counts as a match '
                         '(6% for tools that only print human-readable sizes). <a href="../methodology.html#correctness">Rules</a></p></section>')
            self.write(f"tools/{tid}.html", page(f"{nm} · diskscan-bench", "".join(h), root="../",
                                                  desc=f"{nm}: benchmark results, versions, commands and correctness on diskscan-bench."))

    # ---------- catalog ----------
    def catalog_page(self):
        counts = {p: sum(1 for e in self.catalog if p in e["status"]) for p in self.order}
        n = len(self.catalog)
        nb = sum(1 for e in self.catalog if any(s["state"] == "bench" for s in e["status"].values()))
        h = ['<section class="page-h"><h1>Every disk analyzer we know of</h1>'
             f'<p class="lede">{n} programs across macOS, Linux and Windows: command-line scanners, terminal UIs and GUI apps. {nb} are benchmarked; '
             'for everything else we say why not (licence, no way to detect when a scan finishes, unmaintained, out of scope). '
             f'Missing one? <a href="{REPO}/issues/new?template=submit-tool.yml">Tell us</a>.</p></section>',
             '<p class="callout">' + ICON_INFO + '<span><b>Licence first.</b> A program is only benchmarked if its licence allows automated use on CI '
             f'(or the vendor agrees publicly) and it can scan a folder and signal completion without a human. See the <a href="{REPO}/blob/main/CONTRIBUTING.md">inclusion rules</a>.</span></p>',
             '<section class="card">' + self.os_radios() + '<div class="ctl">' + self.os_seg(counts) +
             '<div class="ctl-g"><span class="st bench">Benchmarked</span><span class="st planned">Planned</span><span class="st not">Not benchmarked</span></div></div><div class="boards">']
        for p in self.order:
            h.append(f'<div class="osp osp-{p}"><div class="panel-in">')
            for state, title in (("bench", "Benchmarked"), ("planned", "Planned"), ("not", "Not benchmarked")):
                es = [e for e in self.catalog if p in e["status"] and e["status"][p]["state"] == state]
                if state == "bench": es.sort(key=lambda e: (self.rank.get((p, e["status"][p]["tool"]), {}).get("track", "z"),
                                                            self.rank.get((p, e["status"][p]["tool"]), {}).get("rank", 99)))
                if not es: continue
                if state == "not": es.sort(key=lambda e: (-sum(1 for f in es if f["status"][p]["tag"] == e["status"][p]["tag"]), e["status"][p]["tag"], e["name"].lower()))
                h.append(f'<div class="cgroup"><h3>{status_badge(state)} <span>on {PLAT_NAME[p]}</span> <span class="tver">{len(es)}</span></h3>')
                if state == "not":
                    tags = list(dict.fromkeys(e["status"][p]["tag"] for e in es))
                    h.append('<p class="foot" style="margin:-4px 0 12px">By reason: ' + " · ".join(
                        f'{E(t)} <b>{sum(1 for e in es if e["status"][p]["tag"] == t)}</b>' for t in tags) + "</p>")
                h.append('<div class="bgrid2">' if state == "bench" else '<ul class="clist">')
                for e in es:
                    s = e["status"][p]
                    link = f'<a class="name" href="{E(e["url"])}">{E(e["name"])}</a>' if e.get("url") else f'<span class="name">{E(e["name"])}</span>'
                    meta = [kind_pill(e.get("kind", "cli"))]
                    if e.get("license"): meta.append(f'<span>{E(e["license"])}</span>')
                    others = [PLAT_NAME[q] for q in e["platforms"] if q != p]
                    if others: meta.append(f'<span>also {", ".join(others)}</span>')
                    if state == "bench":
                        rk = self.rank.get((p, s["tool"]))
                        res = (f'#{rk["rank"]} of {rk["of"]} {"GUI apps" if rk["track"] != "cli" else "CLI tools"}' if rk else "Results")
                        sc = f'<span class="ws">{rk["score"]:.2f}<small>×</small></span>' if rk else ""
                        h.append(f'<a class="card bprog" href="tools/{E(s["tool"])}.html#{p}"><span class="bn">{E(e["name"])} {kind_pill(e.get("kind", "cli"))}</span>'
                                 f'<span class="br">{res}</span>{sc}</a>')
                    else:
                        why = s["reason"]
                        why = re.sub(r"^" + re.escape(s["tag"]) + r"\s*[:.-]\s*", "", why, flags=re.I)
                        blurb = f'<p class="blurb">{rich(e["blurb"])}</p>' if e.get("blurb") else ""
                        h.append(f'<li class="crow"><div class="ci"><div class="ph">{link}</div><div class="meta">{"".join(meta)}</div>{blurb}</div>'
                                 f'<p class="reason"><span class="why">{E(s["tag"])}</span> {rich(why)}</p></li>')
                h.append("</div></div>" if state == "bench" else "</ul></div>")
            h.append("</div></div>")
        h.append("</div></section>")
        self.write("catalog.html", page("All disk analyzers · diskscan-bench", "".join(h), active="catalog.html",
                                        desc="Every known disk-usage analyzer for macOS, Linux and Windows, with benchmark status and the reason when not benchmarked."))

    # ---------- details (data & runs) ----------
    def details(self):
        h = ['<section class="page-h"><h1>Data &amp; runs</h1><p class="lede">Everything behind the leaderboard: runner specs, datasets, '
             'per-dataset timings for every tool, and the full correctness matrix. Raw numbers are in the JSON.</p></section>', noise(),
             '<section class="card">' + self.os_radios() + '<div class="ctl">' + self.os_seg() + '</div><div class="boards">']
        for p in self.order:
            label, r = self.by_plat[p]; ri = r["runner"]; tv = r["tools"]; bad = suspect_datasets(r)
            run = ri.get("github_run")
            h.append(f'<div class="osp osp-{p}"><div class="panel-in"><h2 style="margin-top:18px;font-size:22px">{PLAT_NAME[p]} <span class="tver">{E(label)}</span></h2>'
                     '<dl class="kv">'
                     f'<dt>Run</dt><dd>{E(r["_date"])} · profile <b>{E(r["profile"])}</b>' + (f' · <a href="{REPO}/actions/runs/{E(str(run))}">GitHub run {E(str(run))}</a>' if run else "") +
                     f' · <a href="{E(r["_path"])}">raw JSON</a></dd>'
                     f'<dt>Machine</dt><dd>{E(str(ri.get("cpu_model")))} · {ri.get("cpus")} vCPU · {fmt_b(ri.get("mem_bytes"))} RAM</dd>'
                     f'<dt>OS / FS</dt><dd>{E(str(ri.get("os")))} · {E(str(ri.get("filesystem")))} · image {E(str(ri.get("image")))} {E(str(ri.get("image_version")))}</dd>'
                     f'<dt>Cold cache</dt><dd>{E(r.get("cold_method", ""))}</dd>' + (f'<dt>Commit</dt><dd><a href="{REPO}/commit/{E(ri["commit"])}" class="mono">{E(ri["commit"][:10])}</a></dd>' if ri.get("commit") else "") +
                     '</dl>')
                     # datasets
            h.append('<h3 style="margin:22px 0 10px">Datasets</h3><div class="tscroll"><table class="dt"><thead><tr><th>Dataset</th><th>Files</th><th>Dirs</th><th>Logical</th>'
                     '<th>Allocated</th><th>Manifest</th><th class="l">Scoring</th></tr></thead><tbody>')
            for ds, d in r["datasets"].items():
                why = EXCLUDE_SCORING.get((p, ds), "reference suspect (see methodology)") if ds in bad else ""
                h.append(f'<tr><td class="mono">{E(ds)}</td><td>{d["files"]:,}</td><td>{d["dirs"]:,}</td><td>{fmt_b(d.get("logical_dedup"))}</td><td>{fmt_b(d.get("alloc_du"))}</td>'
                         f'<td class="mono">{E(d.get("manifest_sha256", "")[:12])}</td><td class="l">{"<span class=bad>held out</span> <span class=mut>· " + E(why) + "</span>" if why else "<span class=ok>scored</span>"}</td></tr>')
            h.append('</tbody></table></div>')
            for track in self.tracks(r):
                trs = [x for x in r["results"] if x.get("track", "cli") == track]
                gui = track != "cli"
                h.append(f'<h3 style="margin:30px 0 4px">{"GUI apps" if gui else "Command-line tools"} · per-dataset times</h3>'
                         + (f'<p class="callout gui">{ICON_INFO}<span>GUI track: launch-to-exit times including the app\'s own export; compare GUI apps only with each other.</span></p>' if gui else
                            '<p class="foot" style="margin-top:0">Median per tool, whiskers ±1 stddev, fastest first. <span class="bad">Orange / *</span> = total disagrees with the reference walker.</p>'))
                for ds, d in r["datasets"].items():
                    rows = [x for x in trs if x["dataset"] == ds]
                    if not rows: continue
                    h.append(f'<div class="dshead"><h4 class="mono">{E(ds)}</h4><span>{d["files"]:,} files · {d["dirs"]:,} dirs · {fmt_b(d.get("logical_dedup"))} logical'
                             f'{" · held out of scoring" if ds in bad else ""}</span></div><div class="charts">')
                    for mode in ("cold", "warm"):
                        if not r["cache_modes"].get(mode): continue
                        pts = [(split_name(tv[x["tool"]]["name"])[0], (x.get(mode) or {}).get("median_s") if valid(x.get(mode)) else None,
                                (x.get(mode) or {}).get("stddev_s"), (x.get("correctness") or {}).get("status") == "disagrees") for x in rows]
                        h.append(f"<div>{bars(pts, f'{mode} cache', gui)}</div>")
                    h.append("</div>")
                    h.append('<details class="more"><summary>All numbers</summary><div class="tscroll"><table class="dt"><thead><tr><th>Tool</th><th>Cold median</th><th>±sd</th>'
                             '<th>Warm median</th><th>±sd</th><th>Peak RSS</th><th>Reported total</th></tr></thead><tbody>' +
                             "".join(f'<tr><td><a href="tools/{E(x["tool"])}.html#{p}">{E(tv[x["tool"]]["name"])}</a></td><td>{fmt_t((x.get("cold") or {}).get("median_s"))}</td>'
                                     f'<td class="sd">{fmt_t((x.get("cold") or {}).get("stddev_s"))}</td><td>{fmt_t((x.get("warm") or {}).get("median_s"))}</td>'
                                     f'<td class="sd">{fmt_t((x.get("warm") or {}).get("stddev_s"))}</td><td>{fmt_b(x.get("peak_rss_bytes"))}</td><td>{fmt_b(x.get("reported_bytes"))}</td></tr>' for x in rows) +
                             '</tbody></table></div></details>')
            # correctness matrix
            h.append(f'<h3 id="correctness-{p}" style="margin:34px 0 4px">Correctness: reported total vs reference walker</h3>'
                     f'<p class="foot" style="margin-top:0">Diff vs <span class="mono">{"logical_dedup" if p == "windows" else "alloc_du"}</span> '
                     f'({E(SEMANTICS["logical_dedup" if p == "windows" else "alloc_du"])}). Disagreement is flagged, never excluded.</p>'
                     '<div class="tscroll"><table class="dt"><thead><tr><th>Tool</th>' + "".join(f'<th>{E(ds)}</th>' for ds in r["datasets"]) + '</tr></thead><tbody>')
            for tid, v in tv.items():
                cells = []
                for ds in r["datasets"]:
                    x = next((y for y in r["results"] if y["tool"] == tid and y["dataset"] == ds), None)
                    c = (x or {}).get("correctness")
                    if not c: cells.append("<td class=mut>–</td>"); continue
                    if c["status"] == "agrees": cells.append(f"<td class='ok'>✓ {c['diff_pct']:+.2f}%</td>")
                    elif c["status"] == "disagrees": cells.append(f"<td class='bad' title='closest: {E(SEMANTICS.get(c.get('closest_semantics'), str(c.get('closest_semantics'))))}'>⚠ {c['diff_pct']:+.2f}%</td>")
                    else: cells.append(f"<td class=mut title='{E(c.get('note', ''))}'>{E(c.get('status', '?'))}</td>")
                if any(c != "<td class=mut>–</td>" for c in cells):
                    h.append(f'<tr><td><a href="tools/{E(tid)}.html#{p}-correctness">{E(v["name"])}</a></td>{"".join(cells)}</tr>')
            h.append('</tbody></table></div>')
            h.append('<details class="more"><summary>Tool versions &amp; exact commands</summary><div class="tscroll"><table class="dt"><thead><tr><th>Tool</th><th class="l">Version</th><th class="l">Command</th></tr></thead><tbody>' +
                     "".join(f'<tr><td>{E(v["name"])}</td><td class="l">{E(str(v.get("version")))}</td><td class="l"><code>{E(" ".join(v["cmd"]))}</code></td></tr>' for v in tv.values()) +
                     '</tbody></table></div></details>')
            h.append("</div></div>")
        h.append("</div></section>")
        h.append('<section class="section" id="runs"><h2>All runs</h2><p class="sub">Every published result file, newest first (CC-BY-4.0).</p><div class="tscroll"><table class="dt"><thead><tr>'
                 '<th>Date</th><th class="l">Runner</th><th class="l">Profile</th><th class="l">File</th></tr></thead><tbody>' +
                 "".join(f'<tr><td>{E(r["_date"])}</td><td class="l">{E(r["_label"])}</td><td class="l">{E(r["profile"])}</td><td class="l"><a href="{E(r["_path"])}">results.json</a></td></tr>'
                         for r in sorted(self.runs, key=lambda r: (r["_date"], r["_label"]), reverse=True)) + '</tbody></table></div></section>')
        self.write("details.html", page("Data & runs · diskscan-bench", "".join(h), active="details.html"))

    # ---------- methodology ----------
    def methodology(self):
        md = open(os.path.join(ROOT, "docs", "methodology.md")).read()
        toc = ""
        try:
            import markdown
            m = markdown.Markdown(extensions=["tables", "fenced_code", "toc"], extension_configs={"toc": {"toc_depth": "2-3"}})
            body = m.convert(md); toc = m.toc
        except ImportError:
            body = f"<pre>{E(md)}</pre>"
        h = ['<section class="page-h"><h1>Methodology</h1><p class="lede">How tools are run, timed, checked and scored. '
             f'Source: <a href="{REPO}/blob/main/docs/methodology.md">docs/methodology.md</a>.</p></section>', disclosure(),
             f'<div class="doc"><nav class="toc" aria-label="On this page"><p class="tl">On this page</p>{toc}</nav><article class="card prose">{body}</article></div>']
        self.write("methodology.html", page("Methodology · diskscan-bench", "".join(h), active="methodology.html"))

    # ---------- badges ----------
    def badges(self):
        os.makedirs(os.path.join(OUT, "badges"), exist_ok=True)
        made = []
        for p in self.order:
            label, r = self.by_plat[p]
            sc, base, bad = scores(r, "cli")
            for i, d in enumerate(sc, 1):
                fn = f'{d["tool"]}-{label}.svg'
                txt = f'#{i} {PLAT_NAME[p]} · {d["score"]:.2f}× du'
                open(os.path.join(OUT, "badges", fn), "w").write(badge("diskscan-bench", txt, "#d99a00" if i == 1 else "#4f46e5"))
                made.append((r["tools"][d["tool"]]["name"], d["tool"], label, p, fn, i))
        best = {}
        for name, tid, label, p, fn, i in made:
            if tid not in best or (p == "linux"): best[tid] = fn
        for tid, fn in best.items():
            shutil.copy(os.path.join(OUT, "badges", fn), os.path.join(OUT, "badges", f"{tid}.svg"))
        h = ['<section class="page-h"><h1>Embeddable badges</h1><p class="lede">Rank and speed score per platform, regenerated on every run. '
             f'<span class="mono">badges/&lt;tool&gt;.svg</span> shows the Linux result where available. Please link the badge to the leaderboard.</p></section><div class="bgrid">']
        for tid in dict.fromkeys(m[1] for m in made):
            mine = [m for m in made if m[1] == tid]
            h.append(f'<article class="card bcard"><h3><a href="tools/{E(tid)}.html">{E(split_name(mine[0][0])[0])}</a></h3>')
            for name, _, label, p, fn, i in mine:
                h.append(f'<img src="badges/{E(fn)}" alt="diskscan-bench: #{i} on {PLAT_NAME[p]}" loading="lazy">'
                         f'<pre><code>[![diskscan-bench]({BASE_URL}/badges/{E(fn)})]({BASE_URL}/)</code></pre>')
            h.append("</article>")
        h.append("</div>")
        self.write("badges.html", page("Badges · diskscan-bench", "".join(h), active="badges.html"))

def main():
    s = Site()
    shutil.rmtree(OUT, ignore_errors=True); os.makedirs(os.path.join(OUT, "assets"))
    shutil.copytree(os.path.join(ROOT, "results"), os.path.join(OUT, "results"))
    s.write("assets/site.css", CSS.replace("%DARK%", DARK).replace("%TABCSS%", tab_css()))
    s.write("assets/site.js", JS)
    s.leaderboard(); s.tool_pages(); s.catalog_page(); s.details(); s.methodology(); s.badges()
    s.write("results/index.html", page("Raw results · diskscan-bench", '<section class="page-h"><h1>Raw results</h1><p class="lede">CC-BY-4.0. One JSON file per runner and run.</p></section>'
            '<div class="tscroll"><table class="dt"><tbody>' + "".join(f"<tr><td><a href='../{E(r['_path'])}'>{E(r['_path'])}</a></td><td class='l'>{E(r['profile'])}</td></tr>" for r in s.runs) +
            "</tbody></table></div>", root="../"))
    json.dump({k: v["_path"] for k, v in s.latest.items()}, open(os.path.join(OUT, "latest.json"), "w"), indent=1)
    open(os.path.join(OUT, ".nojekyll"), "w").close()
    print("site built:", OUT, len(s.runs), "runs,", len(s.catalog), "catalogued programs")

if __name__ == "__main__":
    main()
