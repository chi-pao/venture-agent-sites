"""Windows launcher: separate managed code from existing local business data."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request

MANIFEST = 'https://raw.githubusercontent.com/chi-pao/venture-agent-sites/main/agent/release.json'
MAX_SOURCE = 4_000_000


def download(url, limit):
    if not url.startswith('https://raw.githubusercontent.com/chi-pao/venture-agent-sites/'):
        raise ValueError('Unexpected update location')
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'venture-agent-updater'}), timeout=20) as response:
        content = response.read(limit + 1)
    if len(content) > limit:
        raise ValueError('Update exceeds size limit')
    return content


def verify_source(content, expected_hash):
    if hashlib.sha256(content).hexdigest() != expected_hash:
        raise ValueError('Update checksum mismatch')
    compile(content, 'venture_agent_integrated.py', 'exec')


def backup_database(data_home, destination):
    source = data_home / 'venture_agent_integrated.db'
    if source.exists():
        # SQLite backup includes committed WAL changes; never copy a live DB file directly.
        with sqlite3.connect(str(source), timeout=30) as src, sqlite3.connect(str(destination / source.name)) as dst:
            src.backup(dst)


def install_update(data_home, code_home, fetch=download):
    current = code_home / 'current.py'
    manifest = json.loads(fetch(MANIFEST, 20_000))
    digest = manifest['sha256']
    if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('Invalid update checksum')
    if current.exists() and hashlib.sha256(current.read_bytes()).hexdigest() == digest:
        return 'Already up to date'
    content = fetch(manifest['source_url'], MAX_SOURCE)
    verify_source(content, digest)
    stage = code_home / 'candidate.py'
    stage.write_bytes(content)
    backup = data_home / 'backups' / (time.strftime('%Y%m%d-%H%M%S') + '-' + str(time.time_ns()))
    backup.mkdir(parents=True)
    backup_database(data_home, backup)
    previous_source = current if current.exists() else data_home / 'venture_agent_integrated.py'
    if previous_source.exists():
        shutil.copy2(previous_source, backup / 'previous.py')
        previous_stage = code_home / 'previous.tmp'
        shutil.copy2(previous_source, previous_stage)
        os.replace(previous_stage, code_home / 'previous.py')
    os.replace(stage, current)
    (code_home / 'installed.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return 'Update installed; backup: ' + str(backup)


def rollback(code_home):
    previous = code_home / 'previous.py'
    if not previous.exists():
        raise ValueError('No previous managed version is available')
    content = previous.read_bytes()
    compile(content, 'previous.py', 'exec')
    stage = code_home / 'rollback.tmp'
    stage.write_bytes(content)
    os.replace(stage, code_home / 'current.py')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-home', required=True)
    parser.add_argument('--rollback', action='store_true')
    args = parser.parse_args()
    data_home = Path(args.data_home).expanduser().resolve()
    data_home.mkdir(parents=True, exist_ok=True)
    code_home = data_home / 'code'
    code_home.mkdir(exist_ok=True)
    # Hold the OS lock for the entire Streamlit session. A crash releases it automatically.
    lock = (code_home / 'launcher.lock').open('a+b')
    lock.seek(0); lock.write(b'0'); lock.flush(); lock.seek(0)
    if os.name == 'nt':
        import msvcrt
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            print('Already running. Close the previous black window before updating.')
            return 1
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', 8501)) == 0:
            print('Port 8501 is in use. Stop the existing app with Ctrl+C, then retry.')
            return 1
    try:
        if args.rollback:
            rollback(code_home)
            print('Previous code restored. Data was not overwritten.')
        else:
            print(install_update(data_home, code_home))
    except Exception as exc:
        print('Update not applied:', str(exc))
        if not (code_home / 'current.py').exists():
            print('Initial setup failed. Existing files have not been changed.')
            return 1
        print('Starting the previously installed version.')
    env = os.environ.copy()
    env['VENTURE_DATA_HOME'] = str(data_home)
    env['PYTHONUTF8'] = '1'
    try:
        return subprocess.call([sys.executable, '-m', 'streamlit', 'run', str(code_home / 'current.py'), '--server.port', '8501'], cwd=str(data_home), env=env)
    except KeyboardInterrupt:
        return 0
    finally:
        lock.close()


if __name__ == '__main__':
    raise SystemExit(main())
