#!/usr/bin/env python3
"""Deterministic synthetic dataset generator for diskscan-bench.

Every profile is a pure function of (profile, seed, scale). File *contents* are
derived from the seed too, so two runs produce byte-identical trees (apart from
timestamps and inode numbers, which the manifest ignores).

Usage: gen.py --out DIR --profile NAME [--seed 42] [--scale 1.0]
"""
import argparse, os, random, sys, subprocess, platform

IS_WIN = os.name == "nt"
IS_MAC = sys.platform == "darwin"

CHUNK = bytes(random.Random(1).getrandbits(8) for _ in range(1 << 16))  # 64 KiB pattern


def write_file(path, size, rng):
    # Pattern-based content: cheap, deterministic, not all-zero (avoids FS zero detection).
    off = rng.randrange(len(CHUNK))
    with open(path, "wb") as f:
        left = size
        while left > 0:
            n = min(left, len(CHUNK) - off)
            f.write(CHUNK[off:off + n])
            left -= n
            off = 0


def tiny_files(root, rng, n, fanout=64, maxsize=4096):
    """n small files in a 2-level fan-out tree (like a source tree / cache dir)."""
    for i in range(n):
        d = os.path.join(root, f"d{(i // fanout) % fanout:02x}", f"e{i // (fanout * fanout):03x}")
        os.makedirs(d, exist_ok=True)
        write_file(os.path.join(d, f"f{i:07d}.dat"), rng.randrange(0, maxsize), rng)


def deep_tree(root, rng, depth, files_per_level=2):
    p = root
    for lvl in range(depth):
        p = os.path.join(p, "d")  # 1-char names: 400 levels stays under macOS PATH_MAX (1024)
        os.makedirs(p, exist_ok=True)
        for j in range(files_per_level):
            write_file(os.path.join(p, f"f{j}.txt"), rng.randrange(0, 2048), rng)


def wide_dir(root, rng, n):
    d = os.path.join(root, "wide")
    os.makedirs(d, exist_ok=True)
    for i in range(n):
        write_file(os.path.join(d, f"w{i:06d}"), rng.randrange(0, 512), rng)


def large_files(root, rng, count, size):
    d = os.path.join(root, "large")
    os.makedirs(d, exist_ok=True)
    for i in range(count):
        write_file(os.path.join(d, f"big{i}.bin"), size, rng)


def sparse_files(root, rng, count, logical):
    d = os.path.join(root, "sparse")
    os.makedirs(d, exist_ok=True)
    for i in range(count):
        p = os.path.join(d, f"sparse{i}.img")
        with open(p, "wb") as f:
            f.write(CHUNK[:4096])
            f.truncate(logical)  # hole after first 4 KiB (Windows: not sparse unless flagged)
        if IS_WIN:
            subprocess.run(["fsutil", "sparse", "setflag", p], capture_output=True)


def hard_links(root, rng, count, links_each):
    d = os.path.join(root, "hardlinks")
    os.makedirs(d, exist_ok=True)
    for i in range(count):
        src = os.path.join(d, f"orig{i:04d}.bin")
        write_file(src, 64 * 1024, rng)
        for k in range(links_each):
            os.link(src, os.path.join(d, f"link{i:04d}_{k}.bin"))


def symlinks(root, rng, count):
    if IS_WIN:
        return  # symlinks need Developer Mode/admin on Windows; skipped (documented)
    d = os.path.join(root, "symlinks")
    os.makedirs(os.path.join(d, "target"), exist_ok=True)
    write_file(os.path.join(d, "target", "payload.bin"), 1 << 20, rng)
    for i in range(count):
        os.symlink("target/payload.bin", os.path.join(d, f"s{i:04d}"))
    os.symlink("..", os.path.join(d, "loop_parent"))        # directory loop
    os.symlink("self", os.path.join(d, "self"))             # self loop
    os.symlink("does-not-exist", os.path.join(d, "dangling"))
    os.symlink("target", os.path.join(d, "dir_link"))


def apfs_clones(root, rng, count):
    if not IS_MAC:
        return
    d = os.path.join(root, "clones")
    os.makedirs(d, exist_ok=True)
    src = os.path.join(d, "clone_src.bin")
    write_file(src, 8 << 20, rng)
    for i in range(count):
        subprocess.run(["cp", "-c", src, os.path.join(d, f"clone{i:03d}.bin")], check=True)


def scaled(x, s):
    return max(1, int(x * s))


def generate(out, profile, seed, scale):
    rng = random.Random(f"{seed}:{profile}")
    os.makedirs(out, exist_ok=True)
    s = scale
    if profile == "small":        # PR smoke test: every feature, tiny
        tiny_files(os.path.join(out, "tiny"), rng, scaled(2000, s))
        deep_tree(os.path.join(out, "deep"), rng, 50)
        wide_dir(out, rng, scaled(1000, s))
        large_files(out, rng, 2, 8 << 20)
        sparse_files(out, rng, 2, 64 << 20)
        hard_links(out, rng, 20, 2)
        symlinks(out, rng, 10)
        apfs_clones(out, rng, 4)
    elif profile == "tiny":
        tiny_files(out, rng, scaled(150_000, s))
    elif profile == "deep":
        deep_tree(out, rng, 400 if not IS_WIN else 100)
    elif profile == "wide":
        wide_dir(out, rng, scaled(50_000, s))
    elif profile == "mixed":      # large + sparse + links + clones
        large_files(out, rng, 4, scaled(256 << 20, s))
        sparse_files(out, rng, 8, 1 << 30)
        hard_links(out, rng, scaled(2000, s), 3)
        symlinks(out, rng, 200)
        apfs_clones(out, rng, 64)
        tiny_files(os.path.join(out, "misc"), rng, scaled(5000, s))
    else:
        raise SystemExit(f"unknown profile {profile}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--scale", type=float, default=1.0)
    a = ap.parse_args()
    generate(a.out, a.profile, a.seed, a.scale)
