# diskscan-bench

A neutral, reproducible benchmark of **disk-usage scanners**: `du`, diskus, dust, dua-cli, gdu, ncdu, pdu, erdtree, dumac,
Sysinternals du, and GUI analyzers (WinDirStat today; more planned). It covers **macOS, Linux and Windows**, measures
**cold and warm cache separately**, and has a **correctness table** that compares each tool's total with a reference walker.

**Results:** https://mikewirth.github.io/diskscan-bench/ · **Methodology:** https://mikewirth.github.io/diskscan-bench/methodology.html · raw JSON in [`results/`](results/)

> **Disclosure.** This project is maintained by Michael Wirth, the maker of [NullDisk](https://nulldisk.app), a macOS
> disk analyzer that is also benchmarked here (via its public CLI). To keep this fair, everything is public: the harness, every flag,
> the datasets and the raw per-run data. **Tool authors can change their own tool's flags by pull request.** Disagreements
> in totals are flagged, never used to exclude a tool.

> **Noise caveat.** Numbers currently come from GitHub-hosted runners (shared VMs). They are indicative, so compare tools
> within one run. Runner specs are recorded with every result. Dedicated machines can be added later.

## Run it yourself
```sh
python3 bench/install.py                 # pinned tool versions -> .tools/bin
python3 bench/run.py --profile smoke     # small dataset, fast
python3 bench/run.py --profile full      # all datasets (needs ~5 GB, sudo for cold cache on Linux)
python3 site/build.py                    # static site -> _site/
```
On macOS, cold-cache runs need the dataset on a dedicated disk image (see `.github/workflows/bench.yml` for the `hdiutil` setup and the `DSB_DMG`/`DSB_MNT` variables).

## Layout
| path | what |
|---|---|
| `bench/tools.py` | tool registry: commands, pinned versions, how totals are parsed; also the planned GUI tools with reasons |
| `bench/install.py` | pinned installs (release binaries, or `cargo install --locked` / brew where needed) |
| `bench/gen.py` | deterministic dataset generator (seed 42) |
| `bench/refwalk.py` | reference walker and dataset manifest |
| `bench/run.py` | runner: hyperfine warm/cold, peak RSS, correctness, runner specs, JSON output |
| `results/<date>/<runner>/results.json` | versioned results (CC-BY-4.0) |
| `site/build.py` | static site, charts, correctness table and SVG badges, published by GitHub Pages |

## Badges
Each tool gets a badge, e.g. `https://mikewirth.github.io/diskscan-bench/badges/dust.svg`. See the [badges page](https://mikewirth.github.io/diskscan-bench/badges.html).

## Adding or tuning a tool
Open a [“Submit your tool”](../../issues/new?template=submit-tool.yml) issue, or send a PR to `bench/tools.py`. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License
Code: MIT OR Apache-2.0 ([LICENSE-MIT](LICENSE-MIT), [LICENSE-APACHE](LICENSE-APACHE)). Results data and charts: [CC-BY-4.0](results/LICENSE).
Third-party tools are downloaded at run time from their upstream releases under their own licences and are not redistributed here.
