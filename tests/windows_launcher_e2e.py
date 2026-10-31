"""End-to-end check of the real Windows entry point, run on a GitHub-hosted Windows runner.

Drives agent/update-and-start.cmd exactly as the owner does (double-click == cmd /c):
the pinned launcher is downloaded from GitHub and hash-checked, the release named by
main's agent/release.json is installed and startup-checked, and Streamlit serves the
dashboard on port 8501. Then: restart, second-instance lock, and --rollback.

This proves the mechanism on Windows. It is not the owner's PC: the owner's Python,
Streamlit version, Ollama and real data are still to be checked by hand.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
HEALTH = 'http://127.0.0.1:8501/_stcore/health'


def log(*parts):
    print('[e2e]', *parts, flush=True)


def healthy():
    try:
        with urllib.request.urlopen(HEALTH, timeout=3) as response:
            return response.status == 200
    except OSError:
        return False


def start(folder, *args):
    out = open(folder / 'console.log', 'a', encoding='utf-8', errors='replace')
    return subprocess.Popen(['cmd', '/c', 'update-and-start.cmd', *args], cwd=folder, stdin=subprocess.DEVNULL,
                            stdout=out, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)


def wait_healthy(process, folder, seconds=420):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if healthy():
            return
        if process.poll() is not None:
            break
        time.sleep(2)
    raise AssertionError('dashboard did not come up:\n' + (folder / 'console.log').read_text(encoding='utf-8', errors='replace')[-4000:])


def stop(process):
    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
    process.wait(timeout=60)
    deadline = time.time() + 60
    while healthy() and time.time() < deadline:
        time.sleep(1)
    assert not healthy(), 'port 8501 still answering after stop'


def console(folder):
    return (folder / 'console.log').read_text(encoding='utf-8', errors='replace')


def main():
    assert os.name == 'nt', 'run on Windows'
    folder = Path(tempfile.mkdtemp(prefix='AI事業開発-'))
    shutil.copy2(ROOT / 'agent' / 'update-and-start.cmd', folder / 'update-and-start.cmd')
    # An "older" app at the legacy location, so the first update has something to keep as previous.py.
    old = (ROOT / 'agent' / 'venture_agent_integrated.py').read_text(encoding='utf-8')
    (folder / 'venture_agent_integrated.py').write_text(old.replace("APP_VERSION='", "APP_VERSION='e2e-old-", 1), encoding='utf-8')

    log('1. first start: download pinned launcher, install release, startup check, serve')
    first = start(folder)
    wait_healthy(first, folder)
    text = console(folder)
    assert 'Update installed' in text, text[-3000:]
    assert 'Startup check passed' in text, text[-3000:]
    current = (folder / 'code' / 'current.py').read_text(encoding='utf-8')
    assert 'e2e-old-' not in current
    assert (folder / 'code' / 'previous.py').exists() and list((folder / 'backups').iterdir())
    log('   ok:', [line for line in current.splitlines() if line.startswith('APP_VERSION')][0])

    log('2. second instance while running is refused by the lock')
    second = subprocess.run(['cmd', '/c', 'update-and-start.cmd'], cwd=folder, stdin=subprocess.DEVNULL,
                            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180)
    assert 'Already running' in second.stdout + second.stderr, second.stdout + second.stderr
    stop(first)

    log('3. restart after stop: no reinstall, dashboard serves again')
    again = start(folder)
    wait_healthy(again, folder)
    assert console(folder).count('Already up to date') >= 1, console(folder)[-3000:]
    assert console(folder).count('Update installed') == 1, 'restart must not reinstall'
    stop(again)

    log('4. --rollback restores the previous code and still starts')
    back = start(folder, '--rollback')
    wait_healthy(back, folder)
    assert 'Previous code restored' in console(folder)
    assert 'e2e-old-' in (folder / 'code' / 'current.py').read_text(encoding='utf-8')
    stop(back)
    log('PASS: Windows cmd entry, pinned launcher, update+startup check, lock, restart, rollback')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('[e2e] FAILED', file=sys.stderr)
        raise
