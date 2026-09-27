"""Exact approved media inventory shared by local and cloud site builds."""
import hashlib
import json
from pathlib import Path
import re

NAMES = {'reel.mp4', 'poster.jpg', 'credits.txt', 'dmsans-OFL.txt', 'playfairdisplay-OFL.txt'}


def approved_files(root):
    root = Path(root)
    catalogue_path = root / 'public-media.json'
    if catalogue_path.is_symlink():
        raise ValueError('Media catalogue symlink refused')
    catalogue = json.loads(catalogue_path.read_text())
    if not isinstance(catalogue, dict) or set(catalogue) != {'schemaVersion', 'items'} or catalogue['schemaVersion'] != 1:
        raise ValueError('Invalid media catalogue')
    items = catalogue['items']
    if not isinstance(items, list) or len(items) > 104:
        raise ValueError('Invalid media inventory size')
    result, seen = [], set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {'contentId', 'approved', 'files'}:
            raise ValueError('Invalid media item')
        identity = item['contentId']
        if not isinstance(identity, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,99}', identity) or identity in seen or item['approved'] is not True:
            raise ValueError('Unapproved or duplicate media identity')
        seen.add(identity)
        files = item['files']
        if not isinstance(files, list) or not 3 <= len(files) <= 5:
            raise ValueError('Incomplete approved media')
        names = []
        for entry in files:
            if not isinstance(entry, dict) or set(entry) != {'name', 'sha256', 'bytes'}:
                raise ValueError('Invalid media file record')
            name = entry['name']
            if not isinstance(name, str) or name not in NAMES or name in names:
                raise ValueError('Media filename outside allowlist')
            names.append(name)
            if type(entry['bytes']) is not int or not 0 < entry['bytes'] <= 50_000_000 or not isinstance(entry['sha256'], str) or not re.fullmatch(r'[a-f0-9]{64}', entry['sha256']):
                raise ValueError('Invalid media fingerprint')
            relative = Path('production') / identity / name
            path = root / 'social-media' / relative
            chain = [root / 'social-media', root / 'social-media' / 'production', path.parent, path]
            if any(p.is_symlink() for p in chain) or not path.is_file() or path.stat().st_size != entry['bytes']:
                raise ValueError('Missing or altered approved media: ' + str(relative))
            if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
                raise ValueError('Media hash mismatch: ' + str(relative))
            result.append(str(relative))
        if not {'reel.mp4', 'poster.jpg', 'credits.txt'}.issubset(names):
            raise ValueError('Approved video, poster and credits required')
    return tuple(result)
