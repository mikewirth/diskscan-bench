"""Tool registry. Tool authors: PR your preferred flags here (see CONTRIBUTING.md).

Fields
  cmd       argv template; {path} = dataset root, {out} = scratch export file
  metric    which quantity the tool reports by default: "allocated" or "logical"
  parse     how to extract the reported total from stdout (see run.py PARSERS)
  precision "exact" | "human" (human-readable output only -> rounding tolerance)
  track     "cli" or "gui"
  status    "active" | "pending" | "planned" (planned/pending are listed, not run)
"""
import os, sys

PLAT = "windows" if os.name == "nt" else ("macos" if sys.platform == "darwin" else "linux")
EXE = ".exe" if PLAT == "windows" else ""

TOOLS = [
    dict(id="du", name="du (system)", homepage="https://www.gnu.org/software/coreutils/",
         platforms=["linux", "macos"], cmd=["du", "-sk", "{path}"], metric="allocated",
         parse="first_int_kib", precision="kib", version=["du", "--version"],
         notes="GNU coreutils on Linux, BSD du on macOS (version = OS build)."),
    dict(id="du-sysinternals", name="du (Sysinternals)", homepage="https://learn.microsoft.com/sysinternals/downloads/du",
         platforms=["windows"], cmd=["du64", "-accepteula", "-nobanner", "-c", "-q", "{path}"], metric="logical",
         parse="sysinternals_csv", precision="exact", version=None, version_static="1.62"),
    dict(id="diskus", name="diskus", homepage="https://github.com/sharkdp/diskus", pin="0.9.0",
         platforms=["linux", "macos", "windows"], cmd=["diskus", "{path}"], metric="allocated",
         parse="first_int", precision="exact", version=["diskus", "--version"]),
    dict(id="dust", name="dust", homepage="https://github.com/bootandy/dust", pin="1.2.6",
         platforms=["linux", "macos", "windows"], cmd=["dust", "-d", "0", "-b", "-o", "b", "-P", "{path}"],
         metric="allocated", parse="first_int", precision="exact", version=["dust", "--version"]),
    dict(id="dua", name="dua-cli", homepage="https://github.com/Byron/dua-cli", pin="2.45.1",
         platforms=["linux", "macos", "windows"], cmd=["dua", "-f", "bytes", "aggregate", "{path}"],
         metric="allocated", parse="last_int", precision="exact", version=["dua", "--version"]),
    dict(id="gdu", name="gdu", homepage="https://github.com/dundee/gdu", pin="5.38.0",
         platforms=["linux", "macos", "windows"], cmd=["gdu", "-n", "-s", "-p", "--no-prefix", "{path}"],
         metric="allocated", parse="first_int", precision="exact", version=["gdu", "--version"]),
    dict(id="ncdu", name="ncdu (JSON export)", homepage="https://dev.yorhel.nl/ncdu", pin="2.9.1",
         platforms=["linux", "macos"], cmd=["ncdu", "-0", "-x", "-o", "{out}", "{path}"],
         metric="allocated", parse="ncdu_json", precision="exact", version=["ncdu", "--version"],
         notes="Non-interactive export mode (-o); includes writing the JSON export."),
    dict(id="pdu", name="pdu (parallel-disk-usage)", homepage="https://github.com/KSXGitHub/parallel-disk-usage", pin="0.24.0",
         platforms=["linux", "macos", "windows"],
         cmd=["pdu", "--quantity=block-size", "--bytes-format=plain", "--max-depth=1", "{path}"],
         metric="allocated", parse="last_int", precision="exact", version=["pdu", "--version"],
         platform_cmd={"windows": ["pdu", "--quantity=apparent-size", "--bytes-format=plain", "--max-depth=1", "{path}"]},
         platform_metric={"windows": "logical"}),
    dict(id="erdtree", name="erdtree (erd)", homepage="https://github.com/solidiquis/erdtree", pin="3.1.2",
         platforms=["linux", "macos", "windows"],
         cmd=["erd", "-i", "--hidden", "-d", "physical", "-L", "1", "-y", "iflat", "--color", "none", "{path}"],
         metric="allocated", parse="first_int", precision="exact", version=["erd", "--version"],
         notes="-i/--hidden so .gitignore'd and hidden files are counted like every other tool."),
    dict(id="dumac", name="dumac", homepage="https://github.com/healeycodes/dumac", pin="git:1ffbe3c38d1066c45cac9b4ec1e31eb74edc1076",
         platforms=["macos"], cmd=["dumac", "{path}"], metric="allocated", parse="human", precision="human",
         version=None, version_static="git 1ffbe3c"),
    dict(id="nulldisk", name="NullDisk CLI", homepage="https://nulldisk.app",
         platforms=["macos", "linux"], cmd=["nulldisk", "scan", "{path}", "--json"],
         metric="allocated", parse="nulldisk_json", precision="exact", version=["nulldisk", "--version"],
         optional=True, ok_exit=[0, 3],
         notes="Maintainer's own tool (see disclosure). Installed from the public manifest "
               "https://assets.nulldisk.app/releases/cli/latest.json (override with NULLDISK_CLI_MANIFEST); "
               "listed as pending while the download is not published."),
    # ---------------- GUI track ----------------
    dict(id="windirstat", name="WinDirStat", homepage="https://windirstat.net", pin="2.9.3", track="gui",
         platforms=["windows"], cmd=["WinDirStat.exe", "/SaveTo", "{out}.csv", "{path}"], metric="logical",
         parse="windirstat_csv", precision="exact", version=None, version_static="2.9.3",
         method="Official CLI: /SaveTo scans without showing the main window, writes CSV, exits. Wall time = process lifetime."),
    dict(id="spacesniffer", name="SpaceSniffer", homepage="http://www.uderzo.it/main_products/space_sniffer/", pin="1.3.0.2", track="gui",
         platforms=["windows"], cmd=["SpaceSniffer.exe", "scan", "{path}", "export", "Grouped by folder", "{out}.txt", "autoclose"],
         metric="logical", parse="none", precision="none", version=None, version_static="1.3.0.2", optional=True,
         method="Official CLI: scan + export + autoclose. Opens the treemap window; wall time = until autoclose after export."),
]

PLANNED_GUI = [
    ("macos", "GrandPerspective", "Accepts a folder on the command line and starts scanning, but has no auto-save/exit or completion signal. Needs Accessibility (UI scripting) to detect the finished window; GitHub macOS runners cannot grant TCC Accessibility permission non-interactively. Planned for dedicated machines."),
    ("macos", "DaisyDisk", "Commercial (trial). No CLI/AppleScript scan dictionary; would need UI automation + a licence for CI. Planned for dedicated machines with the vendor's OK."),
    ("macos", "OmniDiskSweeper", "Free, but no scripting/CLI; completion only visible in UI. Needs Accessibility automation (planned, dedicated machine)."),
    ("macos", "Disk Inventory X", "Free/GPL, no CLI; UI automation needed (planned). Older builds are Intel-only."),
    ("macos", "SquirrelDisk", "Open source (Tauri) and scans by spawning pdu internally, so its engine time is approximately pdu's; GUI has no completion signal. Planned."),
    ("windows", "WizTree", "Has a proper CLI export (/export=... /admin=1, MFT scan) and would be easy to automate, but the EULA allows free use for personal use only; running it on CI for a public benchmark needs a supporter licence or the vendor's permission. Planned pending permission."),
    ("windows", "TreeSize Free", "Free edition exposes no scan/export command-line switches (CLI is Professional-only). Would need UI automation (pywinauto) waiting for the scan to finish. Planned."),
    ("linux", "Baobab (GNOME Disk Usage Analyzer)", "No export/exit mode; completion only in UI. Needs AT-SPI automation under Xvfb. Planned."),
    ("linux", "QDirStat", "GUI has no scan-and-exit mode; its bundled qdirstat-cache-writer is a separate Perl script, not the GUI's engine. Planned (UI automation or a --slow-update-free headless mode if upstream adds one)."),
    ("all", "dua / gdu / ncdu interactive TUIs", "Excluded: interactive mode renders to a terminal; their non-interactive modes are measured in the CLI track instead."),
]


def for_platform(plat=PLAT):
    out = []
    for t in TOOLS:
        if plat not in t["platforms"]:
            continue
        t = dict(t)
        t.setdefault("track", "cli"); t.setdefault("status", "active")
        if "platform_cmd" in t and plat in t["platform_cmd"]:
            t["cmd"] = t["platform_cmd"][plat]
        if "platform_metric" in t and plat in t["platform_metric"]:
            t["metric"] = t["platform_metric"][plat]
        out.append(t)
    return out
