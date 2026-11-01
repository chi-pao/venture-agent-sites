"""Copy a static site (same origin only) by following what its pages and scripts actually load.

Used to move the お買い得物件チェッカー from ChatGPT Sites to this repository. Starts from the page,
follows <script>/<link>/<img> references, ES-module imports, new URL()/fetch()/Worker() targets
and file names listed in JSON (e.g. models/catalog.json), stays on the same host, and writes
the files plus MIRROR_REPORT.md (every file with its size and sha256, and what was skipped).

  python tools/mirror_site.py https://example.site/ checker-site
"""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

MAX_FILE = 40_000_000
MAX_TOTAL = 300_000_000
TEXT_TYPES = ('.html', '.htm', '.js', '.mjs', '.css', '.json', '.webmanifest', '.txt', '.svg')
REF_IN_HTML = re.compile(r'''(?:src|href)\s*=\s*["']([^"'#]+)["']''', re.I)
REF_IN_JS = re.compile(r'''(?:from\s*|import\s*\(\s*|fetch\s*\(\s*|new\s+URL\s*\(\s*|new\s+Worker\s*\(\s*(?:new\s+URL\s*\(\s*)?)["'`]([^"'`]+)["'`]''')
FILE_LIKE = re.compile(r'''["'`]((?:\./|\.\./|/)?[A-Za-z0-9_\-./]+\.(?:mjs|js|json|wasm|bin|onnx|gz|traineddata|webmanifest|css|png|svg|ico|webp|csv))(?:\?[^"'`]*)?["'`]''')
CSS_URL = re.compile(r'''url\(\s*["']?([^"')]+)["']?\s*\)''')
SKIP_PREFIX = ('/_sites/', '/cdn-cgi/')  # hosting-platform assets, not part of the app
SANE_REF = re.compile(r'^[A-Za-z0-9_./~:%?=&+-]+$')


def refs(path, body):
    text = body.decode('utf-8', 'replace')
    found = set()
    if path.endswith(('.html', '.htm', '/')):
        found |= set(REF_IN_HTML.findall(text))
        for script in re.findall(r'<script[^>]*>(.*?)</script>', text, re.S | re.I):
            found |= set(REF_IN_JS.findall(script)) | set(FILE_LIKE.findall(script))
    elif path.endswith(('.js', '.mjs')):
        found |= set(REF_IN_JS.findall(text)) | set(FILE_LIKE.findall(text))
    elif path.endswith('.css'):
        found |= set(CSS_URL.findall(text))
    elif path.endswith(('.json', '.webmanifest')):
        try:
            data = json.loads(text)
        except ValueError:
            data = None

        def walk(value):
            if isinstance(value, dict):
                for v in value.values():
                    walk(v)
            elif isinstance(value, list):
                for v in value:
                    walk(v)
            elif isinstance(value, str) and FILE_LIKE.fullmatch('"' + value + '"'):
                found.add(value)
        walk(data)
    return found


def mirror(base, out, extra=()):
    base = base if base.endswith('/') else base + '/'
    host = urllib.parse.urlsplit(base).netloc
    out = Path(out)
    queue = [(base, True)] + [(urllib.parse.urljoin(base, e), True) for e in extra]
    seen, saved, skipped, total, json_refs = set(), [], [], 0, []
    while queue:
        url, required = queue.pop(0)
        url = urllib.parse.urldefrag(url)[0]
        parts = urllib.parse.urlsplit(url)
        if parts.netloc != host or url in seen or parts.path.startswith(SKIP_PREFIX):
            if parts.netloc and parts.netloc != host and url not in seen:
                skipped.append((url, 'other host (kept as a link)'))
            seen.add(url)
            continue
        seen.add(url)
        rel = parts.path.lstrip('/') or 'index.html'
        if rel.endswith('/'):
            rel += 'index.html'
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'site-mirror (owner migration)'})
            with urllib.request.urlopen(req, timeout=60) as response:
                body = response.read(MAX_FILE + 1)
                ctype = response.headers.get_content_type()
        except urllib.error.HTTPError as exc:
            if required or exc.code != 404:
                skipped.append((url, 'HTTP ' + str(exc.code)))
            continue
        except Exception as exc:  # network errors are reported, not hidden
            skipped.append((url, type(exc).__name__))
            continue
        # Single-page hosts answer unknown paths with an HTML page and status 200.
        looks_html = ctype == 'text/html' or body[:200].lstrip().lower().startswith((b'<!doctype html', b'<html'))
        if looks_html and not rel.endswith(('.html', '.htm')):
            if required:
                skipped.append((url, 'not found (host returned an HTML page instead)'))
            continue
        if any(r == rel for r, _, _ in saved):
            continue  # same file requested with a different ?version query
        if len(body) > MAX_FILE or total + len(body) > MAX_TOTAL:
            skipped.append((url, 'too large'))
            continue
        target = out / PurePosixPath(rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        total += len(body)
        saved.append((rel, len(body), hashlib.sha256(body).hexdigest()))
        if rel.endswith(TEXT_TYPES) or rel == 'index.html':
            for ref in refs(rel if rel != 'index.html' else '/', body):
                if ref.startswith(('data:', 'blob:', 'mailto:', 'javascript:')) or not SANE_REF.match(ref.replace('&amp;', '&')):
                    continue
                if rel.endswith(('.json', '.webmanifest')) and not ref.startswith(('/', 'http')):
                    # A path listed in JSON may be relative to the JSON file or to the site root:
                    # try both, and report it only if neither exists.
                    pair = (urllib.parse.urljoin(url, ref), urllib.parse.urljoin(base, ref))
                    json_refs.append(pair)
                    queue += [(pair[0], False), (pair[1], False)]
                else:
                    queue.append((urllib.parse.urljoin(url, ref), True))
    have = {urllib.parse.urljoin(base, r) for r, _, _ in saved}
    for a, b in json_refs:
        if a.split('?')[0] not in have and b.split('?')[0] not in have:
            skipped.append((b, 'listed in JSON but not found (also tried ' + a + ')'))
    lines = ['# Mirror report', '', 'Source: ' + base, '', '| file | bytes | sha256 |', '|---|---|---|']
    lines += [f'| {r} | {n} | {h} |' for r, n, h in sorted(saved)]
    lines += ['', '## Not copied', ''] + [f'- {u} — {why}' for u, why in sorted(set(skipped))]
    (out / 'MIRROR_REPORT.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return saved, skipped


if __name__ == '__main__':
    saved, skipped = mirror(sys.argv[1], sys.argv[2], sys.argv[3:])
    print(f'saved {len(saved)} files, skipped {len(skipped)}')
    for url, why in skipped:
        print('skip', url, why)
