#!/usr/bin/env python3
"""diskscan-bench runner.

  python bench/run.py --profile smoke|full [--data-root DIR] [--out results/DATE/RUNNER]

Steps per dataset: build (deterministic) -> reference walk + manifest ->
for each tool: one instrumented run (reported total, peak RSS, exit code) ->
hyperfine warm -> hyperfine cold (where the platform supports cache eviction).
"""
import argparse, datetime, json, os, platform, re, shlex, shutil, statistics, subprocess, sys, tarfile, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from tools import for_platform, PLAT, PLANNED_GUI
import refwalk, gen

os.environ["PATH"] = os.path.join(ROOT, ".tools", "bin") + os.pathsep + os.environ["PATH"]
KERNEL = ("6.6", "https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.6.tar.xz",
          "d926a06c63dd8ac7df3f86ee1ffc2ce2a3b81a2d168484e76b5b389aba8e56d0")
PROFILES = {
    "smoke": dict(datasets=["small"], warm_runs=3, cold_runs=2, warmup=1),
    "full": dict(datasets=["tiny", "deep", "wide", "mixed", "node_modules", "linux_kernel"],
                 warm_runs=10, cold_runs=5, warmup=2),
}

def sh(cmd, **kw):
    return subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, errors="replace", **kw)

# ---------------- datasets ----------------
def build_dataset(name, root):
    path = os.path.join(root, name)
    if os.path.exists(os.path.join(path, ".dsb-done")):
        return path
    shutil.rmtree(path, ignore_errors=True)
    t0 = time.time()
    if name in ("small", "tiny", "deep", "wide", "mixed"):
        gen.generate(os.path.join(path, "tree"), name, 42, 1.0)
    elif name == "node_modules":
        os.makedirs(os.path.join(path, "tree"))
        for f in ("package.json", "package-lock.json"):
            shutil.copy(os.path.join(ROOT, "datasets", "node_modules", f), os.path.join(path, "tree", f))
        npm = "npm.cmd" if PLAT == "windows" else "npm"
        subprocess.run([npm, "ci", "--ignore-scripts", "--no-audit", "--no-fund"], cwd=os.path.join(path, "tree"), check=True)
    elif name == "linux_kernel":
        ver, url, sha = KERNEL
        tmp = os.path.join(root, "linux.tar.xz")
        if not os.path.exists(tmp):
            subprocess.run(["curl", "-sSfL", "-o", tmp, url], check=True)
        got = sh(["shasum", "-a", "256", tmp] if PLAT == "macos" else ["sha256sum", tmp]).stdout.split()[0]
        assert got == sha, f"kernel tarball sha mismatch {got}"
        os.makedirs(os.path.join(path, "tree"))
        subprocess.run(["tar", "-xJf", tmp, "-C", os.path.join(path, "tree")], check=True)
        os.remove(tmp)
    open(os.path.join(path, ".dsb-done"), "w").write(str(time.time() - t0))
    return path

# ---------------- parsing ----------------
INT = re.compile(r"\d[\d,]*")
def ints(s): return [int(x.replace(",", "")) for x in INT.findall(s)]
UNITS = {"": 1, "B": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}

def parse_total(t, out, scratch, path):
    p = t["parse"]; lines = [l for l in out.splitlines() if l.strip()]
    try:
        if p == "first_int":
            return ints(lines[0])[0]
        if p == "first_int_kib":
            return ints(lines[0])[0] * 1024
        if p == "last_int":
            return ints(lines[-1])[0]
        if p == "human":
            m = re.match(r"\s*([\d.]+)\s*([KMGT]?)i?B?", lines[0])
            return int(float(m.group(1)) * UNITS[m.group(2)])
        if p == "ncdu_json":
            return ncdu_total(json.load(open(scratch, encoding="utf-8", errors="replace")))
        if p == "sysinternals_csv":
            hdr = [h.strip() for h in lines[0].split(",")]
            row = lines[-1].rsplit(",", len(hdr) - 1)
            return int(row[hdr.index("DirectorySize")])
        if p == "windirstat_csv":
            return windirstat_total(scratch + ".csv")
        if p == "nulldisk_json":
            return find_bytes(json.loads(out))
    except Exception as e:
        return f"parse error: {e}"
    return None

def ncdu_total(j):
    seen = set()
    def rec(node):
        info = node[0] if isinstance(node, list) else node
        tot = 0
        key = info.get("ino")
        hl = info.get("hlnkc") or (info.get("nlink", 1) > 1)
        if not (hl and key in seen):
            tot += info.get("dsize", 0)
            if hl: seen.add(key)
        if isinstance(node, list):
            for c in node[1:]: tot += rec(c)
        return tot
    return rec(j[3])

def windirstat_total(fn):
    import csv
    rows = list(csv.reader(open(fn, encoding="utf-8-sig", errors="replace")))
    hdr = [h.lower() for h in rows[0]]
    col = next(i for i, h in enumerate(hdr) if "size" in h and "alloc" not in h and "disk" not in h)
    return max(int(float(r[col])) for r in rows[1:] if len(r) > col and r[col].replace(".", "").isdigit())

def find_bytes(j):
    """NullDisk JSON: prefer explicit allocated totals; schema is the vendor's."""
    for k in ("allocated_bytes", "total_allocated_bytes", "allocated", "size_on_disk", "disk_bytes", "total_bytes", "bytes", "size"):
        if isinstance(j, dict) and isinstance(j.get(k), int): return j[k]
    if isinstance(j, dict):
        for k in ("total", "summary", "root"):
            if k in j:
                r = find_bytes(j[k])
                if isinstance(r, int): return r
    return "parse error: no total field"

# ---------------- correctness ----------------
def judge(t, val, ref):
    if not isinstance(val, int):
        return dict(status="unknown", note=str(val) if val else "tool does not print a total")
    if t["metric"] == "allocated" and ref.get("alloc_du") is not None:
        canon = "alloc_du"; cands = ["alloc_du", "alloc_files_dedup", "alloc_nodedup", "alloc_files_nodedup"]
    else:
        canon = "logical_dedup"; cands = ["logical_dedup", "logical", "logical_with_dirs_dedup"]
    tol = {"exact": 0.001, "kib": 0.001, "human": 0.06}.get(t["precision"], 0.001)
    def diff(k): return (val - ref[k]) / ref[k] if ref[k] else 0.0
    if not ref[canon]:
        return dict(status="unknown", note="reference total is 0")
    d = diff(canon)
    best = min(cands, key=lambda k: abs(diff(k)))
    ok = abs(d) <= tol
    return dict(status="agrees" if ok else "disagrees", reference=canon, reference_value=ref[canon],
                diff_pct=round(d * 100, 3), closest_semantics=best if abs(diff(best)) <= tol else None)

# ---------------- execution ----------------
def fill(cmd, path, scratch):
    return [c.replace("{path}", path).replace("{out}", scratch) for c in cmd]

def instrumented(argv, timeout=900):
    """Run once; return (stdout, exit, seconds, peak_rss_bytes)."""
    t0 = time.time()
    if PLAT == "linux" and os.path.exists("/usr/bin/time"):
        p = subprocess.run(["/usr/bin/time", "-v"] + argv, capture_output=True, text=True, errors="replace", timeout=timeout)
        m = re.search(r"Maximum resident set size \(kbytes\): (\d+)", p.stderr)
        return p.stdout, p.returncode, time.time() - t0, int(m.group(1)) * 1024 if m else None
    if PLAT == "macos":
        p = subprocess.run(["/usr/bin/time", "-l"] + argv, capture_output=True, text=True, errors="replace", timeout=timeout)
        m = re.search(r"(\d+)\s+maximum resident set size", p.stderr)
        return p.stdout, p.returncode, time.time() - t0, int(m.group(1)) if m else None
    try:
        import psutil
        pr = psutil.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        peak = 0
        while pr.poll() is None:
            if time.time() - t0 > timeout:
                pr.kill(); raise subprocess.TimeoutExpired(argv, timeout)
            try: peak = max(peak, pr.memory_info().peak_wset)
            except Exception: pass
            time.sleep(0.02)
        out = pr.stdout.read().decode(errors="replace")
        return out, pr.returncode, time.time() - t0, peak or None
    except ImportError:
        p = subprocess.run(argv, capture_output=True, text=True, errors="replace", timeout=timeout)
        return p.stdout, p.returncode, time.time() - t0, None

def cold_prepare():
    if PLAT == "linux":
        return "sync; echo 3 | sudo tee /proc/sys/vm/drop_caches >/dev/null"
    if PLAT == "macos" and os.environ.get("DSB_DMG"):
        return f"bash {shlex.quote(os.path.join(HERE, 'macos_remount.sh'))}"
    return None

def hyperfine(argv, runs, warmup, prepare, jf):
    cmd = ["hyperfine", "-N", "-i", "--runs", str(runs), "--export-json", jf, "--style", "basic"]
    if warmup: cmd += ["--warmup", str(warmup)]
    if prepare: cmd += ["--prepare", prepare]
    cmd.append(shlex.join(argv) if PLAT != "windows" else subprocess.list2cmdline(argv))
    p = sh(cmd, timeout=7200)
    if p.returncode != 0:
        return dict(error=(p.stderr or p.stdout)[-800:])
    r = json.load(open(jf))["results"][0]
    if "summary" in r:  # hyperfine >= 2.0 schema
        w = r["summary"]["time_wall_clock"]; m = r["summary"].get("memory_peak_resident") or {}
        g = lambda k: (r["summary"].get(k) or {}).get("mean")
        times = [x["time_wall_clock"]["value"] for x in r["measurements"]]
        codes = sorted({x.get("exit_code") for x in r["measurements"]}, key=str)
        return dict(median_s=w["median"], mean_s=w["mean"], stddev_s=w.get("stddev"), min_s=w["min"], max_s=w["max"],
                    runs=len(times), times_s=times, user_s=g("time_user"), system_s=g("time_system"),
                    peak_rss_median_bytes=m.get("median"), exit_codes=codes)
    times = r["times"]
    return dict(median_s=r["median"], mean_s=r["mean"], stddev_s=r.get("stddev"), min_s=r["min"], max_s=r["max"],
                runs=len(times), times_s=times, user_s=r.get("user"), system_s=r.get("system"),
                exit_codes=sorted(set(r.get("exit_codes") or [])))

def tool_version(t):
    if t.get("version"):
        p = sh(t["version"])
        v = (p.stdout or p.stderr).strip().splitlines()
        if PLAT == "macos" and t["id"] == "du":
            return "BSD du (macOS " + platform.mac_ver()[0] + ")"
        return v[0] if v else None
    return t.get("version_static")

def runner_info(data_root):
    i = dict(platform=PLAT, os=platform.platform(), machine=platform.machine(), cpus=os.cpu_count(),
             python=platform.python_version(),
             image=os.environ.get("ImageOS"), image_version=os.environ.get("ImageVersion"),
             runner_name=os.environ.get("RUNNER_NAME"), runner_environment=os.environ.get("RUNNER_ENVIRONMENT"),
             label=os.environ.get("DSB_RUNNER_LABEL"), github_run=os.environ.get("GITHUB_RUN_ID"),
             commit=os.environ.get("GITHUB_SHA"))
    if PLAT == "linux":
        i["cpu_model"] = next((l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name")), None)
        i["mem_bytes"] = int(next(l.split()[1] for l in open("/proc/meminfo") if l.startswith("MemTotal"))) * 1024
        i["filesystem"] = sh(["df", "-T", data_root]).stdout.splitlines()[-1].split()[1]
        i["kernel"] = platform.release()
    elif PLAT == "macos":
        i["cpu_model"] = sh(["sysctl", "-n", "machdep.cpu.brand_string"]).stdout.strip()
        i["mem_bytes"] = int(sh(["sysctl", "-n", "hw.memsize"]).stdout.strip())
        i["macos"] = platform.mac_ver()[0]
        fs = re.search(r"Type \(Bundle\):\s+(\S+)", sh(["diskutil", "info", data_root]).stdout)
        i["filesystem"] = (fs.group(1) if fs else "apfs") + (" (dedicated disk image)" if os.environ.get("DSB_DMG") else "")
    else:
        i["cpu_model"] = platform.processor()
        try:
            import psutil; i["mem_bytes"] = psutil.virtual_memory().total
        except ImportError: pass
        i["filesystem"] = "NTFS"
    return i

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="smoke", choices=PROFILES)
    ap.add_argument("--data-root", default=os.environ.get("DSB_DATA", os.path.join(tempfile.gettempdir(), "dsb-data")))
    ap.add_argument("--out", default=None)
    ap.add_argument("--datasets", default=None, help="comma list overriding the profile")
    ap.add_argument("--tools", default=None, help="comma list of tool ids")
    a = ap.parse_args()
    prof = PROFILES[a.profile]
    datasets = a.datasets.split(",") if a.datasets else prof["datasets"]
    if PLAT == "windows" and "linux_kernel" in datasets:
        datasets.remove("linux_kernel")  # case-colliding names + symlinks; see methodology
    os.makedirs(a.data_root, exist_ok=True)
    date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    label = os.environ.get("DSB_RUNNER_LABEL", f"local-{PLAT}")
    out = a.out or os.path.join(ROOT, "results", date, label)
    os.makedirs(out, exist_ok=True)
    scratch_dir = tempfile.mkdtemp(prefix="dsb-scratch-")
    tools = for_platform()
    if a.tools: tools = [t for t in tools if t["id"] in a.tools.split(",")]
    prep = cold_prepare()
    res = dict(schema=1, generated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
               profile=a.profile, runner=runner_info(a.data_root),
               cache_modes={"warm": True, "cold": bool(prep)},
               cold_method={"linux": "sync + echo 3 > /proc/sys/vm/drop_caches before every run",
                            "macos": "detach + `purge` + reattach of a dedicated APFS disk image before every run",
                            "windows": "not supported on hosted runners yet (planned: VHD detach/attach)"}[PLAT],
               tools={}, datasets={}, results=[], planned_gui=[dict(platform=p, name=n, reason=r) for p, n, r in PLANNED_GUI])
    for t in tools:
        present = shutil.which(t["cmd"][0]) is not None
        st = t["status"] if present else ("pending" if t.get("optional") else "missing")
        res["tools"][t["id"]] = dict(name=t["name"], homepage=t["homepage"], track=t["track"], metric=t["metric"],
                                     pin=t.get("pin"), status=st, version=tool_version(t) if present else None,
                                     cmd=t["cmd"], notes=t.get("notes"), method=t.get("method"))
    for ds in datasets:
        print(f"== dataset {ds}", flush=True)
        path = os.path.join(build_dataset(ds, a.data_root), "tree")
        ref = refwalk.walk(path, manifest=True)
        res["datasets"][ds] = ref
        print(json.dumps(ref), flush=True)
        for t in tools:
            if res["tools"][t["id"]]["status"] != "active":
                continue
            scratch = os.path.join(scratch_dir, f"{t['id']}-{ds}.out")
            argv = fill(t["cmd"], path, scratch)
            print(f"-- {t['id']} {shlex.join(argv)}", flush=True)
            entry = dict(tool=t["id"], dataset=ds, track=t["track"])
            try:
                stdout, code, secs, rss = instrumented(argv, timeout=300 if t['track'] == 'gui' else 900)
            except subprocess.TimeoutExpired:
                entry["error"] = "timeout in instrumented run"; res["results"].append(entry); continue
            total = parse_total(t, stdout, scratch, path)
            entry.update(exit_code=code, peak_rss_bytes=rss, reported_bytes=total if isinstance(total, int) else None,
                         correctness=judge(t, total, ref), stdout_head=stdout[:300])
            if code not in t.get("ok_exit", [0]):
                entry["correctness"]["note"] = f"exit code {code}"
            entry["warm"] = hyperfine(argv, prof["warm_runs"], prof["warmup"], None, scratch + ".warm.json")
            entry["cold"] = hyperfine(argv, prof["cold_runs"], 0, prep, scratch + ".cold.json") if prep else None
            print(json.dumps({k: entry[k] for k in ("reported_bytes", "correctness")}),
                  "warm", entry["warm"].get("median_s"), "cold", (entry["cold"] or {}).get("median_s"), flush=True)
            res["results"].append(entry)
    with open(os.path.join(out, "results.json"), "w") as f:
        json.dump(res, f, indent=1)
    print("wrote", os.path.join(out, "results.json"))

if __name__ == "__main__":
    main()
