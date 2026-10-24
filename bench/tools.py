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
         platforms=["macos", "linux"], cmd=["nulldisk", "scan", "{path}", "--json", "--depth", "0"],
         metric="allocated", parse="nulldisk_json", precision="exact", version=["nulldisk", "--version"],
         optional=True, ok_exit=[0, 3], pin="manifest latest.json",
         notes="Maintainer's own tool (see disclosure). Installed from the public manifest "
               "https://assets.nulldisk.app/releases/cli/latest.json (override with NULLDISK_CLI_MANIFEST); "
               "listed as pending while the download is not published. '--depth 0' prints only the root total "
               "(like du -s); 'size' is allocated bytes with hard links counted once (per `nulldisk scan --help`). Not available for Windows."),
    # ---------------- GUI track ----------------
    dict(id="windirstat", name="WinDirStat", homepage="https://windirstat.net", pin="2.9.3", track="gui",
         platforms=["windows"], cmd=["WinDirStat.exe", "/SaveTo", "{out}.csv", "{path}"], metric="logical",
         parse="windirstat_csv", precision="exact", version=None, version_static="2.9.3",
         method="Official CLI: /SaveTo scans without showing the main window, writes CSV, exits. Wall time = process lifetime."),
    dict(id="spacesniffer", name="SpaceSniffer", homepage="http://www.uderzo.it/main_products/space_sniffer/", pin="1.3.0.2", track="gui",
         platforms=["windows"], cmd=["python", "{gui}/spacesniffer.py", "{path}", "{out}"], requires="SpaceSniffer.exe",
         metric="logical", parse="gui_json", precision="exact", timing="harness", version=None, version_static="1.3.0.2",
         method="Official CLI: scan <dir> export \"diskscan-bench total\" <file> autoclose. The export configuration is pre-seeded in "
                "SpaceSnifferConfig.xml and prints only the root's <%sizebytes%> (exact). Completion: process exit after the export; "
                "bench/gui/spacesniffer.py only adds a timeout."),
    # Linux GUI apps: Ubuntu packages of the runner image (apt versions are fixed per Ubuntu release), run under Xvfb and
    # driven by bench/gui/linux_atspi.py through AT-SPI. Time = launch -> completion signal (see methodology).
    dict(id="qdirstat", name="QDirStat", homepage="https://github.com/shundhammer/qdirstat", track="gui",
         platforms=["linux"], cmd=["/usr/bin/python3", "{gui}/linux_atspi.py", "qdirstat", "{path}"], requires="qdirstat",
         metric="allocated", parse="gui_json", precision="human", timing="harness",
         version=["dpkg-query", "-W", "-f=${Version}", "qdirstat"], pin="apt (Ubuntu 24.04)",
         method="`qdirstat <dir>` under Xvfb. Completion: the app's own log (/tmp/qdirstat-$USER/qdirstat.log) gets "
                "'Reading finished' for this process. Total: the root row's Size column, read via AT-SPI (human-readable)."),
    dict(id="k4dirstat", name="K4DirStat", homepage="https://github.com/jeromerobert/k4dirstat", track="gui",
         platforms=["linux"], cmd=["/usr/bin/python3", "{gui}/linux_atspi.py", "k4dirstat", "{path}"], requires="k4dirstat",
         metric="allocated", parse="gui_json", precision="human", timing="harness",
         version=["dpkg-query", "-W", "-f=${Version}", "k4dirstat"], pin="apt (Ubuntu 24.04)",
         method="`k4dirstat <dir>` under Xvfb. Completion: status bar text becomes 'Finished. Elapsed time: …' (AT-SPI). "
                "Total: the root row's Subtree Total column, read via AT-SPI (human-readable)."),
]

PLANNED_GUI = [
    ("macos", "OmniDiskSweeper", "Runs on macos-14, but scans of the benchmark's disk-image dataset volume are 50-75x slower than the same tree on the runner's boot disk (~115 s for the 150k-file tree vs a few seconds on the boot disk). Not caused by mount options (-nobrowse and case-sensitivity tested) or by TCC (Full Disk Access / removable-volume grants tested). Timing would measure the runner's disk-image layer rather than the app, and doesn't fit the 300-minute job budget. The harness (bench/gui/macos_app.py) and pinned install are kept for dedicated machines."),
    ("macos", "GrandPerspective", "Runs on macos-14, but scans of the benchmark's disk-image dataset volume are 50-75x slower than the same tree on the runner's boot disk (~50-70 s for the 150k-file tree vs a few seconds on the boot disk). Not caused by mount options (-nobrowse and case-sensitivity tested) or by TCC (Full Disk Access / removable-volume grants tested). Timing would measure the runner's disk-image layer rather than the app, and doesn't fit the 300-minute job budget. The harness (bench/gui/macos_app.py) and pinned install are kept for dedicated machines."),
    ("macos", "Disk Inventory X", "Runs on macos-14, but scans of the benchmark's disk-image dataset volume are 50-75x slower than the same tree on the runner's boot disk (~190 s for the 150k-file tree vs a few seconds on the boot disk). Not caused by mount options (-nobrowse and case-sensitivity tested) or by TCC (Full Disk Access / removable-volume grants tested). Timing would measure the runner's disk-image layer rather than the app, and doesn't fit the 300-minute job budget. The harness (bench/gui/macos_app.py) and pinned install are kept for dedicated machines."),
    ("macos", "DaisyDisk", "Commercial (trial). No CLI/AppleScript scan dictionary; would need UI automation + a licence for CI. Planned for dedicated machines with the vendor's OK."),
    ("macos", "SquirrelDisk", "Open source (Tauri) and scans by spawning pdu internally, so its engine time is approximately pdu's; GUI has no completion signal. Planned."),
    ("windows", "WizTree", "Has a proper CLI export (/export=... /admin=1, MFT scan) and would be easy to automate, but the EULA allows free use for personal use only; running it on CI for a public benchmark needs a supporter licence or the vendor's permission. Planned pending permission."),
    ("windows", "TreeSize Free", "Blocked on hosted runners by its licence: TreeSize Free 4.8.1 (current download) opens a modal 'Windows Server is not supported' dialog at launch (\"TreeSize Free is no longer supported on a Windows Server as of version 4.7.3\") and never scans; windows-latest is Windows Server 2025. Running an older build would sidestep the vendor's terms. Planned for a Windows 10/11 (desktop) runner."),
    ("linux", "Baobab (GNOME Disk Usage Analyzer)", "Ubuntu 24.04 ships Baobab 46.0 on GTK 4.14: under Xvfb + AT-SPI the end of the scan is visible (the charts appear) but the folder list exposes no rows to AT-SPI (only its column headers) and the total is only painted in the ring chart, so the total can't be read from the app. Baobab 48 / GTK 4.18 exposes the rows and works with bench/gui/linux_atspi.py; enable when ubuntu-latest ships it."),
    ("linux", "Filelight", "Ubuntu 24.04 ships Filelight 23.08 (KF5): the status bar shows 'N files' when the scan ends, but the total size is only painted in the radial map (no accessible text, no export or CLI); under Xvfb the window even stayed on its Overview page. Planned."),
    ("all", "dua / gdu / ncdu interactive TUIs", "Excluded: interactive mode renders to a terminal; their non-interactive modes are measured in the CLI track instead."),
]


# macOS GUI apps with working harnesses (bench/gui/macos_app.py, installs in install.py) that are on hold: see their
# PLANNED_GUI reason. Move an entry back into TOOLS to benchmark it (e.g. on a dedicated machine).
ON_HOLD_GUI = [
    dict(id="omnidisksweeper", name="OmniDiskSweeper", homepage="https://www.omnigroup.com/more/", pin="1.16", track="gui",
         platforms=["macos"], cmd=["python3", "{gui}/macos_app.py", "omnidisksweeper", "{path}"], requires=".tools/apps/OmniDiskSweeper.app",
         metric="allocated", parse="gui_json", precision="human", timing="harness", version=None, version_static="1.16",
         method="`open -F -a OmniDiskSweeper.app <dir>`. Completion: the folder window's title changes from '<dir> (still calculating)' / "
                "'<dir> - at least …, still calculating' to '<dir> - <size>' (CGWindowList). Total: that size (human-readable, SI units)."),
    dict(id="grandperspective", name="GrandPerspective", homepage="https://grandperspectiv.sourceforge.net/", pin="3.8.0", track="gui",
         platforms=["macos"], cmd=["python3", "{gui}/macos_app.py", "grandperspective", "{path}"], requires=".tools/apps/GrandPerspective.app",
         metric="allocated", parse="gui_json", precision="human", timing="harness", version=None, version_static="3.8.0",
         method="`open -F -a GrandPerspective.app <dir>`. While scanning it shows a 'Scanning in progress' panel; completion: the view "
                "window '<dir> @ <date>' appears (CGWindowList). Total: the window's status-line size of the folder in view, read via "
                "the accessibility tree (human-readable, binary units)."),
    dict(id="diskinventoryx", name="Disk Inventory X", homepage="https://www.derlien.com/", pin="1.3", track="gui",
         platforms=["macos"], cmd=["python3", "{gui}/macos_app.py", "diskinventoryx", "{path}"], requires=".tools/apps/Disk Inventory X.app",
         metric="allocated", parse="gui_json", precision="human", timing="harness", version=None, version_static="1.3 (x86_64, runs under Rosetta 2)",
         method="`open -F -a 'Disk Inventory X.app' <dir>`. While scanning it shows a 'Loading folder contents...' panel; completion: the "
                "document window titled '<folder> (<size>)' appears (CGWindowList). Total: that size (human-readable, SI units). "
                "Intel-only build, so it runs translated by Rosetta 2 on the arm64 runner."),
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
