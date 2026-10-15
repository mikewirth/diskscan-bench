#!/usr/bin/env python3
"""Install pinned tool versions into .tools/bin (prepend it to PATH).

Release binaries are used where upstream publishes them; otherwise
`cargo install --locked` with an exact version / git rev. Versions live here and
in tools.py `pin` – bump both in one PR.
"""
import os, sys, platform, shutil, subprocess, tarfile, zipfile, urllib.request, json, hashlib, stat, tempfile
from tools import PLAT

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, ".tools", "bin")
ARCH = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x86_64"
GH = "https://github.com"

T = {  # (platform, arch) -> url ; {exe} names the binary inside the archive
 "hyperfine": {("linux","x86_64"): f"{GH}/sharkdp/hyperfine/releases/download/v2.0.0/hyperfine-v2.0.0-x86_64-unknown-linux-musl.tar.gz",
               ("macos","arm64"): f"{GH}/sharkdp/hyperfine/releases/download/v2.0.0/hyperfine-v2.0.0-aarch64-apple-darwin.tar.gz",
               ("macos","x86_64"): f"{GH}/sharkdp/hyperfine/releases/download/v2.0.0/hyperfine-v2.0.0-x86_64-apple-darwin.tar.gz",
               ("windows","x86_64"): f"{GH}/sharkdp/hyperfine/releases/download/v2.0.0/hyperfine-v2.0.0-x86_64-pc-windows-msvc.zip"},
 "diskus": {("linux","x86_64"): f"{GH}/sharkdp/diskus/releases/download/v0.9.0/diskus-v0.9.0-x86_64-unknown-linux-musl.tar.gz",
            ("macos","arm64"): f"{GH}/sharkdp/diskus/releases/download/v0.9.0/diskus-v0.9.0-aarch64-apple-darwin.tar.gz",
            ("macos","x86_64"): f"{GH}/sharkdp/diskus/releases/download/v0.9.0/diskus-v0.9.0-x86_64-apple-darwin.tar.gz",
            ("windows","x86_64"): f"{GH}/sharkdp/diskus/releases/download/v0.9.0/diskus-v0.9.0-x86_64-pc-windows-msvc.zip"},
 "dust": {("linux","x86_64"): f"{GH}/bootandy/dust/releases/download/v1.2.6/dust-v1.2.6-x86_64-unknown-linux-musl.tar.gz",
          ("macos","arm64"): f"{GH}/bootandy/dust/releases/download/v1.2.6/dust-v1.2.6-aarch64-apple-darwin.tar.gz",
          ("macos","x86_64"): f"{GH}/bootandy/dust/releases/download/v1.2.6/dust-v1.2.6-x86_64-apple-darwin.tar.gz",
          ("windows","x86_64"): f"{GH}/bootandy/dust/releases/download/v1.2.6/dust-v1.2.6-x86_64-pc-windows-msvc.zip"},
 "dua": {("linux","x86_64"): f"{GH}/Byron/dua-cli/releases/download/v2.45.1/dua-v2.45.1-x86_64-unknown-linux-musl.tar.gz",
         ("macos","arm64"): f"{GH}/Byron/dua-cli/releases/download/v2.45.1/dua-v2.45.1-aarch64-apple-darwin.tar.gz",
         ("macos","x86_64"): f"{GH}/Byron/dua-cli/releases/download/v2.45.1/dua-v2.45.1-x86_64-apple-darwin.tar.gz",
         ("windows","x86_64"): f"{GH}/Byron/dua-cli/releases/download/v2.45.1/dua-v2.45.1-x86_64-pc-windows-msvc.zip"},
 "gdu": {("linux","x86_64"): (f"{GH}/dundee/gdu/releases/download/v5.38.0/gdu_linux_amd64_static.tgz", "gdu_linux_amd64_static"),
         ("macos","arm64"): (f"{GH}/dundee/gdu/releases/download/v5.38.0/gdu_darwin_arm64.tgz", "gdu_darwin_arm64"),
         ("macos","x86_64"): (f"{GH}/dundee/gdu/releases/download/v5.38.0/gdu_darwin_amd64.tgz", "gdu_darwin_amd64"),
         ("windows","x86_64"): (f"{GH}/dundee/gdu/releases/download/v5.38.0/gdu_windows_amd64.exe.zip", "gdu_windows_amd64.exe")},
 "pdu": {("linux","x86_64"): f"{GH}/KSXGitHub/parallel-disk-usage/releases/download/0.24.0/pdu-x86_64-unknown-linux-musl",
         ("macos","x86_64"): f"{GH}/KSXGitHub/parallel-disk-usage/releases/download/0.24.0/pdu-x86_64-apple-darwin",
         ("macos","arm64"): ("cargo", ["parallel-disk-usage", "--version", "0.24.0", "--bin", "pdu"]),
         ("windows","x86_64"): f"{GH}/KSXGitHub/parallel-disk-usage/releases/download/0.24.0/pdu-x86_64-pc-windows-msvc.exe"},
 "erd": {("linux","x86_64"): f"{GH}/solidiquis/erdtree/releases/download/v3.1.2/erd-v3.1.2-x86_64-unknown-linux-musl.tar.gz",
         ("macos","arm64"): f"{GH}/solidiquis/erdtree/releases/download/v3.1.2/erd-v3.1.2-aarch64-apple-darwin.tar.gz",
         ("macos","x86_64"): f"{GH}/solidiquis/erdtree/releases/download/v3.1.2/erd-v3.1.2-x86_64-apple-darwin.tar.gz",
         ("windows","x86_64"): f"{GH}/solidiquis/erdtree/releases/download/v3.1.2/erd-v3.1.2-x86_64-pc-windows-msvc.exe"},
 "ncdu": {("linux","x86_64"): ("https://dev.yorhel.nl/download/ncdu-2.9.1-linux-x86_64.tar.gz", "ncdu",
                               "0c6c84b3f763c33baa051c8327f0e736f46f33a8cc061bb951d24517a8c5d73e"),
          ("macos","arm64"): ("brew", "ncdu"), ("macos","x86_64"): ("brew", "ncdu")},
 "dumac": {("macos","arm64"): ("cargo", ["--git", "https://github.com/healeycodes/dumac", "--rev", "1ffbe3c38d1066c45cac9b4ec1e31eb74edc1076"]),
           ("macos","x86_64"): ("cargo", ["--git", "https://github.com/healeycodes/dumac", "--rev", "1ffbe3c38d1066c45cac9b4ec1e31eb74edc1076"])},
 "du64": {("windows","x86_64"): ("https://download.sysinternals.com/files/DU.zip", "du64.exe")},
 "WinDirStat": {("windows","x86_64"): (f"{GH}/windirstat/windirstat/releases/download/release/v2.9.3/WinDirStat.zip", "WinDirStat.exe")},
}

def fetch(url, sha=None):
    req = urllib.request.Request(url, headers={"User-Agent": "diskscan-bench"})
    data = urllib.request.urlopen(req, timeout=120).read()
    if sha and hashlib.sha256(data).hexdigest() != sha:
        raise SystemExit(f"sha256 mismatch for {url}")
    return data

def place(name, url, inner=None, sha=None):
    exe = name + (".exe" if PLAT == "windows" and not name.endswith(".exe") else "")
    data = fetch(url, sha)
    tmp = tempfile.mkdtemp()
    fn = os.path.join(tmp, url.rsplit("/", 1)[1])
    open(fn, "wb").write(data)
    if fn.endswith((".tar.gz", ".tgz")):
        tarfile.open(fn).extractall(tmp)
    elif fn.endswith(".zip"):
        zipfile.ZipFile(fn).extractall(tmp)
    else:
        shutil.copy(fn, os.path.join(BIN, exe)); os.chmod(os.path.join(BIN, exe), 0o755); return
    want = inner or exe
    cands = sorted(os.walk(tmp), key=lambda w: ("x64" not in w[0] and "amd64" not in w[0], "arm64" in w[0]))
    for d, _, fs in cands:
        if want in fs:
            src = d
            # GUI apps: copy the whole folder content (dlls, resources)
            if name in ("WinDirStat", "SpaceSniffer"):
                for f in fs:
                    p = os.path.join(d, f)
                    if os.path.isfile(p): shutil.copy(p, BIN)
                if want != exe: shutil.copy(os.path.join(d, want), os.path.join(BIN, exe))
            else:
                shutil.copy(os.path.join(d, want), os.path.join(BIN, exe))
            os.chmod(os.path.join(BIN, exe), 0o755)
            return
    raise SystemExit(f"{want} not found in {url}")

def install_nulldisk():
    manifest = os.environ.get("NULLDISK_CLI_MANIFEST", "https://assets.nulldisk.app/releases/cli/latest.json")
    plat = {"macos": "macos", "linux": "linux"}.get(PLAT)
    if not plat:
        return "unsupported platform"
    key = f"{plat}-{ARCH}"
    try:
        m = json.loads(fetch(manifest))
        a = m["assets"][key]
        place("nulldisk", a["url"], "nulldisk", a.get("sha256"))
        return f"installed {m.get('version')}"
    except Exception as e:  # 404 until the download is published: skip gracefully
        return f"pending ({type(e).__name__}: {e})"

def main():
    os.makedirs(BIN, exist_ok=True)
    report = {}
    for name, m in T.items():
        spec = m.get((PLAT, ARCH))
        if spec is None:
            continue
        try:
            if isinstance(spec, str):
                place(name, spec)
            elif spec[0] == "cargo":
                subprocess.run(["cargo", "install", "--locked", "--root", os.path.dirname(BIN)] + spec[1], check=True)
            elif spec[0] == "brew":
                subprocess.run(["brew", "install", spec[1]], check=True)
            else:
                place(name, *spec)
            report[name] = "ok"
        except Exception as e:
            report[name] = f"FAILED: {e}"
    report["nulldisk"] = install_nulldisk()
    json.dump(report, open(os.path.join(ROOT, ".tools", "install-report.json"), "w"), indent=1)
    print(json.dumps(report, indent=1))

if __name__ == "__main__":
    main()
