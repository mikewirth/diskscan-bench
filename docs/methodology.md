# Methodology

## What is measured
Wall-clock time for a tool to walk a directory tree and produce its total (or, for GUI apps, its export), measured with
[hyperfine](https://github.com/sharkdp/hyperfine) (`-N`, no shell) with JSON export. We report the **median** and
**standard deviation**; every individual run time is kept in the raw JSON. Peak resident memory comes from hyperfine 2's
per-run measurement and from a separate instrumented run (`/usr/bin/time -v` on Linux, `/usr/bin/time -l` on macOS,
`psutil` peak working set on Windows).

Each tool is run with its **default semantics** plus only the flags needed to (a) print a single machine-readable total,
(b) disable interactive/progress UI and (c) not skip files the others count (e.g. `erd -i --hidden`). The exact commands
are in [`bench/tools.py`](https://github.com/mikewirth/diskscan-bench/blob/main/bench/tools.py) and on the results page.
Authors may PR different flags; we document every change.

## Cache modes (never mixed)
| platform | warm | cold |
|---|---|---|
| Linux | `--warmup 2`, then 10 runs | `sync; echo 3 > /proc/sys/vm/drop_caches` (sudo) before **each** run, 5 runs |
| macOS | `--warmup 2`, then 10 runs | datasets live on a dedicated case-sensitive APFS disk image; before each run it is **detached, `purge`d and re-attached** (detaching drops the volume's cached pages; `purge` alone is known to be incomplete) |
| Windows | `--warmup 2`, then 10 runs | not measured yet (planned: VHD detach/attach) |

Smoke runs (pull requests) use 3 warm / 2 cold runs on the small dataset only and are not published as headline numbers.

## Datasets
Synthetic datasets are produced by [`bench/gen.py`](https://github.com/mikewirth/diskscan-bench/blob/main/bench/gen.py) with seed 42; file contents are seeded too.

| id | shape |
|---|---|
| `small` | smoke test: 2k tiny files, depth-50 chain, 1k-entry dir, 2×8 MiB, 2 sparse, 20 hard-link groups, symlinks incl. loops, 4 APFS clones (macOS) |
| `tiny` | 150,000 files of 0–4 KiB in a two-level fan-out |
| `deep` | a 400-level chain of 1-character directory names, 2 files per level (100 levels on Windows) |
| `wide` | 50,000 entries in a single directory |
| `mixed` | 4×256 MiB files, 8 sparse 1 GiB files (4 KiB allocated), 2,000 files ×3 hard links, 200 symlinks + loop/self/dangling/dir links, 64 APFS clones of an 8 MiB file (macOS, `cp -c`), 5k misc files |
| `node_modules` | `npm ci --ignore-scripts` of a pinned lockfile ([datasets/node_modules](https://github.com/mikewirth/diskscan-bench/tree/main/datasets/node_modules)); optional per-OS binaries differ slightly by platform |
| `linux_kernel` | linux-6.6 release tarball (sha256 pinned), extracted. Not run on Windows (case-colliding file names) |

Every run records a **manifest** per dataset: file/dir/symlink counts, byte totals, and a sha256 over the sorted
`(relative path, type, size)` list, so you can check that you benchmarked the same tree.

## Correctness
[`bench/refwalk.py`](https://github.com/mikewirth/diskscan-bench/blob/main/bench/refwalk.py) is the reference walker. It never follows symlinks and does not cross devices. It computes:

- `alloc_du`: allocated bytes (`st_blocks × 512`) of every inode including directories and the root, hard links counted once. This is the canonical value for tools that report disk usage, and it matches `du -s`.
- `alloc_files_dedup`: the same without directories.
- `alloc_nodedup`: the same without hard-link dedup.
- `logical_dedup`, `logical` and `logical_with_dirs_dedup`: apparent sizes. `logical_dedup` is the canonical value on Windows, where Python exposes no allocation.

A tool **agrees** if it is within 0.1% of the canonical value; tools that print only human-readable sizes get 6%. Otherwise it is flagged
**disagrees**, and we report the semantics it is closest to (e.g. "doesn't count directory blocks", "counts hard links
twice"). Disagreeing tools stay in the charts, drawn orange with a `*`. These are differences of definition, not necessarily bugs.

## GUI track
GUI apps are timed from **process launch until the app signals that the scan is complete**, which includes app start-up
(and, where the signal is an export, writing it). GUI times are therefore **not comparable** with CLI times; GUI apps are ranked
only against each other (same `du` baseline, same datasets and cache modes, same correctness check).

**Completion signal.** Either the app's own command line (scan, export, exit), or a signal that UI automation can observe
without touching the scan: a window title, a status-bar text in the accessibility tree, or a line in a log file the app
writes. **Reported total**: always read from the app itself (its export file, window title or accessibility tree), then
judged against the reference walker exactly like a CLI tool (`human` tolerance when the app only displays rounded sizes).

**Harness.** Each automated app has a small wrapper in [`bench/gui/`](https://github.com/mikewirth/diskscan-bench/tree/main/bench/gui)
that launches the app on the dataset, polls for the completion signal **every 20 ms**, reads the total, closes the app and prints
one JSON line. The wrapper is run by hyperfine (warm-up, runs, cold-cache preparation) like every other tool, but the time we
report is the one the wrapper measures itself: from just before process launch until the signal is observed. Polling adds at most
20 ms (on average ~10 ms) to each time; reading the total and shutting the app down are not timed (the wrapper's own lifetime is kept
in the raw JSON as `wrapper_wall`). A run that doesn't complete within the timeout fails and invalidates the cell.
Peak memory for wrapped apps is the app's own peak (Linux `VmHWM`, Windows peak working set, macOS lifetime max physical footprint).

**Environment.** Linux apps run under Xvfb with a private D-Bus session and the AT-SPI accessibility bus
([`bench/gui/linux_session.sh`](https://github.com/mikewirth/diskscan-bench/blob/main/bench/gui/linux_session.sh)); they are the
**apt packages of the runner's Ubuntu release** (versions are pinned by the release, recorded per run with `dpkg-query`).
macOS apps are sha256-pinned disk-image downloads; GitHub's macOS images run with SIP disabled and already grant the runner's
process tree Accessibility and Screen Recording in TCC, so window titles and the accessibility tree are readable without changes.
Windows apps are sha256-pinned zip downloads.

| app | platform | completion signal | total read from | status |
|---|---|---|---|---|
| WinDirStat 2.9.3 | Windows | `WinDirStat.exe /SaveTo out.csv <dir>` exits after writing the CSV | CSV export (exact) | implemented |
| SpaceSniffer 1.3.0.2 | Windows | `SpaceSniffer.exe scan <dir> export "diskscan-bench total" out.txt autoclose` exits after the export | export using a pre-seeded export configuration (`<%sizebytes%>` of the root, exact) | implemented |
| QDirStat (Ubuntu apt) | Linux | the app's log `/tmp/qdirstat-$USER/qdirstat.log` gets "Reading finished" for this PID | root row *Size* via AT-SPI (human-readable) | implemented |
| K4DirStat (Ubuntu apt) | Linux | status bar becomes "Finished. Elapsed time: …" (AT-SPI) | root row *Subtree Total* via AT-SPI (human-readable) | implemented |
| OmniDiskSweeper 1.16 | macOS | window title changes from "… (still calculating)" to "<dir> - <size>" (CGWindowList) | that title (human-readable) | implemented |
| GrandPerspective 3.8.0 | macOS | the view window "<dir> @ <date>" appears after the "Scanning in progress" panel (CGWindowList) | view status line via the accessibility tree (human-readable) | implemented |
| Disk Inventory X 1.3 | macOS | the document window "<folder> (<size>)" appears after the "Loading folder contents…" panel (CGWindowList) | that title (human-readable) | implemented; Intel-only build, runs under Rosetta 2 |
| TreeSize Free 4.8.1 | Windows | – | – | blocked: shows a modal "Windows Server is not supported" licence dialog (since 4.7.3) and never scans; the hosted runner is Windows Server 2025 |
| Baobab 46.0 (Ubuntu 24.04) | Linux | charts appear when done (AT-SPI) | – | blocked: GTK 4.14 exposes no list rows to AT-SPI and the total is only painted in the chart. Baobab 48/GTK 4.18 works with the same harness |
| Filelight 23.08 (Ubuntu 24.04) | Linux | status bar shows "N files" | – | blocked: total only painted in the radial map (no accessible text, no export/CLI) |
| WizTree | Windows | `/export= /admin=1` CLI exists | – | planned: EULA is free for personal use only |
| DaisyDisk | macOS | – | – | planned: commercial, no scripting |
| SquirrelDisk | macOS | – | – | planned: uses pdu internally |
| dua / gdu / ncdu TUIs | all | – | – | excluded: their non-interactive modes are in the CLI track |

## Hardware and noise
Runs currently use **GitHub-hosted runners** (`ubuntu-latest` x86-64, `macos-14` Apple Silicon, `windows-latest`).
These are shared VMs with network-backed or virtualised storage, so the numbers are **indicative**. Use them for
relative comparisons within one run. Every result file records the runner image, CPU model, vCPU count, RAM and filesystem.
Dedicated machines can be added as extra matrix entries: a self-hosted runner with label `DSB_RUNNER_LABEL`, using the same scripts.
Results land in `results/<date>/<runner-label>/results.json`.

## NullDisk
The maintainer's own engine is included through its public CLI download only (manifest
`https://assets.nulldisk.app/releases/cli/latest.json`). It is shown as *pending* until that download is live.
No private code is part of this repository.

## Leaderboard score
**Speed score** = the geometric mean, over every scored (dataset, cache mode) cell, of `baseline median time / tool median time`.

- The baseline is the platform's `du`: GNU du on Linux, BSD du on macOS, Sysinternals du on Windows. The baseline scores exactly 1.00×; 2.00× means twice as fast as `du` on a typical cell. Higher is better.
- Cells are each dataset × {cold, warm}. On Windows they are warm only, because cold cache isn't measured there yet.
- We use the geometric mean so that no single dataset dominates and a 2× win and a 2× loss cancel out.
- A cell is skipped when the timed runs failed or exited differently from the instrumented run. A tool must cover at least half of the cells to be ranked.
- A dataset is held out of scoring when its reference is suspect. That means no exact-output tool matches the reference within 0.1% while at least 3 tools agree with each other. Datasets can also be held out explicitly. Currently held out: **macOS `node_modules`**. BSD du and the reference walker agree there, but every other tool reports exactly 2.3% less, and we are investigating.
- Accuracy issues never remove a tool from the ranking; they add a ⚠ marker that links to the correctness table.
- The GUI track is ranked separately against the same baseline. GUI times include app launch (and export or the harness's completion signal), so only compare GUI apps with each other.
- Cold and Warm on the leaderboard are the geometric mean of the tool's median times across scored datasets.
