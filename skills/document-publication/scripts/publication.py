"""File-scoped document registration, rendering, and end-to-end verification."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import html
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
from urllib.parse import quote, urlsplit
from urllib.request import urlopen

from reader_presentation import BASE, page, render

DEFAULT_STATE = Path('/opt/projects/out/_reader')
MAX_SOURCE_BYTES = 8 * 1024 * 1024


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def transport_origin():
    executable = shutil.which('tailscale') or '/Applications/Tailscale.app/Contents/MacOS/Tailscale'
    try:
        process = subprocess.run([executable, 'serve', 'status', '--json'], check=True, capture_output=True, text=True, timeout=15)
        config = json.loads(process.stdout)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise ValueError('Cannot read Tailscale Serve configuration; verify that Tailscale is running') from exc
    origins = []
    for host, settings in config.get('Web', {}).items():
        if settings.get('Handlers', {}).get('/reader', {}).get('Proxy') != 'http://127.0.0.1:8767':
            continue
        port = host.rsplit(':', 1)[-1]
        if not config.get('TCP', {}).get(port, {}).get('HTTPS') or config.get('AllowFunnel', {}).get(host):
            raise ValueError('The reader route must use private Tailscale Serve with HTTPS; Funnel is unsupported.')
        origins.append('https://' + (host[:-4] if host.endswith(':443') else host))
    if len(origins) != 1:
        raise ValueError('Expected one existing private /reader route to 127.0.0.1:8767. Inspect Tailscale Serve before publishing.')
    return origins[0]


def atomic_write(path, value):
    path = Path(path)
    data = value.encode('utf-8') if isinstance(value, str) else value
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == data:
        return
    descriptor, temporary = tempfile.mkstemp(prefix='.publication-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save_json(path, value):
    atomic_write(path, json.dumps(value, indent=2, ensure_ascii=False) + '\n')


@contextmanager
def state_lock(state):
    state = Path(state)
    state.mkdir(parents=True, exist_ok=True)
    with (state / '.publication.lock').open('a') as stream:
        os.chmod(stream.name, 0o600)
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def read_registry(state):
    path = Path(state) / 'registry.json'
    if not path.exists():
        raise ValueError('Reader is not installed. Run scripts/install.py from the document-publication skill.')
    registry = json.loads(path.read_text())
    if registry.get('version') != 1:
        raise ValueError('Unsupported document registry version.')
    origin = urlsplit(registry['origin'])
    if origin.scheme != 'https' or not origin.hostname or origin.path not in ('', '/') or origin.query or origin.fragment or origin.username:
        raise ValueError('The reader origin must be an HTTPS origin without credentials or a path.')
    paths, identities = set(), set()
    for entry in registry['documents']:
        relative = PurePosixPath(entry['path'])
        if (relative.is_absolute() or '..' in relative.parts or '\\' in entry['path']
                or any(p.startswith('.') for p in relative.parts) or relative.suffix != '.html'
                or not re.fullmatch('[a-f0-9]{16}', entry['id'])
                or not re.fullmatch('[A-Za-z0-9_-]+', entry['collection'])
                or entry['path'] in paths or entry['id'] in identities
                or entry['mode'] not in ('snapshot', 'live')):
            raise ValueError('Invalid or duplicate publication entry.')
        paths.add(entry['path'])
        identities.add(entry['id'])
    return registry


def read_source(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(descriptor, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('Choose a regular Markdown file.')
        data = stream.read(MAX_SOURCE_BYTES + 1)
    if len(data) > MAX_SOURCE_BYTES:
        raise ValueError('Markdown files must be at most 8 MB.')
    text = data.decode('utf-8-sig')
    if '\0' in text:
        raise ValueError('Choose a UTF-8 Markdown text file.')
    return data, text


def document_title(text, fallback):
    return next((line[2:].strip() for line in text.splitlines() if line.startswith('# ')), fallback)


def entry_url(registry, entry):
    return registry['origin'].rstrip('/') + BASE + quote(entry['path'])


def register(state, source, mode=None, title=None):
    source = Path(source).expanduser().resolve(strict=True)
    if source.suffix.lower() not in ('.md', '.markdown'):
        raise ValueError('Choose a Markdown file (.md or .markdown).')
    data, text = read_source(source)
    with state_lock(state):
        registry = read_registry(state)
        entry = next((row for row in registry['documents'] if row['source'] == str(source)), None)
        if entry is None:
            identity = digest(str(source).encode())[:16]
            name = re.sub(r'[^a-z0-9]+', '-', source.stem.lower()).strip('-')[:64] or 'document'
            entry = {'id': identity, 'source': str(source), 'path': f'documents/{name}-{identity}.html',
                     'collection': 'documents', 'collection_title': 'Published documents', 'mode': 'snapshot'}
            registry['documents'].append(entry)
        entry['mode'] = mode or entry['mode']
        entry['title'] = title or document_title(text, source.stem)
        entry['published_at'] = timestamp()
        if entry['mode'] == 'snapshot':
            snapshots = Path(state) / 'snapshots'
            snapshots.mkdir(mode=0o700, exist_ok=True)
            atomic_write(snapshots / (entry['id'] + '.md'), data)
        save_json(Path(state) / 'registry.json', registry)
        results = generate_locked(state, registry)
        result = results[entry['id']]
        if result.get('error'):
            raise ValueError(result['error'])
        return {**entry, **result, 'url': entry_url(registry, entry)}


def generate_locked(state, registry):
    state = Path(state)
    site = state / 'site'
    result_path = state / 'rendered.json'
    previous = json.loads(result_path.read_text()) if result_path.exists() else {}
    available = {Path(entry['source']): BASE + quote(entry['path']) for entry in registry['documents']}
    results, collections, manifest = {}, {}, []
    expected = {'index.html'}
    for entry in registry['documents']:
        output = site / entry['path']
        try:
            source = Path(entry['source']) if entry['mode'] == 'live' else state / 'snapshots' / (entry['id'] + '.md')
            data, text = read_source(source)
            body = render(Path(entry['source']), text, available)
            collection_url = BASE + quote(entry['collection']) + '/'
            nav = f'<a href="{collection_url}">{html.escape(entry["collection_title"])}</a>'
            # The existing presentation is intentionally retained byte for byte.
            output_html = page(entry['title'], body, nav)
            atomic_write(output, output_html)
            source_hash = digest(data)
            old = previous.get(entry['id'], {})
            results[entry['id']] = {'source_sha256': source_hash, 'html_sha256': digest(output_html.encode()),
                                    'rendered_at': old.get('rendered_at', timestamp()) if old.get('source_sha256') == source_hash else timestamp()}
        except (OSError, ValueError, UnicodeError) as exc:
            # Retain the last rendered page; diagnostics must disclose stale live sources.
            results[entry['id']] = {**previous.get(entry['id'], {}), 'error': str(exc)}
            if not output.is_file():
                continue
            saved = output.read_text()
            notice = 'Source unavailable; showing the last rendered version. '
            if notice not in saved:
                saved = saved.replace('<footer>', '<footer>' + notice)
                atomic_write(output, saved)
            results[entry['id']]['html_sha256'] = digest(saved.encode())
        expected.add(entry['path'])
        label = entry['collection_title']
        group = collections.setdefault(entry['collection'], {'title': label, 'cards': []})
        mode_label = 'Snapshot' if entry['mode'] == 'snapshot' else 'Updates from source'
        if results[entry['id']].get('error'):
            mode_label = 'Source unavailable; saved version'
        group['cards'].append(f'<li><a href="{BASE}{quote(entry["path"])}"><strong>{html.escape(entry["title"])}</strong><span>{mode_label}</span></a></li>')
        manifest.append({'source': entry['source'], 'url': BASE + quote(entry['path']), 'title': entry['title']})
    groups = []
    for name, group in collections.items():
        listing = '<ul class="cards">' + ''.join(group['cards']) + '</ul>'
        title = group['title']
        body = f'<h1>{html.escape(title)}</h1><p class="meta">{len(group["cards"])} reports</p>' + listing
        relative = name + '/index.html'
        expected.add(relative)
        atomic_write(site / relative, page(title, body, refresh=True))
        groups.append(f'<section><h2><a href="{BASE}{quote(name)}/">{html.escape(title)}</a></h2>{listing}</section>')
    body = f'<h1>Research reader</h1><p class="meta">{len(collections)} collections · Tap a report to read</p>' + ''.join(groups)
    atomic_write(site / 'index.html', page('Research reader', body, refresh=True))
    # Only generated HTML lives under site; source content and state are siblings.
    for old in site.rglob('*.html'):
        if old.relative_to(site).as_posix() not in expected:
            old.unlink()
    save_json(result_path, results)
    save_json(state / 'manifest.json', manifest)
    return results


def generate(state=DEFAULT_STATE):
    with state_lock(state):
        return generate_locked(state, read_registry(state))


def verify(url, expected_hash):
    with urlopen(url, timeout=15) as response:
        data = response.read(MAX_SOURCE_BYTES * 8 + 1)
        if response.status != 200 or response.headers.get_content_type() != 'text/html':
            raise ValueError('The phone URL did not return an HTML report.')
        if digest(data) != expected_hash:
            raise ValueError('The phone URL does not match the rendered report. Check the reader service and Tailscale route.')
    return timestamp()


def remove(state, identity):
    with state_lock(state):
        registry = read_registry(state)
        matches = [entry for entry in registry['documents'] if entry['id'] == identity]
        if not matches:
            raise ValueError('Unknown publication ID; use --list.')
        registry['documents'] = [entry for entry in registry['documents'] if entry['id'] != identity]
        save_json(Path(state) / 'registry.json', registry)
        generate_locked(state, registry)
        (Path(state) / 'snapshots' / (identity + '.md')).unlink(missing_ok=True)
        (Path(state) / 'receipts' / (identity + '.json')).unlink(missing_ok=True)
