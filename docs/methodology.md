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
GUI apps are timed only when the app itself can be told to scan a folder **and signal completion** (exit after an export).
They are timed from process launch to exit, which includes app start-up and writing the export, so GUI times are **not comparable** with CLI times.
Apps that would need UI automation or a commercial licence on CI are listed as *planned* with the reason.

| app | platform | method | status |
|---|---|---|---|
| WinDirStat 2.9.3 | Windows | `WinDirStat.exe /SaveTo out.csv <dir>`: scans without showing the main window, writes CSV, exits | implemented |
| SpaceSniffer 1.3.0.2 | Windows | `SpaceSniffer.exe scan <dir> export "Grouped by folder" out.txt autoclose` | planned: process never exits on the hosted runner (modal/first-run dialog suspected) |
| WizTree | Windows | `/export= /admin=1` CLI exists | planned: EULA is free for personal use only |
| TreeSize Free | Windows | no CLI in the Free edition | planned: UI automation |
| GrandPerspective | macOS | CLI launch starts a scan, but there is no completion or exit signal | planned: needs Accessibility (TCC), which can't be granted on hosted runners |
| DaisyDisk | macOS | commercial, no scripting | planned |
| OmniDiskSweeper, Disk Inventory X | macOS | no scripting | planned: UI automation |
| SquirrelDisk | macOS | uses pdu internally | planned |
| Baobab, QDirStat | Linux | no scan-and-exit mode | planned: AT-SPI / Xvfb automation |
| dua / gdu / ncdu TUIs | all | interactive | excluded: their non-interactive modes are in the CLI track |

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
