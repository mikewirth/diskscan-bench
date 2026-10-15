#!/usr/bin/env python3
"""Build the static results site into _site/ from results/**/results.json."""
import glob, html, re, json, os, shutil, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "_site")
sys.path.insert(0, os.path.join(ROOT, "bench"))
from tools import TOOLS, PLANNED_GUI
E = html.escape

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

def fmt_t(s):
    if s is None: return "–"
    return f"{s*1000:.1f} ms" if s < 1 else f"{s:.2f} s"

def fmt_b(b):
    if b is None: return "–"
    for u in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(b) < 1024 or u == "TiB": return f"{b:.1f} {u}" if u != "B" else f"{b} B"
        b /= 1024

def bars(rows, title):
    """rows: [(label, median, stddev, flag)] -> inline SVG horizontal bar chart."""
    rows = [r for r in rows if r[1] is not None]
    if not rows: return ""
    rows.sort(key=lambda r: r[1]); mx = max(r[1] + (r[2] or 0) for r in rows) or 1
    W, lw, h = 640, 190, 22; H = 28 + h * len(rows)
    o = [f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="{E(title)}"><text x="0" y="16" class="ct">{E(title)}</text>']
    for i, (lab, med, sd, flag) in enumerate(rows):
        y = 26 + i * h; w = (W - lw - 90) * med / mx
        o.append(f'<text x="{lw-6}" y="{y+15}" text-anchor="end">{E(lab)}{" *" if flag else ""}</text>'
                 f'<rect x="{lw}" y="{y+3}" width="{max(w,1):.1f}" height="{h-7}" class="b{" f" if flag else ""}"/>')
        if sd:
            x1 = lw + (W - lw - 90) * max(med - sd, 0) / mx; x2 = lw + (W - lw - 90) * (med + sd) / mx
            o.append(f'<line x1="{x1:.1f}" x2="{x2:.1f}" y1="{y+11}" y2="{y+11}" class="sd"/>')
        o.append(f'<text x="{lw+w+6:.1f}" y="{y+15}">{fmt_t(med)}</text>')
    o.append("</svg>")
    return "".join(o)

def badge(left, right, color="#4c7"):
    lw, rw = 7 * len(left) + 12, 7 * len(right) + 12
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{lw+rw}" height="20" role="img" aria-label="{E(left)}: {E(right)}">'
            f'<rect width="{lw}" height="20" fill="#555"/><rect x="{lw}" width="{rw}" height="20" fill="{color}"/>'
            f'<g fill="#fff" font-family="Verdana,DejaVu Sans,sans-serif" font-size="11">'
            f'<text x="6" y="14">{E(left)}</text><text x="{lw+6}" y="14">{E(right)}</text></g></svg>')

CSS = """
:root{--bg:#fff;--fg:#14161a;--mut:#6b7280;--line:#e6e8eb;--card:#f7f8fa;--acc:#4f46e5;--gold:#f5b301;--warn:#d97706;--ok:#15803d;--bar:#4f46e5}
@media (prefers-color-scheme:dark){:root{--bg:#0e1015;--fg:#e8eaed;--mut:#9aa1ad;--line:#262a33;--card:#161922;--acc:#8b85ff;--bar:#8b85ff;--ok:#4ade80}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Inter,Roboto,sans-serif}
a{color:var(--acc);text-decoration:none}a:hover{text-decoration:underline}
header.top{border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg);z-index:5}
header.top .in{max-width:1080px;margin:auto;padding:12px 20px;display:flex;gap:18px;align-items:center;flex-wrap:wrap}
header.top .brand{font-weight:800;letter-spacing:-.02em;color:var(--fg);font-size:17px}header.top nav{display:flex;gap:16px;font-size:14px;flex-wrap:wrap}
header.top nav a{color:var(--mut)}header.top nav a:hover{color:var(--fg)}
main{max-width:1080px;margin:auto;padding:24px 20px 60px}
h1{font-size:34px;letter-spacing:-.03em;margin:8px 0 4px}h2{letter-spacing:-.02em;margin-top:40px}
.sub{color:var(--mut);margin:0 0 4px}.meta{color:var(--mut);font-size:13px}
.tabs{margin-top:22px}.tabs input{display:none}.tabs label{display:inline-block;padding:8px 16px;border:1px solid var(--line);border-radius:999px;margin:0 6px 8px 0;cursor:pointer;font-weight:600;font-size:14px;color:var(--mut)}
.tabs input:checked+label{background:var(--fg);color:var(--bg);border-color:var(--fg)}
.panel{display:none}#t-macos:checked~#p-macos,#t-linux:checked~#p-linux,#t-windows:checked~#p-windows{display:block}
table.lb{width:100%;border-collapse:separate;border-spacing:0;margin:10px 0 6px;font-size:15px}
.lb th{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--mut);text-align:left;font-weight:600;padding:8px 12px;border-bottom:1px solid var(--line)}
.lb td{padding:12px;border-bottom:1px solid var(--line);vertical-align:middle}.lb td.num,.lb th.num{text-align:right;font-variant-numeric:tabular-nums}
.lb tr.first td{background:linear-gradient(90deg,rgba(245,179,1,.16),transparent 70%);font-weight:700}
.rank{font-weight:800;width:56px;font-size:17px}.tool{font-weight:600}.ver{color:var(--mut);font-weight:400;font-size:12px;margin-left:6px}
.score{font-size:20px;font-weight:800;font-variant-numeric:tabular-nums}.sbar{height:6px;border-radius:3px;background:var(--line);margin-top:5px;min-width:80px}.sbar i{display:block;height:100%;border-radius:3px;background:var(--bar)}
.first .sbar i{background:var(--gold)}.acc-ok{color:var(--ok)}.acc-w{color:var(--warn)}.muted td{color:var(--mut)}
.hide-sm{}@media (max-width:640px){.hide-sm{display:none}h1{font-size:26px}.lb td{padding:10px 6px}.score{font-size:17px}}
.note{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 16px;font-size:13.5px;color:var(--mut);margin:18px 0}
.disc{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--gold);border-radius:8px;padding:10px 14px;font-size:13.5px}
.warn{background:var(--card);border-radius:8px;padding:10px 14px;font-size:13.5px}
table{border-collapse:collapse;font-size:13px;margin:8px 0 20px}td,th{border:1px solid var(--line);padding:4px 8px;text-align:right}td:first-child,th:first-child{text-align:left}
table.lb td,table.lb th{border-left:0;border-right:0;border-top:0;text-align:left}table.lb td.num,table.lb th.num{text-align:right}
.chart{width:100%;max-width:720px;font-size:12px;fill:var(--fg)}.ct{font-weight:600;font-size:13px}.b{fill:var(--bar)}.b.f{fill:var(--warn)}.sd{stroke:var(--fg);stroke-width:1.5}
.bad{color:var(--warn)}.ok{color:var(--ok)}code{font-size:12px}details{margin:8px 0}footer{color:var(--mut);font-size:12px;border-top:1px solid var(--line);margin-top:40px;padding-top:14px}
"""

def page(title, body):
    return (f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="color-scheme" content="light dark"><title>{E(title)}</title><style>{CSS}</style><body>'
            f'<header class="top"><div class="in"><a class="brand" href="index.html">diskscan-bench</a><nav>'
            f'<a href="index.html">Leaderboard</a><a href="details.html">Details</a><a href="methodology.html">Methodology</a>'
            f'<a href="badges.html">Badges</a><a href="https://github.com/mikewirth/diskscan-bench">GitHub</a></nav></div></header>'
            f'<main>{body}<footer>Code MIT OR Apache-2.0 · results CC-BY-4.0 · maintained by the maker of NullDisk '
            f'(<a href="methodology.html">disclosure</a>) · <a href="results/">raw JSON</a></footer></main></body></html>')

DISCLOSURE = ('<p class="disc"><b>Disclosure:</b> diskscan-bench is maintained by Michael Wirth, who also makes '
              '<a href="https://nulldisk.app">NullDisk</a>, a commercial macOS disk analyzer that is one of the benchmarked tools. '
              'Everything (harness, flags, datasets, raw data) is public; tool authors are invited to tune their own flags via pull request.</p>')
NOISE = ('<p class="warn"><b>Indicative numbers.</b> These runs use GitHub-hosted runners (shared VMs, network-backed disks, '
         'variable neighbours). Compare tools <i>within one run</i>; don\'t compare across runs or treat absolute times as hardware truth. '
         'Bars show the median, whiskers ±1 stddev. <span style="color:#d8893b">Orange / *</span> = reported total disagrees with the reference walker.</p>')

def main():
    runs, latest = load()
    shutil.rmtree(OUT, ignore_errors=True); os.makedirs(os.path.join(OUT, "badges"))
    shutil.copytree(os.path.join(ROOT, "results"), os.path.join(OUT, "results"))
    idx = ["<h1>diskscan-bench</h1><p>A neutral, reproducible benchmark of disk-usage scanners: CLI tools and GUI disk analyzers, "
           "on macOS, Linux and Windows, cold and warm cache, with a correctness check against a reference walker.</p>", DISCLOSURE, NOISE]
    corr = ["<h2 id='correctness'>Correctness: reported total vs reference walker</h2><p>Diff vs the canonical semantics "
            "(<code>alloc_du</code>: allocated bytes of every inode incl. directories, hard links counted once — what <code>du -s</code> reports; "
            "<code>logical_dedup</code> on Windows). <i>Closest</i> names the semantics the tool actually matches. Disagreement is flagged, never excluded.</p>"]
    badge_rows = []
    best_for_badge = {}
    for label, r in sorted(latest.items()):
        ri = r["runner"]
        idx.append(f"<h2 id='{E(label)}'>{E(label)}</h2><p><small>{E(r['_date'])} · profile <b>{E(r['profile'])}</b> · "
                   f"{E(str(ri.get('cpu_model')))} · {ri.get('cpus')} vCPU · {fmt_b(ri.get('mem_bytes'))} RAM · FS {E(str(ri.get('filesystem')))} · "
                   f"image {E(str(ri.get('image')))} {E(str(ri.get('image_version')))} · cold cache: {E(r['cold_method'])} · "
                   f"<a href='{E(r['_path'])}'>raw JSON</a></small></p>")
        tv = r["tools"]
        idx.append("<details><summary>Tool versions &amp; commands</summary><table><tr><th>tool</th><th>status</th><th>version</th><th>command</th></tr>" +
                   "".join(f"<tr><td>{E(v['name'])}</td><td>{E(v['status'])}</td><td>{E(str(v.get('version')))}</td><td><code>{E(' '.join(v['cmd']))}</code></td></tr>" for v in tv.values()) +
                   "</table></details>")
        for track in ("cli", "gui"):
            trs = [x for x in r["results"] if x.get("track", "cli") == track]
            if not trs: continue
            if track == "gui":
                idx.append("<h3>GUI track (separate methodology: time from launch until the app's own CLI export finishes and the process exits)</h3>")
            for ds in r["datasets"]:
                d = r["datasets"][ds]; rows = [x for x in trs if x["dataset"] == ds]
                if not rows: continue
                idx.append(f"<h4>{E(ds)} <small>— {d['files']:,} files, {d['dirs']:,} dirs, {fmt_b(d['logical_dedup'])} logical, "
                           f"{fmt_b(d.get('alloc_du'))} allocated · manifest <code>{d['manifest_sha256'][:12]}</code></small></h4>")
                for mode in ("cold", "warm"):
                    pts = [(tv[x["tool"]]["name"], None if (x.get(mode) or {}).get("invalid") else (x.get(mode) or {}).get("median_s"), (x.get(mode) or {}).get("stddev_s"),
                            x["correctness"]["status"] == "disagrees") for x in rows]
                    idx.append(bars(pts, f"{ds} · {mode} cache · {label}"))
                idx.append("<table><tr><th>tool</th><th>cold median</th><th>±sd</th><th>warm median</th><th>±sd</th><th>peak RSS</th><th>total</th></tr>" +
                           "".join(f"<tr><td>{E(tv[x['tool']]['name'])}</td><td>{fmt_t((x.get('cold') or {}).get('median_s'))}</td><td>{fmt_t((x.get('cold') or {}).get('stddev_s'))}</td>"
                                   f"<td>{fmt_t((x.get('warm') or {}).get('median_s'))}</td><td>{fmt_t((x.get('warm') or {}).get('stddev_s'))}</td>"
                                   f"<td>{fmt_b(x.get('peak_rss_bytes'))}</td><td>{fmt_b(x.get('reported_bytes'))}</td></tr>" for x in rows) + "</table>")
        corr.append(f"<h3>{E(label)}</h3><table><tr><th>tool</th>" + "".join(f"<th>{E(ds)}</th>" for ds in r["datasets"]) + "</tr>")
        for tid, v in tv.items():
            cells = []
            for ds in r["datasets"]:
                x = next((y for y in r["results"] if y["tool"] == tid and y["dataset"] == ds), None)
                if not x or "correctness" not in x: cells.append("<td>–</td>"); continue
                c = x["correctness"]
                if c["status"] == "agrees": cells.append(f"<td class='ok'>✓ {c['diff_pct']:+.2f}%</td>")
                elif c["status"] == "disagrees": cells.append(f"<td class='bad'>✗ {c['diff_pct']:+.2f}%<br><small>closest: {E(str(c.get('closest_semantics')))}</small></td>")
                else: cells.append(f"<td><small>{E(c.get('note',''))[:60]}</small></td>")
            if any(c != "<td>–</td>" for c in cells):
                corr.append(f"<tr><td>{E(v['name'])}</td>{''.join(cells)}</tr>")
        corr.append("</table>")
        # badges: kernel (or largest dataset) warm+cold per runner
        pref = [d for d in ("linux_kernel", "node_modules", "tiny", "small") if d in r["datasets"]]
        for x in r["results"]:
            if pref and x["dataset"] == pref[0] and (x.get("warm") or {}).get("median_s"):
                txt = f"{fmt_t(x['warm']['median_s'])} warm" + (f" / {fmt_t(x['cold']['median_s'])} cold" if (x.get('cold') or {}).get('median_s') else "") + f" ({pref[0]}, {label})"
                fn = f"{x['tool']}-{label}.svg"
                pass
                badge_rows.append((x["tool"], label, fn, txt))
                best_for_badge.setdefault(x["tool"], fn)

    pend = [t for t in TOOLS if t["id"] == "nulldisk"]
    planned = ("<h2 id='planned'>GUI tools: planned / excluded</h2><table><tr><th>platform</th><th>tool</th><th>reason</th></tr>" +
               "".join(f"<tr><td>{E(p)}</td><td>{E(n)}</td><td style='text-align:left'>{E(why)}</td></tr>" for p, n, why in PLANNED_GUI) + "</table>")
    hist = "<h2>All runs</h2><ul>" + "".join(f"<li><a href='{E(r['_path'])}'>{E(r['_date'])} / {E(r['_label'])}</a> ({E(r['profile'])})</li>" for r in reversed(runs)) + "</ul>"
    if not latest: idx.append("<p>No results yet.</p>")
    open(os.path.join(OUT, "details.html"), "w").write(page("Details · diskscan-bench", "<h1>Technical details</h1>" + "".join(idx[1:] + corr) + planned + hist))
    leaderboard(latest)
    md = open(os.path.join(ROOT, "docs", "methodology.md")).read()
    try:
        import markdown; body = markdown.markdown(md, extensions=["tables", "fenced_code"])
    except ImportError:
        body = f"<pre>{E(md)}</pre>"
    open(os.path.join(OUT, "methodology.html"), "w").write(page("Methodology · diskscan-bench", DISCLOSURE + body))
    base = "https://mikewirth.github.io/diskscan-bench"
    with open(os.path.join(OUT, "results", "index.html"), "w") as f:
        f.write(page("Raw results", "<h1>Raw results (CC-BY-4.0)</h1><ul>" + "".join(f"<li><a href='../{E(r['_path'])}'>{E(r['_path'])}</a></li>" for r in runs) + "</ul>"))
    json.dump({k: v["_path"] for k, v in latest.items()}, open(os.path.join(OUT, "latest.json"), "w"), indent=1)
    open(os.path.join(OUT, ".nojekyll"), "w").close()
    print("site built:", OUT, len(runs), "runs")

# ---------------- leaderboard ----------------
import math
# Datasets held out of scoring pending investigation (shown on the details page, documented in methodology).
EXCLUDE_SCORING = {("macos", "node_modules"): "BSD du and the reference walker agree, but all 7 other tools report exactly 2.3% less; under investigation (likely APFS clone/compression accounting from npm's clonefile installs)"}
BASELINE = {"linux": "du", "macos": "du", "windows": "du-sysinternals"}
PLAT_NAME = {"macos": "macOS", "linux": "Linux", "windows": "Windows"}

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

def scores(r, track):
    """Speed score = geometric mean over (dataset, cache mode) of baseline_median / tool_median."""
    plat = r["runner"]["platform"]; base = BASELINE[plat]; bad = suspect_datasets(r)
    rows = [x for x in r["results"] if x.get("track", "cli") == track]
    allres = r["results"]
    cells = [(ds, m) for ds in r["datasets"] if ds not in bad for m in ("cold", "warm")
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
            if x["tool"] == tid and x["dataset"] not in bad and x["correctness"]["status"] == "disagrees":
                warn.append(f'{x["dataset"]} {x["correctness"]["diff_pct"]:+.1f}%')
        if not ratios or len(ratios) < 0.5 * len(cells): continue
        geo = math.exp(sum(map(math.log, ratios)) / len(ratios))
        def med(mode):
            xs = [x[mode]["median_s"] for x in rows if x["tool"] == tid and x["dataset"] not in bad and valid(x.get(mode))]
            return math.exp(sum(map(math.log, xs)) / len(xs)) if xs else None
        out.append(dict(tool=tid, score=geo, n=len(ratios), cells=len(cells), warn=warn, cold=med("cold"), warm=med("warm")))
    out.sort(key=lambda d: -d["score"])
    return out, base, bad

def leaderboard(latest):
    by_plat = {}
    for label, r in latest.items():
        by_plat.setdefault(r["runner"]["platform"], (label, r))
    order = [p for p in ("macos", "linux", "windows") if p in by_plat]
    dates = sorted(r["_date"] for _, r in by_plat.values())
    h = ['<h1>Disk-usage scanner leaderboard</h1>',
         '<p class="sub"><b>Speed score</b> = how many times faster than the platform\'s <code>du</code>, as a geometric mean over every dataset, cold and warm cache. '
         '<code>du</code> = 1.00×, higher is better.</p>',
         f'<p class="meta">Last updated {E(dates[-1] if dates else "–")} · GitHub-hosted runners (indicative, see <a href="methodology.html">methodology</a>) · '
         'maintained by the maker of NullDisk (<a href="methodology.html">disclosure</a>)</p>', '<div class="tabs">']
    for i, p in enumerate(order):
        h.append(f'<input type="radio" name="t" id="t-{p}"{" checked" if p == "linux" or (i == 0 and "linux" not in order) else ""}><label for="t-{p}">{PLAT_NAME[p]}</label>')
    badges = []
    for p in order:
        label, r = by_plat[p]; tv = r["tools"]; ri = r["runner"]
        h.append(f'<section class="panel" id="p-{p}">')
        for track, title in (("cli", "CLI tools"), ("gui", "GUI apps")):
            sc, base, bad = scores(r, track)
            if not sc: continue
            top = sc[0]["score"]
            h.append(f'<h2>{title} · {PLAT_NAME[p]}</h2>' if track == "gui" else "")
            h.append('<table class="lb"><tr><th>#</th><th>Tool</th><th class="num">Speed score</th>'
                     '<th class="num hide-sm">Cold</th><th class="num hide-sm">Warm</th><th>Accuracy</th></tr>')
            for i, d in enumerate(sc, 1):
                t = tv[d["tool"]]; vm = re.search(r"git \w+|\d+(?:\.\d+)+", t.get("version") or ""); ver = vm.group(0) if vm else ""
                medal = {1: "🏆", 2: "🥈", 3: "🥉"}.get(i, str(i))
                acc = (f'<a class="acc-w" href="details.html#correctness" title="{E("; ".join(d["warn"]))}">⚠ differs</a>'
                       if d["warn"] else '<span class="acc-ok">✓</span>')
                base_note = ' <span class="ver">(baseline)</span>' if d["tool"] == base else ""
                h.append(f'<tr class="{"first" if i == 1 else ""}"><td class="rank">{medal}</td>'
                         f'<td><a class="tool" href="details.html#{E(label)}">{E(t["name"])}</a><span class="ver">{E(ver)}</span>{base_note}</td>'
                         f'<td class="num"><div class="score">{d["score"]:.2f}×</div><div class="sbar"><i style="width:{100*d["score"]/top:.0f}%"></i></div></td>'
                         f'<td class="num hide-sm">{fmt_t(d["cold"])}</td><td class="num hide-sm">{fmt_t(d["warm"])}</td><td>{acc}</td></tr>')
                if track == "cli":
                    fn = f'{d["tool"]}-{label}.svg'
                    txt = f'#{i} {PLAT_NAME[p]} · {d["score"]:.2f}× du'
                    open(os.path.join(OUT, "badges", fn), "w").write(badge("diskscan-bench", txt, "#e0a800" if i == 1 else "#4f46e5"))
                    badges.append((t["name"], d["tool"], label, p, fn, i))
            h.append("</table>")
            if track == "cli":
                h.append(f'<p class="meta">Baseline <code>{E(base)}</code> · {sc[0]["cells"]} dataset×cache cells · Cold/Warm = geometric-mean median time · '
                         f'{E(str(ri.get("cpu_model")))}, {ri.get("cpus")} vCPU, {E(str(ri.get("filesystem")))}'
                         + (f' · not scored (reference under review): {E(", ".join(sorted(bad)))}' if bad else "")
                         + ("" if r["cache_modes"].get("cold") else " · warm cache only on this platform") + "</p>")
        plan = [(n, why) for pp, n, why in PLANNED_GUI if pp in (p, "all")]
        if plan:
            if not any(x.get("track") == "gui" for x in r["results"]): h.append(f'<h2>GUI apps · {PLAT_NAME[p]}</h2>')
            h.append('<table class="lb"><tr><th></th><th>Planned / excluded</th><th>Why</th></tr>' +
                     "".join(f'<tr class="muted"><td class="rank">–</td><td>{E(n)}</td><td>{E(w)}</td></tr>' for n, w in plan) + "</table>")
        h.append("</section>")
    h.append("</div>")
    h.append('<div class="note">GUI times run from app launch until its own export finishes, so they are not comparable with CLI times. '
             '⚠ means the reported total differs from our reference walker, usually because of a definition (directory blocks, hard links), not a bug. '
             'The tool stays ranked; see <a href="details.html#correctness">correctness</a>. Tool authors can tune their flags by PR. '
             'NullDisk CLI: pending public download.</div>')
    open(os.path.join(OUT, "index.html"), "w").write(page("diskscan-bench: disk-usage scanner leaderboard", "".join(h)))
    best = {}
    for name, tid, label, p, fn, i in badges:
        if tid not in best or (p == "linux"): best[tid] = fn
    for tid, fn in best.items():
        shutil.copy(os.path.join(OUT, "badges", fn), os.path.join(OUT, "badges", f"{tid}.svg"))
    base = "https://mikewirth.github.io/diskscan-bench"
    open(os.path.join(OUT, "badges.html"), "w").write(page("Badges · diskscan-bench",
        "<h1>Embeddable badges</h1><p class='sub'>Rank and speed score per platform, regenerated on every run. Please link the badge to the leaderboard.</p>"
        "<table class='lb'><tr><th>Tool</th><th>Platform</th><th>Badge</th><th>Markdown</th></tr>" +
        "".join(f"<tr><td>{E(n)}</td><td>{PLAT_NAME[p]}</td><td><img src='badges/{E(fn)}' alt='badge'></td><td><code>[![diskscan-bench]({base}/badges/{E(fn)})]({base}/)</code></td></tr>"
                for n, tid, label, p, fn, i in badges) + "</table>"))

if __name__ == "__main__":
    main()
