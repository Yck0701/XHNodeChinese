"""Lossless-precedence compaction and backed-up, validated dictionary updates."""
import csv
import hashlib
import io
from pathlib import Path
from . import core

SCOPES = ('Namespace', 'Key', 'Category')


def identity(row):
    return tuple(row[key] for key in ('Source', *SCOPES))


def compact(rows):
    # Keep the last occurrence at its original position: overlapping scopes and
    # normalized display aliases rely on the order of the remaining records.
    seen, result = set(), []
    for row in reversed(rows):
        key = identity(row)
        if not row['Translation'] or key in seen:
            continue
        seen.add(key)
        result.append(row)
    return list(reversed(result))


def encode(rows):
    scoped = any(any(row[k] for k in SCOPES) for row in rows)
    stream = io.StringIO(newline='')
    stream.write('# 用户自定义词典：UTF-8；自动更新同一词条，个人译文优先。\r\n')
    writer = csv.writer(stream, quoting=csv.QUOTE_ALL)
    fields = core.FIELDS if scoped else ['Source', 'Translation']
    writer.writerow(fields if scoped else ['Key', 'Value'])
    writer.writerows([[row[key] for key in fields] for row in rows])
    return stream.getvalue().encode('utf-8-sig')


def update(plugin, save, pairs=None, overwrite=True, guard=None):
    user = Path(plugin) / 'Dictionaries/User.csv'
    before = user.read_bytes()
    rows = core.load_dictionary(user, include_empty=True)
    kept = compact(rows)
    existing = {r['Source']: r['Translation'] for r in kept if not any(r[k] for k in SCOPES)}
    pairs = pairs or {}
    changes = {s: t for s, t in pairs.items() if t and existing.get(s) != t
               and (overwrite or s not in existing)}
    for source, translation in changes.items():
        if '\0' in source + translation or core.placeholders(source) != core.placeholders(translation):
            raise ValueError('自动写入词条的占位符不匹配：' + source)
    removed = len(rows) - len(kept)
    # Move intentional overrides to the end, keeping the same precedence as
    # the previous append-based importer without keeping obsolete records.
    kept = [r for r in kept if any(r[k] for k in SCOPES) or r['Source'] not in changes]
    kept.extend(dict(zip(core.FIELDS, (s, t, '', '', ''))) for s, t in changes.items())
    if removed or changes:
        payload = encode(kept)
        if user.read_bytes() != before or (guard is not None and not guard()):
            raise RuntimeError('词典正在被编辑，稍后重试')
        backup = Path(save) / 'DictionaryBackups' / ('compact-' + hashlib.sha256(before).hexdigest()[:16] + '.csv')
        if not backup.exists():
            core.atomic_write(backup, before)
        core.atomic_write(user, payload)
    return {'before': len(rows), 'after': len(kept), 'removed': removed, 'written': len(changes)}
