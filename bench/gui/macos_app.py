"""GUI-track harness for macOS disk analyzers (pyobjc: Quartz + ApplicationServices).

  python3 bench/gui/macos_app.py <app-id> <dir>

The app is launched with `open -F -a <bundle> <dir>` (LaunchServices "open document", fresh state). Completion
signals are read from the window list (CGWindowListCopyWindowInfo; window titles need the Screen Recording
permission, which GitHub's macOS images grant to the runner's process tree) or the accessibility tree
(AXUIElement; Accessibility is likewise pre-granted on the images), polled every common.POLL_S.
Apps are installed by bench/install.py into .tools/apps.
"""
import ctypes, os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import Quartz as Q
import ApplicationServices as AS
from AppKit import NSRunningApplication

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
APPS = os.path.join(ROOT, ".tools", "apps")
TIMEOUT = float(os.environ.get("DSB_GUI_TIMEOUT", "900"))
SPEC = {  # id -> (bundle name, bundle identifier)
    "diskinventoryx": ("Disk Inventory X.app", "com.derlien.DiskInventoryX"),
    "grandperspective": ("GrandPerspective.app", "net.sourceforge.grandperspectiv"),
    "omnidisksweeper": ("OmniDiskSweeper.app", "com.omnigroup.OmniDiskSweeper"),
}


def running(bid):
    return [a for a in NSRunningApplication.runningApplicationsWithBundleIdentifier_(bid) if not a.isTerminated()]


def window_titles(pid):
    L = Q.CGWindowListCopyWindowInfo(Q.kCGWindowListOptionAll, Q.kCGNullWindowID) or []
    return [w.get("kCGWindowName") or "" for w in L if w.get("kCGWindowOwnerPID") == pid]


def ax(e, a):
    err, v = AS.AXUIElementCopyAttributeValue(e, a, None)
    return v if err == 0 else None


def ax_find(e, pred, depth=0, maxdepth=12):
    if depth > maxdepth:
        return None
    if pred(e):
        return e
    for c in ax(e, "AXChildren") or []:
        r = ax_find(c, pred, depth + 1, maxdepth)
        if r is not None:
            return r
    return None


class RusageV4(ctypes.Structure):
    _fields_ = [("uuid", ctypes.c_uint8 * 16)] + [(f"f{i}", ctypes.c_uint64) for i in range(40)]


def peak_footprint(pid):
    """ri_lifetime_max_phys_footprint (bytes) via proc_pid_rusage(RUSAGE_INFO_V4)."""
    try:
        lib = ctypes.CDLL("/usr/lib/libproc.dylib")
        r = RusageV4()
        if lib.proc_pid_rusage(pid, 4, ctypes.byref(r)) != 0:
            return None
        return int(r.f28)  # 29th uint64 after the uuid
    except Exception:
        return None


def kill_all(bid):
    for a in running(bid):
        try: os.kill(a.processIdentifier(), 9)
        except ProcessLookupError: pass
    common.wait_for(lambda: not running(bid), 20, what="previous instance exit")


def run(app, path):
    path = os.path.abspath(path)
    bundle, bid = SPEC[app]
    bpath = os.path.join(APPS, bundle)
    if not os.path.isdir(bpath):
        common.fail(f"{bpath} not installed")
    kill_all(bid)
    # no window restoration from an earlier (killed) run
    subprocess.run(["defaults", "write", bid, "NSQuitAlwaysKeepsWindows", "-bool", "false"])
    subprocess.run(["defaults", "write", bid, "ApplePersistenceIgnoreState", "-bool", "true"])
    t = common.Timer()
    subprocess.run(["open", "-F", "-a", bpath, path], check=True)
    pid = common.wait_for(lambda: (running(bid) or [None])[0], 60, what="app launch").processIdentifier()
    try:
        if app == "diskinventoryx":
            # While scanning DIX shows a "Loading folder contents..." panel; when done it opens the document
            # window titled "<folder name> (<total size>)".
            pat = re.compile(re.escape(os.path.basename(path)) + r" \((.+)\)$")
            def done():
                return next((m for m in (pat.match(n) for n in window_titles(pid)) if m), None)
            m = common.wait_for(done, TIMEOUT)
            el = t.elapsed(); sig = f"window title {m.group(0)!r}"
            txt = m.group(1); total = common.human_bytes(txt, 1000)
        elif app == "omnidisksweeper":
            # Window title: "<path> (still calculating)" -> "<path> - at least <size>, still calculating" -> "<path> - <size>"
            pat = re.compile(re.escape(path) + r" - ([\d.,]+\s*\S*B|Zero KB|\d+ bytes?)$")
            def done():
                return next((m for m in (pat.match(n) for n in window_titles(pid)) if m), None)
            m = common.wait_for(done, TIMEOUT)
            el = t.elapsed(); sig = f"window title {m.group(0)!r}"
            txt = m.group(1); total = common.human_bytes(txt, 1000)
        elif app == "grandperspective":
            # While scanning: "Scanning in progress" panel; when done the view window "<dir> @ <date>" opens. Its status
            # line holds two labels: the hovered/selected item's path (empty when none) and a size, which is then the
            # size of the folder in view, i.e. the scan total (binary units, e.g. "585 MB" = 585 MiB, 3 significant digits).
            prefix = path + " @ "
            common.wait_for(lambda: any(n.startswith(prefix) for n in window_titles(pid)), TIMEOUT)
            el = t.elapsed(); sig = "view window '<dir> @ <date>' opened"
            axapp = AS.AXUIElementCreateApplication(pid)
            def total_label():
                w = next((w for w in ax(axapp, "AXWindows") or [] if (ax(w, "AXTitle") or "").startswith(prefix)), None)
                vals = [ax(c, "AXValue") or "" for c in (ax(w, "AXChildren") or []) if ax(c, "AXRole") == "AXStaticText"] if w else []
                sizes = [v for v in vals if re.fullmatch(r"[\d.,]+\s*(bytes?|[KMGT]B)", v)]
                return sizes[0] if sizes and "" in vals else None
            txt = common.wait_for(total_label, 30, what="total label")
            total = common.human_bytes(txt, 1024)
        else:
            common.fail(f"no harness for {app}")
        rss = peak_footprint(pid)
    except TimeoutError as e:
        kill_all(bid); common.fail(str(e))
    kill_all(bid)
    common.report(total, el, sig, rss, displayed=txt)


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2])
