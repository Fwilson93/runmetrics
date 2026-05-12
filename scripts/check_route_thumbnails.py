#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATCHED = ROOT / 'docs' / 'data' / 'matched_runs.json'
ROUTES = ROOT / 'docs' / 'assets' / 'routes'


def read_json(path: Path, default):
    if not path.exists():
        return default
    with path.open('r', encoding='utf-8') as f:
        return json.load(f)


def main() -> int:
    matched = read_json(MATCHED, {})
    items = matched.get('items') or []
    pngs = sorted(ROUTES.glob('*.png')) if ROUTES.exists() else []
    refs = [x.get('route_image') for x in items if x.get('route_image')]
    missing = []
    for ref in refs:
        rel = ref.replace('./', '')
        if not (ROOT / 'docs' / rel).exists():
            missing.append(ref)

    print(f'[route-check] png files: {len(pngs)}')
    print(f'[route-check] matched route image refs: {len(refs)}')
    if missing:
        print('[route-check] missing referenced PNGs:')
        for m in missing:
            print(f'  - {m}')
    elif refs:
        print('[route-check] all referenced route PNGs exist')
    else:
        print('[route-check] no route_image refs in docs/data/matched_runs.json')

    print('[route-check] if PNGs are not appearing on GitHub Pages, check git status for docs/assets/routes/')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
