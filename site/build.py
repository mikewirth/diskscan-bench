#!/usr/bin/env python3
"""Build the static results site into _site/ from results/**/results.json."""
import glob, html, json, os, shutil, sys
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

CSS = """body{font:15px/1.5 system-ui,sans-serif;max-width:1000px;margin:auto;padding:0 16px;color:#222}
nav a{margin-right:14px}table{border-collapse:collapse;font-size:13px;margin:8px 0 20px}td,th{border:1px solid #ddd;padding:3px 7px;text-align:right}
td:first-child,th:first-child{text-align:left}.disc{background:#fff6e0;border:1px solid #e8c66a;padding:8px 12px;border-radius:6px}
.warn{background:#f3f3f3;padding:8px 12px;border-radius:6px}.chart{width:100%;max-width:700px;font-size:12px}.ct{font-weight:600;font-size:13px}
.b{fill:#3b7dd8}.b.f{fill:#d8893b}.sd{stroke:#111;stroke-width:1.5}.bad{color:#b40}.ok{color:#270}code{font-size:12px}h2{margin-top:36px}"""

def page(title, body):
    return (f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
            f'<title>{E(title)}</title><style>{CSS}</style><body><nav><a href="index.html"><b>diskscan-bench</b></a>'
            f'<a href="index.html">Results</a><a href="methodology.html">Methodology</a><a href="badges.html">Badges</a>'
            f'<a href="https://github.com/mikewirth/diskscan-bench">GitHub</a><a href="results/">Raw JSON</a></nav>{body}'
            f'<hr><p><small>Code MIT OR Apache-2.0 · results CC-BY-4.0 · maintained by the maker of NullDisk (see disclosure)</small></p></body></html>')

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
                    pts = [(tv[x["tool"]]["name"], (x.get(mode) or {}).get("median_s"), (x.get(mode) or {}).get("stddev_s"),
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
                open(os.path.join(OUT, "badges", fn), "w").write(badge("diskscan-bench", txt))
                badge_rows.append((x["tool"], label, fn, txt))
                best_for_badge.setdefault(x["tool"], fn)
    for tid, fn in best_for_badge.items():
        shutil.copy(os.path.join(OUT, "badges", fn), os.path.join(OUT, "badges", f"{tid}.svg"))
    pend = [t for t in TOOLS if t["id"] == "nulldisk"]
    planned = ("<h2 id='planned'>GUI tools: planned / excluded</h2><table><tr><th>platform</th><th>tool</th><th>reason</th></tr>" +
               "".join(f"<tr><td>{E(p)}</td><td>{E(n)}</td><td style='text-align:left'>{E(why)}</td></tr>" for p, n, why in PLANNED_GUI) + "</table>")
    hist = "<h2>All runs</h2><ul>" + "".join(f"<li><a href='{E(r['_path'])}'>{E(r['_date'])} / {E(r['_label'])}</a> ({E(r['profile'])})</li>" for r in reversed(runs)) + "</ul>"
    if not latest: idx.append("<p>No results yet.</p>")
    open(os.path.join(OUT, "index.html"), "w").write(page("diskscan-bench results", "".join(idx + corr) + planned + hist))
    md = open(os.path.join(ROOT, "docs", "methodology.md")).read()
    try:
        import markdown; body = markdown.markdown(md, extensions=["tables", "fenced_code"])
    except ImportError:
        body = f"<pre>{E(md)}</pre>"
    open(os.path.join(OUT, "methodology.html"), "w").write(page("Methodology · diskscan-bench", DISCLOSURE + body))
    base = "https://mikewirth.github.io/diskscan-bench"
    open(os.path.join(OUT, "badges.html"), "w").write(page("Badges · diskscan-bench",
        "<h1>Embeddable badges</h1><p>Each badge shows the latest median for the tool on that runner (preferred dataset: Linux kernel source). "
        "Badges are regenerated on every run. Please link the badge back to the results page.</p><table><tr><th>tool</th><th>runner</th><th>badge</th><th>Markdown</th></tr>" +
        "".join(f"<tr><td>{E(t)}</td><td>{E(l)}</td><td><img src='badges/{E(fn)}'></td><td style='text-align:left'><code>[![diskscan-bench]({base}/badges/{E(fn)})]({base}/#{E(l)})</code></td></tr>" for t, l, fn, _ in badge_rows) + "</table>"))
    with open(os.path.join(OUT, "results", "index.html"), "w") as f:
        f.write(page("Raw results", "<h1>Raw results (CC-BY-4.0)</h1><ul>" + "".join(f"<li><a href='../{E(r['_path'])}'>{E(r['_path'])}</a></li>" for r in runs) + "</ul>"))
    json.dump({k: v["_path"] for k, v in latest.items()}, open(os.path.join(OUT, "latest.json"), "w"), indent=1)
    open(os.path.join(OUT, ".nojekyll"), "w").close()
    print("site built:", OUT, len(runs), "runs")

if __name__ == "__main__":
    main()
