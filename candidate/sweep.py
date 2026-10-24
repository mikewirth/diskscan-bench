"""Parameter sweep for a candidate build (artifacts only). Builds datasets with bench/run.py's own
builder (incl. settle), then times du/dumac/dua/diskus and nulldisk at several --jobs values,
warm (hyperfine) and optionally cold (same prepare as run.py). Prints a table and writes sweep.json."""
import json, os, sys, shutil, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bench"))
import run
DS = (os.environ.get("SWEEP_DATASETS") or "tiny,wide,mixed,linux_kernel,deep").split(",")
JOBS = (os.environ.get("SWEEP_JOBS") or "1,2,3,4,6,8,12,0").split(",")
EXTRA = [x for x in (os.environ.get("SWEEP_EXTRA") or "").split(";") if x]  # extra nulldisk arg sets
WARM, COLD = int(os.environ.get("SWEEP_WARM", "15")), int(os.environ.get("SWEEP_COLD", "3"))
root = os.environ.get("DSB_DATA") or os.path.join(tempfile.gettempdir(), "dsb-data")
os.makedirs(root, exist_ok=True)
cfgs = []
for t in ("du", "dumac", "dua", "diskus", "pdu", "gdu"):
    tt = [x for x in run.for_platform() if x["id"] == t]
    if tt and shutil.which(tt[0]["cmd"][0]): cfgs.append((t, tt[0]["cmd"]))
base = ["nulldisk", "scan", "{path}", "--json", "--depth", "0"]
for j in JOBS: cfgs.append((f"nd-j{j}", base + ([] if j == "0" else ["--jobs", j])))
PROBE = os.environ.get("PROBE")
if PROBE and os.path.exists(PROBE):
    for st in (os.environ.get("PROBE_STRATS") or "0,1,2,3,4").split(","):
        for t in (os.environ.get("PROBE_THREADS") or "1,3,6").split(","):
            cfgs.append((f"probe-s{st}-t{t}", [PROBE, st, t, "{path}"]))
for e in EXTRA: cfgs.append((f"nd[{e}]", base + e.split()))
prep = run.cold_prepare()
out, tmp = {}, tempfile.mkdtemp()
for ds in DS:
    path = os.path.join(run.build_dataset(ds, root), "tree")
    for name, cmd in cfgs:
        argv = run.fill(cmd, path, os.path.join(tmp, "o"))
        w = run.hyperfine(argv, WARM, 3, None, os.path.join(tmp, "w.json"))
        c = run.hyperfine(argv, COLD, 0, prep, os.path.join(tmp, "c.json")) if (prep and COLD) else {}
        out[f"{ds}/{name}"] = dict(warm=w, cold=c)
        f = lambda m: "%7.1f (u%5.0f s%6.0f)" % (m["median_s"]*1e3, (m.get("user_s") or 0)*1e3, (m.get("system_s") or 0)*1e3) if m.get("median_s") else "   -   "
        print(f"{ds:13s} {name:16s} warm {f(w)}   cold {f(c)}", flush=True)
os.makedirs("results-candidate", exist_ok=True)
json.dump(out, open(os.path.join("results-candidate", f"sweep-{os.environ.get('DSB_RUNNER_LABEL','local')}.json"), "w"), indent=1)
