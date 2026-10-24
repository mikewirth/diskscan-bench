"""Every known disk-usage analyzer, benchmarked or not (rendered on catalog.html).

This file only holds facts about the programs (name, link, platforms, kind, licence, a one-line description and,
for programs the benchmark does not run, why not). Benchmark status is NOT set here: site/build.py merges this list
with bench/tools.py, so
  - a program whose `id` (or name) matches a TOOLS entry with results on an OS shows as "Benchmarked" there;
  - a program named in PLANNED_GUI shows as "Planned" with the reason from bench/tools.py;
  - anything else shows as "Not benchmarked" with `reason` (or `reason_by_os[os]`) and the short `tag`.
TOOLS / PLANNED_GUI entries missing here are added automatically.

Fields: id, name, url, platforms (macos/linux/windows), kind (cli|tui|gui), license, blurb,
        tag + reason (+ optional reason_by_os) for programs that aren't benchmarked, aliases (extra names to match).
"""

CATALOG = []
