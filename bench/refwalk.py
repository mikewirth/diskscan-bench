#!/usr/bin/env python3
"""Reference walker: the ground truth every tool is compared against.

Rules (documented in docs/methodology.md):
  * never follows symlinks; a symlink counts as one entry with its own lstat size
  * does not cross filesystem boundaries
  * "alloc_du" = sum(st_blocks*512) over every inode incl. directories and the root,
    each inode counted once (GNU/BSD du semantics)
Prints JSON. With --manifest also emits a sha256 over sorted (path,type,size).
"""
import os, sys, json, hashlib, stat

def walk(root, manifest=False):
    r = dict(files=0, dirs=0, symlinks=0, entries=0,
             logical=0, logical_dedup=0, logical_with_dirs=0, logical_with_dirs_dedup=0,
             alloc_du=0, alloc_files_dedup=0, alloc_nodedup=0, alloc_files_nodedup=0,
             hardlinked_inodes=0)
    seen = set()
    lines = [] if manifest else None
    has_blocks = hasattr(os.stat_result, "st_blocks")
    st0 = os.lstat(root)
    dev = st0.st_dev
    stack = [(root, "")]
    def account(st, isdir, rel, kind):
        alloc = st.st_blocks * 512 if has_blocks else 0
        key = (st.st_dev, st.st_ino)
        first = key not in seen or st.st_ino == 0
        if st.st_nlink > 1 and not isdir and first:
            r["hardlinked_inodes"] += 1
        seen.add(key)
        r["alloc_nodedup"] += alloc
        r["logical_with_dirs"] += st.st_size
        if first:
            r["alloc_du"] += alloc
            r["logical_with_dirs_dedup"] += st.st_size
        if not isdir:
            r["logical"] += st.st_size
            r["alloc_files_nodedup"] += alloc
            if first:
                r["logical_dedup"] += st.st_size
                r["alloc_files_dedup"] += alloc
        if lines is not None:
            lines.append(f"{rel}\t{kind}\t{0 if isdir else st.st_size}")
    account(st0, True, ".", "d")
    while stack:
        path, rel = stack.pop()
        try:
            it = list(os.scandir(path))
        except OSError:
            continue
        for e in it:
            st = os.lstat(e.path) if os.name == "nt" else e.stat(follow_symlinks=False)
            erel = f"{rel}/{e.name}" if rel else e.name
            r["entries"] += 1
            if stat.S_ISLNK(st.st_mode):
                r["symlinks"] += 1; r["files"] += 1
                account(st, False, erel, "l")
            elif stat.S_ISDIR(st.st_mode):
                r["dirs"] += 1
                account(st, True, erel, "d")
                if st.st_dev == dev:
                    stack.append((e.path, erel))
            else:
                r["files"] += 1
                account(st, False, erel, "f")
    if lines is not None:
        lines.sort()
        h = hashlib.sha256("\n".join(lines).encode()).hexdigest()
        r["manifest_sha256"] = h
    if not has_blocks:
        for k in ("alloc_du", "alloc_files_dedup", "alloc_nodedup", "alloc_files_nodedup"):
            r[k] = None
    return r

if __name__ == "__main__":
    print(json.dumps(walk(sys.argv[1], manifest="--manifest" in sys.argv), indent=1))
