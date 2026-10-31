"""Verify staged binaries before and after publication to a destination store.

A storage adapter must supply put_if_absent(key, bytes) and read(key) methods.
Only read-back content with the same SHA256 is marked published-verified.
LocalDirectoryStore is a reference implementation, NOT hosted/CDN publishing.
No code assumes that a destination URL is live merely because its path is known.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
import re

from .acquisition import MAX_FILE_BYTES, MAX_FILES, MAX_TOTAL_BYTES

STAGED_PATH = re.compile(r'^graph-staged/[0-9a-f]{24}\.(?:[a-z0-9]{1,8})$')
SHA256 = re.compile(r'^[0-9a-f]{64}$')
SAFE_KEY = re.compile(r'^assets/(?:images|documents)/[0-9a-f]{24}\.[a-z0-9]{1,8}$')


class PublicationError(ValueError):
    pass


class LocalDirectoryStore:
    """Opt-in local package destination, no network or destination-domain claim."""

    destination_type = 'local-filesystem'

    def __init__(self, directory: Path):
        self.root = Path(directory)
        if self.root.is_symlink():
            raise PublicationError('PUBLISH_DESTINATION_SYMLINK')
        self.root.mkdir(parents=True, exist_ok=True)
        self._base = self.root.resolve()

    def _path(self, key: str) -> Path:
        if not SAFE_KEY.fullmatch(key):
            raise PublicationError('PUBLISH_KEY_INVALID')
        current = self.root
        for piece in Path(key).parts[:-1]:
            current = current / piece
            if current.is_symlink():
                raise PublicationError('PUBLISH_PATH_SYMLINK')
        path = self.root / key
        if path.is_symlink() or not path.resolve().is_relative_to(self._base):
            raise PublicationError('PUBLISH_PATH_ESCAPE')
        return path

    def put_if_absent(self, key: str, content: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path = self._path(key)
        try:
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
            if hasattr(os, 'O_NOFOLLOW'):
                flags |= os.O_NOFOLLOW
            with os.fdopen(os.open(path, flags, 0o600), 'wb') as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
        except FileExistsError:
            # A previous publication is idempotent only with identical bytes.
            if self.read(key) != content:
                raise PublicationError('PUBLISH_COLLISION') from None

    def read(self, key: str) -> bytes:
        path = self._path(key)
        if path.stat().st_size > MAX_FILE_BYTES:
            raise PublicationError('PUBLISH_READ_LIMIT')
        return path.read_bytes()


def publish_staged_assets(stage_report: dict, staged_root: Path, store, *, output_report: Path | None = None) -> dict:
    """Untrusted reports never choose output paths. Fail individually and retain evidence."""
    rows = stage_report.get('items')
    if not isinstance(rows, list) or len(rows) > MAX_FILES:
        raise PublicationError('PUBLISH_BATCH_LIMIT')
    if not callable(getattr(store, 'put_if_absent', None)) or not callable(getattr(store, 'read', None)):
        raise PublicationError('PUBLISH_STORE_INTERFACE_INVALID')
    if staged_root.is_symlink():
        raise PublicationError('PUBLISH_STAGING_ROOT_SYMLINK')
    root = staged_root.resolve()
    results, total, counted = [], 0, set()
    for row in rows:
        item = {'nodeId': row.get('nodeId'), 'status': 'not-stageable', 'publishedVerified': False}
        if row.get('stageStatus') != 'staged-verified':
            results.append(item)
            continue
        try:
            rel, digest, size = row.get('stagedPath'), row.get('sha256'), row.get('sizeBytes')
            kind = row.get('kind')
            if not isinstance(rel, str) or not STAGED_PATH.fullmatch(rel):
                raise PublicationError('PUBLISH_STAGED_PATH_INVALID')
            if not isinstance(digest, str) or not SHA256.fullmatch(digest):
                raise PublicationError('PUBLISH_HASH_INVALID')
            if type(size) is not int or size < 1 or size > MAX_FILE_BYTES:
                raise PublicationError('PUBLISH_SIZE_INVALID')
            if kind not in ('image', 'document'):
                raise PublicationError('PUBLISH_KIND_INVALID')
            path = staged_root / rel
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise PublicationError('PUBLISH_STAGED_PATH_ESCAPE')
            if path.stat().st_size != size:
                raise PublicationError('PUBLISH_SOURCE_SIZE_MISMATCH')
            content = path.read_bytes()
            if sha256(content).hexdigest() != digest:
                raise PublicationError('PUBLISH_SOURCE_HASH_MISMATCH')
            if digest not in counted:
                total += size
                counted.add(digest)
            if total > MAX_TOTAL_BYTES:
                raise PublicationError('PUBLISH_TOTAL_LIMIT')
            ext = Path(rel).suffix
            category = 'images' if kind == 'image' else 'documents'
            key = f'assets/{category}/{digest[:24]}{ext}'
            store.put_if_absent(key, content)
            received = store.read(key)
            if type(received) is not bytes or len(received) != size or sha256(received).hexdigest() != digest:
                raise PublicationError('PUBLISH_READBACK_MISMATCH')
            item.update(status='published-verified', publishedVerified=True, storageKey=key,
                        sha256=digest, sizeBytes=size)
        except Exception as exc:
            # Store errors can contain tenant credentials, endpoints, or signed URLs.
            code = str(exc)
            if not re.fullmatch(r'PUBLISH_[A-Z0-9_]{1,64}', code):
                code = 'PUBLISH_FAILED'
            item.update(status='publish-failed', errorCode=code)
        results.append(item)
    count = Counter(row['status'] for row in results)
    receipt = {'version': '0.1', 'destinationType': getattr(store, 'destination_type', 'external-adapter'),
               'items': results, 'summary': dict(count), 'readBackVerified': count['published-verified'],
               'allStagedPublished': bool(count['published-verified']) and not count['publish-failed'],
               'allDependenciesPublished': bool(results) and all(x['status'] == 'published-verified' for x in results),
               'hostedDestinationVerified': False,
               'note': 'Byte read-back proves storage equality only. Live website URLs/CDN are unverified.'}
    if output_report is not None:
        output_report.parent.mkdir(parents=True, exist_ok=True)
        output_report.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return receipt
