#!/usr/bin/env python3
"""
Add a file-backed mock mapping into mock_api/mocks.json and copy the file into mock_data/.

Usage:
  python add_mock.py --label mymock --src /path/to/resp.json --type json

This will copy the source into mock_data/ and add an entry in mocks.json:
  { "mymock": { "path": "mock_data/mymock__resp.json", "type": "json", "status": 200 } }

"""
import argparse
import os
import json
import shutil
from pathlib import Path

HERE = Path(__file__).parent
MOCKS_JSON = HERE / 'mocks.json'
MOCK_DATA_DIR = HERE / 'mock_data'


def load_mappings():
    if MOCKS_JSON.exists():
        try:
            return json.loads(MOCKS_JSON.read_text())
        except Exception:
            return {}
    return {}


def save_mappings(m):
    MOCKS_JSON.write_text(json.dumps(m, indent=2))


def main():
    p = argparse.ArgumentParser(description='Register a file-backed mock')
    p.add_argument('--label', required=True, help='Label to register (served at /mocks/{label})')
    p.add_argument('--src', required=True, help='Source file to copy into mock_data')
    p.add_argument('--type', default='json', choices=['json', 'csv', 'raw'], help='Type of mock')
    p.add_argument('--status', type=int, default=200, help='HTTP status code to return')
    p.add_argument('--headers', default='{}', help='JSON string of headers to return')
    p.add_argument('--content-type', default=None, help='Content-Type for raw responses')
    p.add_argument('--overwrite', action='store_true', help='Overwrite existing mapping')
    args = p.parse_args()

    label = args.label
    src = Path(args.src)
    if not src.exists():
        print('Source not found:', src)
        raise SystemExit(2)

    MOCK_DATA_DIR.mkdir(parents=True, exist_ok=True)

    mappings = load_mappings()
    if label in mappings and not args.overwrite:
        print('Label already exists. Use --overwrite to replace.')
        raise SystemExit(3)

    # Validate json if needed
    if args.type == 'json':
        try:
            json.loads(src.read_text())
        except Exception as e:
            print('Source is not valid JSON:', e)
            raise SystemExit(4)

    dest_name = f"{label}__{src.name}"
    dest = MOCK_DATA_DIR / dest_name
    shutil.copy2(src, dest)

    # If overwriting, optionally remove previous file if it exists and different
    if args.overwrite and label in mappings:
        prev = mappings[label].get('path')
        try:
            if prev and prev != str(dest):
                prev_path = (HERE / prev).resolve()
                if prev_path.exists() and prev_path.parent == MOCK_DATA_DIR.resolve():
                    prev_path.unlink()
        except Exception:
            pass

    entry = {
        'path': str(Path('mock_data') / dest_name),
        'type': args.type,
        'status': args.status,
    }
    try:
        entry['headers'] = json.loads(args.headers)
    except Exception:
        print('Invalid headers JSON; using empty')
        entry['headers'] = {}
    if args.content_type:
        entry['content_type'] = args.content_type

    mappings[label] = entry
    save_mappings(mappings)

    print('Registered mock:', label)
    print(json.dumps({label: entry}, indent=2))


if __name__ == '__main__':
    main()
