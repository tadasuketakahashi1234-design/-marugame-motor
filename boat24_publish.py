"""Publish collected observations without discarding forecasts on push races.

Works in a detached temporary worktree. Failed pushes always retry the SAME
captured observations, merged with the latest upstream history; no recollection.
"""
import argparse
import json
import subprocess
import tempfile
import time
from pathlib import Path

from boat24_integrity import atomic_write, merge_ledgers


def git(*args, cwd=None):
    return subprocess.check_output(['git', *args], cwd=cwd, text=True).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('path')
    parser.add_argument('--key', default='predictions', choices=['predictions', 'records'])
    args = parser.parse_args()
    root = Path(git('rev-parse', '--show-toplevel'))
    collected = json.loads((root / args.path).read_text(encoding='utf-8'))
    for attempt in range(5):
        git('fetch', 'origin', 'main', cwd=root)
        with tempfile.TemporaryDirectory(prefix='boat24-publish-') as tmp:
            work = Path(tmp) / 'checkout'
            git('worktree', 'add', '--detach', str(work), 'origin/main', cwd=root)
            try:
                dest = work / args.path
                remote = json.loads(dest.read_text(encoding='utf-8')) if dest.exists() else {}
                merged = merge_ledgers(remote, collected, args.key)
                if args.key == 'records':
                    from boat24_compare import score_predictions
                    merged['summary'] = {v: score_predictions(merged['records'], v)
                                         for v in ('baseline', 'experimental')}
                atomic_write(dest, merged)
                git('add', '--', args.path, cwd=work)
                if not git('diff', '--cached', '--name-only', cwd=work):
                    print('Already saved')
                    return
                git('-c', 'user.name=github-actions[bot]',
                    '-c', 'user.email=41898282+github-actions[bot]@users.noreply.github.com',
                    'commit', '-m', 'Save Boat24 observations without replacing forecast history', cwd=work)
                push = subprocess.run(['git', 'push', 'origin', 'HEAD:main'], cwd=work)
                if push.returncode == 0:
                    print(f'Saved {len(merged[args.key])} records (attempt {attempt + 1})')
                    return
            finally:
                git('worktree', 'remove', '--force', str(work), cwd=root)
        time.sleep(2)
    raise SystemExit('Push failed; collected observations remain in the original checkout and workflow artifact')


if __name__ == '__main__':
    main()
