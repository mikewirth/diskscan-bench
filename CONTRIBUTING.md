# Contributing

## Inclusion rules
A tool is included if it:
1. computes the size of a directory tree (a CLI, or a GUI with a scriptable scan-and-exit/export mode or a completion signal and total that UI automation can read reliably, see the GUI track in the methodology);
2. has a public, versioned release we can download in CI. Its licence must allow automated use on CI;
3. can print or export a total (or a full tree we can sum) without interaction.

Commercial tools are welcome if the licence allows CI use or the vendor gives permission in a public issue.

## Tool authors: tuning your flags
Edit your entry in `bench/tools.py` (`cmd`, `metric`, `parse`) and the pinned version in `bench/install.py`. In the PR, say
**why** the flags are representative of how users run the tool. We accept flags that select threads, output format, or
semantics (e.g. hard-link dedup), as long as the semantics are labelled honestly. We do not accept flags that skip parts of the
dataset the other tools count. The PR smoke test must pass.

## Disputes
If you think a result or correctness flag is wrong, open an issue with the run's `results.json` path. We would rather
fix the harness than argue. Maintainer's conflict of interest: see the disclosure in the README. NullDisk gets no special
treatment, and its entry follows the same rules.

## Development
`python3 bench/run.py --profile smoke --tools dust,gdu` runs a quick local check. Keep the code dependency-free
(Python stdlib only; `psutil` is optional on Windows).

By contributing, you agree to license code under MIT OR Apache-2.0 and data under CC-BY-4.0.
