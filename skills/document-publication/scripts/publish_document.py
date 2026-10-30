#!/Users/walle/miniforge3/bin/python3
"""Publish one Markdown file to the existing private Tailscale research reader."""
import argparse
import json
import os
from pathlib import Path
import sys

# Resolve the installed command symlink before importing its neighboring modules.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from publication import DEFAULT_STATE, entry_url, generate_locked, read_registry, register, remove, save_json, state_lock, transport_origin, verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', nargs='?', help='An explicitly selected UTF-8 Markdown file.')
    parser.add_argument('--mode', choices=('snapshot', 'live'), help='New documents default to snapshot; repeat publications retain their mode.')
    parser.add_argument('--title', help='Optional report title in the reader index.')
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--list', action='store_true', help='List registered documents and source errors.')
    action.add_argument('--remove', metavar='ID', help='Withdraw one published document; preserve its original source.')
    action.add_argument('--check', action='store_true', help='Regenerate and verify every registered phone URL.')
    parser.add_argument('--json', action='store_true', help='Return a publication receipt or structured diagnostics.')
    args = parser.parse_args()
    if bool(args.source) == bool(args.list or args.remove or args.check):
        parser.error('Choose a source file, --list, --remove, or --check.')
    if not args.source and (args.mode or args.title):
        parser.error('--mode and --title require a source file.')
    state = Path(os.environ.get('DOCUMENT_PUBLICATION_STATE', str(DEFAULT_STATE)))
    try:
        if args.source:
            if transport_origin() != read_registry(state)['origin']:
                raise ValueError('Tailscale reader origin changed; rerun the skill installer to reconcile it.')
            receipt = register(state, args.source, args.mode, args.title)
            # Success is emitted only after reading the real HTTPS report and matching its hash.
            receipt['verified_at'] = verify(receipt['url'], receipt['html_sha256'])
            with state_lock(state):
                save_json(state / 'receipts' / (receipt['id'] + '.json'), receipt)
            print(json.dumps(receipt, indent=2) if args.json else receipt['url'])
        elif args.remove:
            remove(state, args.remove)
            print(json.dumps({'removed': args.remove}))
        else:
            if args.check and transport_origin() != read_registry(state)['origin']:
                raise ValueError('The registered origin does not match the private reader route.')
            with state_lock(state):
                registry = read_registry(state)
                results = generate_locked(state, registry)
            rows = [{**entry, **results.get(entry['id'], {}), 'url': entry_url(registry, entry)} for entry in registry['documents']]
            if args.check:
                for row in rows:
                    if not row.get('error'):
                        try:
                            row['verified_at'] = verify(row['url'], row['html_sha256'])
                        except (OSError, ValueError) as exc:
                            row['error'] = str(exc)
            if args.json:
                print(json.dumps(rows, indent=2))
            else:
                for row in rows:
                    print(f'{row["id"]}\t{row["mode"]}\t{row["url"]}' + (f'\tERROR: {row["error"]}' if row.get('error') else ''))
            return int(any(row.get('error') for row in rows))
    except (OSError, ValueError, UnicodeError, KeyError) as exc:
        print(f'Publication failed: {exc}. No verified link was returned; use --list or --check to inspect registration.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
