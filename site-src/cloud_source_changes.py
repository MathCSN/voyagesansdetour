"""Skip a push build only when a complete candidate-only file list is known.

GitHub Actions push payloads may omit per-commit file lists. Missing data is
not evidence that public source stayed unchanged: use the regular build in
that case. This helper performs no Git or provider calls.
"""
import json
from pathlib import Path, PurePosixPath


def push_requires_build(event):
    """Return False only for a complete, nonempty set of candidate JSON files."""
    if not isinstance(event, dict):
        return True
    commits = event.get('commits')
    size = event.get('size')
    # A count mismatch or absent count cannot rule out omitted commits.
    if (not isinstance(commits, list) or not commits or type(size) is not int
            or size != len(commits) or event.get('truncated', False) is not False):
        return True
    files = []
    for commit in commits:
        if not isinstance(commit, dict):
            return True
        for change in ('added', 'modified', 'removed'):
            paths = commit.get(change)
            if not isinstance(paths, list):
                return True
            for path in paths:
                if not isinstance(path, str) or not path or '\\' in path or '\x00' in path:
                    return True
                parts = PurePosixPath(path).parts
                if (PurePosixPath(path).is_absolute() or '..' in parts or
                        str(PurePosixPath(path)) != path):
                    return True
                files.append(path)
    if not files:
        return True
    # This optimization is intentionally narrower than "no site-src file":
    # workflow and validation changes must also receive an actual build.
    return any(not (path.startswith('site-src/editorial-candidates/') and path.endswith('.json'))
               for path in files)


def push_file_requires_build(path):
    """Load the runner event, conservatively building if it cannot be read."""
    try:
        with Path(path).open(encoding='utf-8') as handle:
            event = json.load(handle)
    except (OSError, ValueError, TypeError):
        return True
    return push_requires_build(event)
