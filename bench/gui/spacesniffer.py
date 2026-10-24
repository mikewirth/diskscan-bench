"""GUI-track harness for SpaceSniffer 1.3.0.2 (Windows).

  python bench/gui/spacesniffer.py <dir> <out-prefix>

Uses SpaceSniffer's own command line: `scan <dir> export "diskscan-bench total" <file> autoclose`. The export
configuration "diskscan-bench total" is pre-seeded by bench/install.py into SpaceSnifferConfig.xml next to the
executable (bench/gui/SpaceSnifferConfig.xml = the app's defaults + one config whose footer prints the root's
<%sizebytes%>), so the total is exact and the export does not write one line per file.
Completion signal: process exit after the export (autoclose). The harness only adds a timeout, so a hang fails
the run instead of stalling the benchmark, and records the app's peak working set.
"""
import os, re, shutil, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

TIMEOUT = float(os.environ.get("DSB_GUI_TIMEOUT", "900"))


def main(path, out):
    exe = shutil.which("SpaceSniffer.exe") or common.fail("SpaceSniffer.exe not on PATH")
    fn = out + ".txt"
    if os.path.exists(fn):
        os.remove(fn)
    import psutil
    t = common.Timer()
    p = psutil.Popen([exe, "scan", os.path.abspath(path), "export", "diskscan-bench total", fn, "autoclose"])
    peak = 0
    while p.poll() is None:
        try:
            peak = max(peak, p.memory_info().peak_wset)
        except psutil.Error:
            pass
        if t.elapsed() > TIMEOUT:
            common.kill_tree(p.pid); common.fail(f"SpaceSniffer did not exit within {TIMEOUT}s")
        time.sleep(common.POLL_S)
    el = t.elapsed()
    try:
        txt = open(fn, encoding="utf-8-sig", errors="replace").read()
    except OSError:
        common.fail(f"no export written (exit code {p.returncode})")
    kv = dict(re.findall(r"^(\w+)=(\d+)\s*$", txt, re.M))
    if "sizebytes" not in kv:
        common.fail(f"unexpected export: {txt[:200]!r}")
    common.report(int(kv["sizebytes"]), el, f"process exit {p.returncode} after export", peak or None,
                  disk_size_bytes=int(kv["disksizebytes"]), files=int(kv.get("files", 0)))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
