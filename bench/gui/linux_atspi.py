#!/usr/bin/python3
"""GUI-track harness for Linux disk analyzers under Xvfb, read through AT-SPI.

  /usr/bin/python3 bench/gui/linux_atspi.py <app> <dir>

Needs the session from bench/gui/linux_session.sh (Xvfb, D-Bus session bus, AT-SPI bus).
Must run with the distro's python3 (python3-gi + gir1.2-atspi-2.0).

Completion signals (polled every common.POLL_S):
  qdirstat   the app's own log file (/tmp/qdirstat-$USER/qdirstat.log) gets "Reading finished" for this PID
  k4dirstat  status bar text starts with "Finished."
  baobab     root row's "Modified" cell changes from "Unknown" (set when the scan of the root completes)
  filelight  status bar / summary shows "Files: N" after the scan (see FILELIGHT notes below)
Total: the root row's size column (human-readable, as displayed).
"""
import getpass, os, signal, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import gi
gi.require_version("Atspi", "2.0")
from gi.repository import Atspi, GLib

TIMEOUT = float(os.environ.get("DSB_GUI_TIMEOUT", "900"))


def pump():
    ctx = GLib.MainContext.default()
    while ctx.pending():
        ctx.iteration(False)


def find_app(pid):
    pump()
    desk = Atspi.get_desktop(0)
    desk.clear_cache()
    for i in range(desk.get_child_count()):
        a = desk.get_child_at_index(i)
        try:
            if a is not None and a.get_process_id() == pid:
                return a
        except GLib.Error:
            pass
    return None


def walk(o, pred, limit=20000):
    """Breadth-first search; returns the first accessible matching pred."""
    q = [o]; n = 0
    while q and n < limit:
        x = q.pop(0); n += 1
        try:
            if pred(x):
                return x
            q.extend(c for c in (x.get_child_at_index(i) for i in range(x.get_child_count())) if c is not None)
        except GLib.Error:
            continue
    return None


def role(x): return x.get_role_name()
def name(x):
    x.clear_cache()
    return x.get_name() or ""


def children(x):
    return [c for c in (x.get_child_at_index(i) for i in range(x.get_child_count())) if c is not None]


def qt_root_size(app, path, column):
    """Qt QTreeView: column headers are children of the tree followed by the cells row by row."""
    tree = walk(app, lambda x: role(x) == "tree")
    cs = children(tree)
    hdr = [name(c) for c in cs if role(c) == "table column header"]
    cells = [c for c in cs if role(c) == "table cell"]
    row = next(i for i, c in enumerate(cells) if name(c).rstrip("/") == path.rstrip("/"))
    return name(cells[row + hdr.index(column)])


def run(app, path):
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(3))  # still close the app when killed by a timeout
    path = os.path.abspath(path)
    Atspi.get_desktop(0).get_child_count()  # connect to the registry before the clock starts
    env = dict(os.environ)
    argv = {"qdirstat": ["qdirstat", path], "k4dirstat": ["k4dirstat", path],
            "baobab": ["baobab", path], "filelight": ["filelight", path]}[app]
    log = f"/tmp/qdirstat-{getpass.getuser()}/qdirstat.log"
    t = common.Timer()
    p = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, start_new_session=True)
    try:
        a = None if app == "qdirstat" else common.wait_for(lambda: find_app(p.pid), 60, what="AT-SPI registration")
        if app == "qdirstat":
            tag = f"[{p.pid}]"
            def done():
                try:
                    with open(log, errors="replace") as f:
                        return any(tag in l and "Reading finished" in l for l in f)
                except OSError:
                    return False
            common.wait_for(done, TIMEOUT)
            el = t.elapsed(); sig = "log: Reading finished"
            a = common.wait_for(lambda: find_app(p.pid), 60, what="AT-SPI registration")
            txt = qt_root_size(a, path, "Size")
            total = common.human_bytes(txt, 1024)
        elif app == "k4dirstat":
            sb = common.wait_for(lambda: walk(a, lambda x: role(x) == "status bar"), 60, what="status bar")
            common.wait_for(lambda: name(sb).startswith("Finished"), TIMEOUT)
            el = t.elapsed(); sig = "status bar: " + name(sb)
            txt = qt_root_size(a, path, "Subtree Total")
            total = common.human_bytes(txt, 1024)
        elif app == "baobab":
            base = os.path.basename(path.rstrip("/"))
            def root_row():
                r = walk(a, lambda x: role(x) == "table row" and name(x).startswith(base + " "))
                return r
            row = common.wait_for(root_row, 60, what="root row")
            def done():
                c = children(row)
                return len(c) >= 4 and name(c[-1]) not in ("Unknown", "")
            common.wait_for(done, TIMEOUT)
            el = t.elapsed(); sig = "root row modified=" + name(children(row)[-1])
            txt = name(children(row)[1])
            total = common.human_bytes(txt, 1000)
        else:
            raise SystemExit(f"unknown app {app}")
        rss = common.peak_rss_linux(p.pid)
    except TimeoutError as e:
        common.kill_tree(p.pid); common.fail(str(e))
    finally:
        if p.poll() is None:
            common.kill_tree(p.pid)
    common.report(total, el, sig, rss, displayed=txt)


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2])
