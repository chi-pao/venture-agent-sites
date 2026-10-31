"""Windows launcher: separate managed code from existing local business data."""
import argparse
from contextlib import closing
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
SMOKE_TIMEOUT = 240
EARLY_EXIT_SECONDS = 60
# Render the dashboard once, headless, the way a browser session would. Exit 3 = cannot verify here.
SMOKE_SCRIPT = (
    'import sys\n'
    'try:\n from streamlit.testing.v1 import AppTest\n'
    'except Exception as exc:\n print("smoke-unverified:", type(exc).__name__); sys.exit(3)\n'
    'at = AppTest.from_file(sys.argv[1], default_timeout=int(sys.argv[2])).run()\n'
    'errors = [str(getattr(e, "message", e))[:300] for e in at.exception]\n'
    'print("smoke-errors:" if errors else "smoke-ok", errors if errors else "")\n'
    'sys.exit(1 if errors else 0)\n'
)


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
        # closing(): sqlite3's own context manager commits but never closes the file handle.
        with closing(sqlite3.connect(str(source), timeout=30)) as src, closing(sqlite3.connect(str(destination / source.name))) as dst:
            src.backup(dst)


def failed_updates(code_home):
    try:
        data = json.loads((code_home / 'failed_updates.json').read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def install_update(data_home, code_home, fetch=download):
    current = code_home / 'current.py'
    manifest = json.loads(fetch(MANIFEST, 20_000))
    digest = manifest['sha256']
    if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('Invalid update checksum')
    if current.exists() and hashlib.sha256(current.read_bytes()).hexdigest() == digest:
        return 'Already up to date'
    if digest in failed_updates(code_home):
        # This exact build already failed its startup check here and was rolled back.
        return 'Update ' + str(manifest.get('version', '')) + ' skipped: it failed the startup check earlier'
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
    # Mark the new code as unproven until it passes the startup check.
    (code_home / 'pending_check.json').write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
    return 'Update installed; backup: ' + str(backup)


def smoke_check(data_home, code_home, timeout=SMOKE_TIMEOUT):
    """Render the installed dashboard against a throwaway copy of the DB.

    Returns ('ok'|'failed'|'unverified', detail). Secrets (VENTURE_* variables) are
    not passed, so the check cannot publish, post or upload anything.
    """
    import tempfile
    with tempfile.TemporaryDirectory(prefix='venture-smoke-') as tmp:
        sandbox = Path(tmp)
        source = data_home / 'venture_agent_integrated.db'
        if source.exists():
            with closing(sqlite3.connect(str(source), timeout=30)) as src, closing(sqlite3.connect(str(sandbox / source.name))) as dst:
                src.backup(dst)
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith('VENTURE_')}
        env.update(VENTURE_DATA_HOME=str(sandbox), PYTHONUTF8='1')
        try:
            result = subprocess.run([sys.executable, '-c', SMOKE_SCRIPT, str(code_home / 'current.py'), str(max(30, timeout - 30))],
                                    cwd=str(sandbox), env=env, capture_output=True, text=True,
                                    encoding='utf-8', errors='replace', timeout=timeout)
        except subprocess.TimeoutExpired:
            return 'unverified', 'startup check timed out after ' + str(timeout) + 's'
    detail = ((result.stdout or '') + (result.stderr or '')).strip()[-800:]
    if result.returncode == 0:
        return 'ok', detail
    if result.returncode == 3:
        return 'unverified', detail
    return 'failed', detail or ('exit code ' + str(result.returncode))


def recover_failed_update(code_home, reason):
    """Put the previous managed code back and remember the failed build so it is not reinstalled."""
    current = code_home / 'current.py'
    digest = hashlib.sha256(current.read_bytes()).hexdigest() if current.exists() else ''
    manifest = {}
    for name in ('pending_check.json', 'installed.json'):
        try:
            manifest = json.loads((code_home / name).read_text(encoding='utf-8'))
            break
        except (OSError, ValueError):
            continue
    rollback(code_home)
    failed = failed_updates(code_home)
    if digest:
        failed[digest] = {'version': manifest.get('version', ''), 'reason': str(reason)[:800],
                          'recovered_at': time.strftime('%Y-%m-%d %H:%M:%S')}
        (code_home / 'failed_updates.json').write_text(json.dumps(failed, ensure_ascii=False, indent=2), encoding='utf-8')
    (code_home / 'pending_check.json').unlink(missing_ok=True)
    return 'Rolled back to the previous version (' + str(manifest.get('version', 'unknown')) + ' failed: ' + str(reason)[:200] + ')'


def verify_pending_update(data_home, code_home, check=smoke_check):
    """Run after install. Returns a message; rolls back automatically when the new code fails."""
    pending = code_home / 'pending_check.json'
    if not pending.exists():
        return ''
    status, detail = check(data_home, code_home)
    if status == 'ok':
        pending.unlink(missing_ok=True)
        return 'Startup check passed'
    if status == 'unverified':
        pending.unlink(missing_ok=True)
        return 'Startup check could not run (' + detail[-200:] + '); starting the new version unverified'
    if not (code_home / 'previous.py').exists():
        pending.unlink(missing_ok=True)
        return 'Startup check failed and no previous version exists; starting anyway: ' + detail[-300:]
    return recover_failed_update(code_home, 'startup check: ' + detail)


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
    fresh = (code_home / 'pending_check.json').exists()
    if fresh:
        print('Checking that the new version starts...')
        message = verify_pending_update(data_home, code_home)
        print(message)
        fresh = not message.startswith('Rolled back')
    env = os.environ.copy()
    env['VENTURE_DATA_HOME'] = str(data_home)
    env['PYTHONUTF8'] = '1'
    command = [sys.executable, '-m', 'streamlit', 'run', str(code_home / 'current.py'), '--server.port', '8501']
    try:
        started = time.monotonic()
        code = subprocess.call(command, cwd=str(data_home), env=env)
        # A just-updated version that dies immediately is treated as a failed update.
        if fresh and code != 0 and time.monotonic() - started < EARLY_EXIT_SECONDS and (code_home / 'previous.py').exists():
            print(recover_failed_update(code_home, 'exited with code ' + str(code) + ' right after the update'))
            code = subprocess.call(command, cwd=str(data_home), env=env)
        return code
    except KeyboardInterrupt:
        return 0
    finally:
        lock.close()


if __name__ == '__main__':
    raise SystemExit(main())
