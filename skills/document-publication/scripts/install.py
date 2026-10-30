#!/Users/walle/miniforge3/bin/python3
"""Install the personal publication command and adopt the existing research reader."""
import argparse
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys

from publication import DEFAULT_STATE, atomic_write, digest, generate, read_registry, save_json, state_lock, transport_origin

SCRIPTS = Path(__file__).resolve().parent
SKILL = SCRIPTS.parent
LABEL = 'net.tailffa31c.research-reader'


def migrate(state, origin):
    """Preserve exact legacy URLs without retaining recursive source discovery."""
    registry_path = state / 'registry.json'
    if registry_path.exists():
        registry = read_registry(state)
        registry['origin'] = origin
        save_json(registry_path, registry)
        return
    legacy = state / 'manifest.json'
    documents = []
    for row in json.loads(legacy.read_text()) if legacy.exists() else []:
        if not row['url'].startswith('/reader/'):
            raise ValueError('Legacy report has an unexpected route.')
        source = str(Path(row['source']).resolve(strict=True))
        relative = row['url'].removeprefix('/reader/')
        collection = relative.split('/', 1)[0]
        index = state / 'site' / collection / 'index.html'
        match = re.search(r'<title>(.*?) · Research reader</title>', index.read_text()) if index.exists() else None
        label = html.unescape(match.group(1)) if match else collection.replace('-', ' ').title()
        documents.append({'id': digest(source.encode())[:16], 'source': source, 'path': relative,
                          'title': row['title'], 'collection': collection, 'collection_title': label,
                          'mode': 'live', 'published_at': datetime.now(timezone.utc).isoformat(timespec='seconds')})
    save_json(registry_path, {'version': 1, 'origin': origin, 'refresh_seconds': 30, 'documents': documents})
    read_registry(state)


def install_link(target, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink() and destination.resolve() == target.resolve():
        return
    if destination.exists() or destination.is_symlink():
        raise ValueError(f'Refusing to replace an unrelated installation: {destination}')
    destination.symlink_to(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, default=DEFAULT_STATE)
    parser.add_argument('--no-start', action='store_true', help='Write installation files without changing the running reader.')
    args = parser.parse_args()
    state = args.state_dir.resolve()
    origin = transport_origin()
    backup = state / 'backups' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup.mkdir(parents=True, mode=0o700)
    for name in ('regenerate.py', 'serve.py', 'README.md', 'registry.json', 'manifest.json', LABEL + '.plist'):
        path = state / name
        if path.is_file():
            shutil.copy2(path, backup / name)
    with state_lock(state):
        migrate(state, origin)
    generate(state)
    wrapper = f'import sys\nsys.path.insert(0, {str(SCRIPTS)!r})\n'
    atomic_write(state / 'regenerate.py', f'#!{sys.executable}\n' + wrapper +
                 f'from publication import generate\nif __name__ == "__main__":\n    generate({str(state)!r})\n')
    atomic_write(state / 'serve.py', f'#!{sys.executable}\n' + wrapper +
                 f'from reader_service import main\nif __name__ == "__main__":\n    main({str(state)!r})\n')
    os.chmod(state / 'regenerate.py', 0o700)
    os.chmod(state / 'serve.py', 0o700)
    plist = state / (LABEL + '.plist')
    atomic_write(plist, plistlib.dumps({'Label': LABEL, 'ProgramArguments': [sys.executable, str(state / 'serve.py')],
                                      'WorkingDirectory': str(state), 'RunAtLoad': True, 'KeepAlive': True,
                                      'ThrottleInterval': 10, 'ProcessType': 'Background',
                                      'StandardOutPath': str(state / 'service.log'), 'StandardErrorPath': str(state / 'service-error.log')}))
    install_link(SKILL, Path.home() / '.agents' / 'skills' / SKILL.name)
    install_link(SCRIPTS / 'publish_document.py', Path.home() / '.local' / 'bin' / 'publish-document')
    launch_agent = Path.home() / 'Library' / 'LaunchAgents' / plist.name
    install_link(plist, launch_agent)
    atomic_write(state / 'README.md', '# Private document reader\n\n'
                 f'Index: {origin}/reader/\n\n'
                 f'Implementation and instructions: {SKILL}/SKILL.md\n\n'
                 'Publish one selected file with `publish-document /absolute/path/report.md`.\n'
                 'New publications default to snapshots; use `--mode live` for automatic source updates.\n'
                 'Repeating a publication keeps its URL and mode. `--list` shows registrations and source errors;\n'
                 '`--check` verifies every phone URL. New registrations require no registry edits or restart.\n\n'
                 'Only generated HTML under `site/` is served. Registry, snapshots, receipts, backups, and logs\n'
                 'stay here, outside the skill repository. The Mac must stay awake and online.\n'
                 f'The existing LaunchAgent {LABEL} hosts loopback port 8767; Tailscale owns /reader.\n')
    if not args.no_start:
        target = f'gui/{os.getuid()}/{LABEL}'
        # An existing loaded plist has unchanged arguments; kickstart adopts the new wrapper once.
        loaded = subprocess.run(['launchctl', 'print', target], capture_output=True).returncode == 0
        if not loaded:
            subprocess.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(launch_agent)], check=True)
        subprocess.run(['launchctl', 'kickstart', '-k', target], check=True)
    print(json.dumps({'installed': str(SKILL), 'command': str(Path.home() / '.local/bin/publish-document'),
                      'registry': str(state / 'registry.json'), 'backup': str(backup), 'origin': origin}, indent=2))


if __name__ == '__main__':
    main()
