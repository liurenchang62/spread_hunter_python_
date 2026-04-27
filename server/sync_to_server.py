#!/usr/bin/env python3
"""
Push local workspace files to the VPS over SFTP without using GitHub.

Modes:
  all     — tracked changes vs HEAD + untracked non-ignored files; deletes on
            remote match git deletions vs HEAD (ignored paths excluded).
  ignored — gitignored files that look like secrets/config (skips .venv,
            __pycache__, logs/, etc.); use --full-ignored for literally all.

Password: set SERVER_PASSWORD. Optional: SERVER_HOST (or SPREAD_HUNTER_SERVER),
SERVER_USER (default root), SERVER_REMOTE (default /root/spread_hunter_python),
SERVER_PORT (default 22).

Install: pip install -r server/requirements.txt
Run from repo root: python server/sync_to_server.py --mode all
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_git(args: list[str]) -> str:
    p = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if p.returncode != 0:
        sys.stderr.write(p.stderr or p.stdout or "git failed\n")
        raise SystemExit(p.returncode)
    return p.stdout


def _rel_norm(line: str) -> str | None:
    line = line.strip().replace("\\", "/")
    if not line or line.startswith(".git/"):
        return None
    return line


def git_paths_all_mode() -> tuple[set[str], set[str]]:
    upload: set[str] = set()
    for block in (
        _run_git(["diff", "--name-only", "HEAD"]),
        _run_git(["ls-files", "--others", "--exclude-standard"]),
    ):
        for line in block.splitlines():
            n = _rel_norm(line)
            if n:
                upload.add(n)

    deleted: set[str] = set()
    for line in _run_git(["diff", "--name-only", "--diff-filter=D", "HEAD"]).splitlines():
        n = _rel_norm(line)
        if n:
            deleted.add(n)

    def is_ignored(rel: str) -> bool:
        r = subprocess.run(
            ["git", "check-ignore", "-q", rel],
            cwd=REPO_ROOT,
        )
        return r.returncode == 0

    upload = {p for p in upload if not is_ignored(p)}
    deleted = {p for p in deleted if not is_ignored(p)}
    upload -= deleted
    return upload, deleted


def _is_noise_ignored_path(rel_s: str) -> bool:
    """Venv, caches, IDE, runtime logs — ignored by git but not 'secrets' sync."""
    s = rel_s.replace("\\", "/")
    prefixes = (
        ".venv/",
        "venv/",
        "ENV/",
        ".claude/",
        ".idea/",
        ".vscode/",
        "logs/",
        "tools/out/",
        "reference/",
        "secrets/",
        "dist/",
        "build/",
        ".eggs/",
    )
    if any(s.startswith(p) for p in prefixes):
        return True
    parts = s.split("/")
    if "__pycache__" in parts:
        return True
    if any(p.endswith(".egg-info") for p in parts):
        return True
    if s.endswith((".pyc", ".pyo", ".pyd")):
        return True
    return False


def iter_ignored_rel_paths(*, full: bool) -> list[str]:
    out: list[str] = []
    for p in REPO_ROOT.rglob("*"):
        if ".git" in p.parts:
            continue
        if not p.is_file():
            continue
        rel = p.relative_to(REPO_ROOT)
        rel_s = str(rel).replace("\\", "/")
        r = subprocess.run(
            ["git", "check-ignore", "-q", rel_s],
            cwd=REPO_ROOT,
        )
        if r.returncode != 0:
            continue
        if not full and _is_noise_ignored_path(rel_s):
            continue
        out.append(rel_s)
    return sorted(out)


def sftp_makedirs(sftp, remote_dir: str) -> None:
    parts = [x for x in remote_dir.split("/") if x]
    cur = ""
    for part in parts:
        cur = f"{cur}/{part}"
        try:
            sftp.stat(cur)
        except OSError:
            sftp.mkdir(cur)


def upload_one(sftp, local: Path, remote_base: str) -> None:
    rel_s = str(local.relative_to(REPO_ROOT)).replace("\\", "/")
    dest = f"{remote_base}/{rel_s}"
    parent = dest.rsplit("/", 1)[0]
    sftp_makedirs(sftp, parent)
    sftp.put(str(local), dest)


def remove_one(sftp, remote_base: str, rel_s: str) -> None:
    dest = f"{remote_base}/{rel_s}"
    try:
        sftp.remove(dest)
    except OSError:
        pass


def chmod_after_ignored(ssh, remote_base: str, rel_paths: list[str]) -> None:
    py_sec = []
    for p in rel_paths:
        n = p.replace("\\", "/")
        if n == "trader/config.py" or n == "trader_config.ref.txt":
            py_sec.append(f"{remote_base}/{n}")
        elif p.endswith(".py") and (
            "api_keys" in p or "withdrawal_addresses" in p
        ):
            py_sec.append(f"{remote_base}/{n}")
    if py_sec:
        cmd = "chmod 600 " + " ".join(py_sec)
        _, stdout, stderr = ssh.exec_command(cmd)
        stdout.channel.recv_exit_status()
        err = stderr.read().decode()
        if err:
            sys.stderr.write(err)

    env_dir = f"{remote_base}/env"
    cmd = (
        f"chmod 700 {env_dir} 2>/dev/null || true; "
        f"test -f {env_dir}/.env && chmod 600 {env_dir}/.env || true"
    )
    _, stdout, stderr = ssh.exec_command(cmd)
    stdout.channel.recv_exit_status()


def connect():
    try:
        import paramiko
    except ImportError:
        sys.stderr.write(
            "Missing paramiko. Install: pip install -r server/requirements.txt\n"
        )
        raise SystemExit(1)

    password = os.environ.get("SERVER_PASSWORD")
    if not password:
        sys.stderr.write("Set SERVER_PASSWORD in the environment.\n")
        raise SystemExit(1)

    host = (
        os.environ.get("SERVER_HOST")
        or os.environ.get("SPREAD_HUNTER_SERVER")
        or "45.76.202.248"
    )
    user = os.environ.get("SERVER_USER", "root")
    remote = os.environ.get("SERVER_REMOTE", "/root/spread_hunter_python").rstrip("/")
    port = int(os.environ.get("SERVER_PORT", "22"))

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=host,
        port=port,
        username=user,
        password=password,
        allow_agent=False,
        look_for_keys=False,
        timeout=30,
    )
    return client, remote


def main() -> None:
    parser = argparse.ArgumentParser(description="SFTP sync to server (no GitHub).")
    parser.add_argument(
        "--mode",
        choices=("all", "ignored"),
        required=True,
        help="all: non-ignored git changes; ignored: only gitignored files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions only; do not connect.",
    )
    parser.add_argument(
        "--full-ignored",
        action="store_true",
        help="With --mode ignored: upload every ignored file (includes .venv, "
        "logs, __pycache__). Default skips those so only secrets/config match "
        "typical deploy needs.",
    )
    args = parser.parse_args()

    if args.mode == "all":
        upload_rels, delete_rels = git_paths_all_mode()
        to_upload = sorted(REPO_ROOT / p for p in upload_rels)
        to_upload = [p for p in to_upload if p.is_file()]
        missing = [p for p in upload_rels if not (REPO_ROOT / p).is_file()]
        if missing:
            for m in sorted(missing):
                print(f"SKIP (not a file): {m}")
        print(f"Upload {len(to_upload)} file(s), delete {len(delete_rels)} on remote.")
        if args.dry_run:
            for p in to_upload:
                print(f"UP {p.relative_to(REPO_ROOT)}")
            for d in sorted(delete_rels):
                print(f"RM {d}")
            return

        client, remote_base = connect()
        try:
            sftp = client.open_sftp()
            try:
                for p in to_upload:
                    print(f"UP {p.relative_to(REPO_ROOT)}")
                    upload_one(sftp, p, remote_base)
                for d in sorted(delete_rels):
                    print(f"RM {d}")
                    remove_one(sftp, remote_base, d)
            finally:
                sftp.close()
        finally:
            client.close()
        print("Done (all).")
        return

    # ignored
    rels = iter_ignored_rel_paths(full=args.full_ignored)
    paths = [REPO_ROOT / r for r in rels if (REPO_ROOT / r).is_file()]
    print(f"Upload {len(paths)} ignored file(s).")
    if args.dry_run:
        for p in paths:
            print(f"UP {p.relative_to(REPO_ROOT)}")
        return

    client, remote_base = connect()
    try:
        sftp = client.open_sftp()
        try:
            for p in paths:
                print(f"UP {p.relative_to(REPO_ROOT)}")
                upload_one(sftp, p, remote_base)
        finally:
            sftp.close()
        chmod_after_ignored(client, remote_base, rels)
    finally:
        client.close()
    print("Done (ignored).")


if __name__ == "__main__":
    main()
