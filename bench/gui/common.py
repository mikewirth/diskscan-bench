"""Shared helpers for GUI-track harnesses (see docs/methodology.md, "GUI track").

A harness launches the app on a folder, polls for the app's completion signal, reads the
reported total from the app itself, closes the app and prints one JSON line:

  {"total_bytes": int, "elapsed_s": float, "signal": str, "peak_rss_bytes": int|null, ...}

elapsed_s = wall time from just before process launch until the completion signal was observed.
It is also appended to the file named by $DSB_GUI_TIMES (one line per run) so run.py can use it
instead of the wrapper's own lifetime, which additionally includes reading the total and shutdown.
"""
import json, os, re, subprocess, sys, time

POLL_S = 0.02  # completion-signal polling interval; adds at most this much latency to elapsed_s

UNITS = {"": 0, "B": 0, "BYTES": 0, "K": 1, "KB": 1, "M": 2, "MB": 2, "G": 3, "GB": 3, "T": 4, "TB": 4,
         "KIB": 1, "MIB": 2, "GIB": 3, "TIB": 4}


def human_bytes(text, base=1024):
    """'30.9 MB' -> int. base: 1024 for apps that mean MiB by 'MB' (Qt/KDE dirstats), 1000 for SI (macOS, GNOME)."""
    m = re.search(r"([\d][\d.,   ]*)\s*([KMGT]i?B|[KMGT]|bytes?|B)\b", text.replace(" ", " "), re.I)
    if not m:
        raise ValueError(f"no size in {text!r}")
    num = m.group(1).replace(" ", "").replace(" ", "")
    if "," in num and "." in num: num = num.replace(",", "")
    elif "," in num: num = num.replace(",", "." if len(num.split(",")[-1]) != 3 else "")
    unit = m.group(2).upper()
    unit = "B" if unit.startswith("BYTE") else unit
    b = 1024 if unit.endswith("IB") else base
    return int(round(float(num) * b ** UNITS[unit]))


class Timer:
    def __init__(self):
        self.t0 = time.perf_counter()

    def elapsed(self):
        return time.perf_counter() - self.t0


def wait_for(pred, timeout, interval=POLL_S, what="completion"):
    """Poll pred() until it returns a truthy value; returns it. Raises TimeoutError."""
    end = time.perf_counter() + timeout
    while True:
        v = pred()
        if v:
            return v
        if time.perf_counter() > end:
            raise TimeoutError(f"no {what} signal within {timeout}s")
        time.sleep(interval)


def kill_tree(pid):
    try:
        import psutil
        p = psutil.Process(pid)
        procs = p.children(recursive=True) + [p]
        for c in procs:
            try: c.kill()
            except psutil.NoSuchProcess: pass
        psutil.wait_procs(procs, timeout=10)
        return
    except ImportError:
        pass
    except Exception:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
    else:
        try: os.killpg(pid, 9)  # harnesses start the app with start_new_session=True
        except (ProcessLookupError, PermissionError):
            try: os.kill(pid, 9)
            except ProcessLookupError: pass


def peak_rss_linux(pid):
    try:
        for l in open(f"/proc/{pid}/status"):
            if l.startswith("VmHWM:"):
                return int(l.split()[1]) * 1024
    except OSError:
        return None


def report(total, elapsed, signal, peak_rss=None, **extra):
    fn = os.environ.get("DSB_GUI_TIMES")
    if fn:
        with open(fn, "a") as f:
            f.write(f"{elapsed:.6f}\n")
    print(json.dumps(dict(total_bytes=total, elapsed_s=round(elapsed, 6), signal=signal,
                          peak_rss_bytes=peak_rss, poll_s=POLL_S, **extra)), flush=True)


def fail(msg, code=2):
    print(json.dumps(dict(error=msg)), flush=True)
    sys.exit(code)
