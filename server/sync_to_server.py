#!/usr/bin/env python3
"""
Upload gitignored secrets/config to VPS over SFTP.

Uploads (skips .venv, __pycache__, logs/, tools/out/, etc.):
  trader/config.py, clients/api_keys*.py, withdrawal_addresses.py,
  env/, trader_config.ref.txt

Environment variables (set in Windows system vars or current session):
  SERVER_PASSWORD     — required
  SERVER_HOST / SPREAD_HUNTER_SERVER — optional, default 45.76.202.248
  SERVER_USER         — optional, default root
  SERVER_REMOTE       — optional, default /root/spread_hunter_python
  SERVER_PORT         — optional, default 22

Run from repo root:
  python server/sync_to_server.py
  python server/sync_to_server.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _is_noise(rel_s: str) -> bool:
    s = rel_s.replace("\\", "/")
    prefixes = (
        ".venv/", "venv/", "ENV/", ".claude/", ".idea/", ".vscode/",
        "logs/", "tools/out/", "reference/", "secrets/",
        "dist/", "build/", ".eggs/",
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


def iter_ignored_files() -> list[str]:
    out: list[str] = []
    for p in REPO_ROOT.rglob("*"):
        if ".git" in p.parts or not p.is_file():
            continue
        rel_s = str(p.relative_to(REPO_ROOT)).replace("\\", "/")
        r = subprocess.run(["git", "check-ignore", "-q", rel_s], cwd=REPO_ROOT)
        if r.returncode != 0:
            continue
        if _is_noise(rel_s):
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
    sftp_makedirs(sftp, dest.rsplit("/", 1)[0])
    sftp.put(str(local), dest)


def chmod_secrets(ssh, remote_base: str, rel_paths: list[str]) -> None:
    targets = []
    for p in rel_paths:
        n = p.replace("\\", "/")
        if n in ("trader/config.py", "trader_config.ref.txt"):
            targets.append(f"{remote_base}/{n}")
        elif n.endswith(".py") and ("api_keys" in n or "withdrawal_addresses" in n):
            targets.append(f"{remote_base}/{n}")
    if targets:
        _, out, _ = ssh.exec_command("chmod 600 " + " ".join(targets))
        out.channel.recv_exit_status()

    env_dir = f"{remote_base}/env"
    cmd = (
        f"chmod 700 {env_dir} 2>/dev/null || true; "
        f"test -f {env_dir}/.env && chmod 600 {env_dir}/.env || true"
    )
    _, out, _ = ssh.exec_command(cmd)
    out.channel.recv_exit_status()


def connect():
    try:
        import paramiko
    except ImportError:
        sys.stderr.write("Missing paramiko. Run: pip install -r server/requirements.txt\n")
        raise SystemExit(1)

    password = os.environ.get("SERVER_PASSWORD")
    if not password:
        sys.stderr.write("Set SERVER_PASSWORD environment variable.\n")
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
    client.connect(hostname=host, port=port, username=user, password=password,
                   allow_agent=False, look_for_keys=False, timeout=30)
    return client, remote


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload gitignored secrets/config to VPS.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print files to upload without connecting.")
    args = parser.parse_args()

    rels = iter_ignored_files()
    paths = [REPO_ROOT / r for r in rels if (REPO_ROOT / r).is_file()]

    if not paths:
        print("No ignored files found to upload.")
        return

    print(f"Files to upload ({len(paths)}):")
    for p in paths:
        print(f"  {p.relative_to(REPO_ROOT)}")

    if args.dry_run:
        return

    client, remote_base = connect()
    try:
        sftp = client.open_sftp()
        try:
            for p in paths:
                print(f"UP  {p.relative_to(REPO_ROOT)}")
                upload_one(sftp, p, remote_base)
        finally:
            sftp.close()
        chmod_secrets(client, remote_base, rels)
    finally:
        client.close()
    print("Done.")


if __name__ == "__main__":
    main()
