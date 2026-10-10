"""CSV-to-localization pipeline, usable both inside UE and from normal Python."""
import csv
import json
import os
import re
import tempfile
import time
from collections import Counter
from pathlib import Path
from . import locres

TARGET = 'XHNodeChinese'
CULTURE = 'zh-Hans-CN'
FIELDS = ['Source', 'Translation', 'Namespace', 'Key', 'Category']
PATTERNS = [
    ('Niagara', re.compile('niagara', re.I)),
    ('Material', re.compile('material|materialexpression|materialgraph', re.I)),
    ('Blueprint', re.compile('blueprint|k2node|kismet|edgraph|graphnode|graphpin', re.I)),
]


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
    try:
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_json(path, data):
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8'))


def category(namespace, key, path=''):
    name = namespace + '/' + key + '/' + path
    for label, pattern in PATTERNS:
        if pattern.search(name):
            return label
    return None


def resources(engine):
    root = Path(engine)
    files = []
    for target in ('Editor', 'Engine', 'PropertyNames', 'ToolTips', 'Category', 'Keywords'):
        path = root / 'Content/Localization' / target / 'en' / (target + '.locres')
        if path.exists():
            files.append(path)
    niagara = root / 'Plugins/FX/Niagara/Content/Localization'
    if niagara.exists():
        files.extend(p for p in niagara.rglob('*.locres') if p.parent.name == 'en')
    return sorted(set(files))


def build_catalogue(engine):
    result = {}
    for file in resources(engine):
        chinese = file.parent.parent / 'zh-Hans' / file.name
        localized = {(n, k): (h, s) for n, k, h, s in locres.read(chinese)} if chinese.exists() else {}
        for namespace, key, source_hash, source in locres.read(file):
            group = category(namespace, key, str(file))
            if not group or not source.strip():
                continue
            translated_hash, translated = localized.get((namespace, key), (None, ''))
            if translated_hash != source_hash:
                translated = ''
            identity = (namespace, key)
            entry = {'namespace': namespace, 'key': key, 'hash': source_hash,
                     'source': source, 'builtin': translated, 'category': group}
            if identity in result and result[identity]['hash'] != source_hash:
                raise ValueError(f'Conflicting engine source identity: {identity}')
            result[identity] = entry
    return list(result.values())


def placeholders(value):
    braces = re.findall(r'(?<!\{)\{[A-Za-z_0-9]+\}(?!\})', value)
    printf = re.findall(r'(?<!%)%(?:\d+\$)?[-+ #0]*(?:\d+|\*)?(?:\.(?:\d+|\*))?(?:ll|[hlL])?[diuoxXfFeEgGaAcsp]', value)
    return Counter(braces + printf)


def load_dictionary(path, include_empty=False):
    """Accept comments, Key/Value, headerless pairs, and legacy named columns."""
    from itertools import chain
    path = Path(path)
    if not path.exists():
        return []
    with path.open(encoding='utf-8-sig', newline='') as stream:
        rows, header, detected, line = [], None, False, 0
        while True:
            first_line = stream.readline()
            if not first_line:
                break
            if not first_line.strip() or first_line.lstrip().startswith('#'):
                line += 1
                continue
            # Parse one complete record. A '#' inside a quoted multiline field
            # remains data; only unquoted lines at record boundaries are comments.
            reader = csv.reader(chain((first_line,), stream), strict=True)
            try:
                values = next(reader)
            except csv.Error as error:
                raise ValueError(f'{path.name}:{line + reader.line_num}: invalid CSV: {error}') from error
            line += reader.line_num
            if not values or all(not value.strip() for value in values):
                continue
            if not detected:
                detected = True
                names = [value.strip() for value in values]
                if {'Source', 'Translation'}.issubset(names):
                    header = names
                    continue
                if len(names) == 2 and set(names) == {'Key', 'Value'}:
                    header = [{'Key': 'Source', 'Value': 'Translation'}[name] for name in names]
                    continue
            if header is None:
                if len(values) != 2:
                    raise ValueError(f'{path.name}:{line}: expected two columns: "English","Chinese"')
                row = dict(zip(('Source', 'Translation'), values))
            else:
                if len(values) > len(header):
                    raise ValueError(f'{path.name}:{line}: more columns than the header')
                row = dict(zip(header, values))
            source, translation = row.get('Source') or '', row.get('Translation') or ''
            if not source or (not translation and not include_empty):
                continue
            if translation and placeholders(source) != placeholders(translation):
                raise ValueError(f'{path.name}:{line}: format placeholders do not match')
            if '\0' in source + translation:
                raise ValueError(f'{path.name}:{line}: NUL is not allowed')
            rows.append({field: row.get(field) or '' for field in FIELDS})
    return rows


def select_translations(catalogue, dictionaries):
    by_source = {}
    for entry in catalogue:
        by_source.setdefault(entry['source'], []).append(entry)
    selected, unmatched = {}, []
    for path in dictionaries:
        for row in load_dictionary(path):
            matches = [entry for entry in by_source.get(row['Source'], [])
                       if (not row['Namespace'] or entry['namespace'] == row['Namespace'])
                       and (not row['Key'] or entry['key'] == row['Key'])
                       and (not row['Category'] or entry['category'] == row['Category'])]
            if not matches:
                unmatched.append(row['Source'])
            for entry in matches:
                selected[(entry['namespace'], entry['key'])] = (*[entry[k] for k in ('namespace', 'key', 'hash')], row['Translation'])
    return list(selected.values()), sorted(set(unmatched))


def compile_dictionary(plugin, catalogue, bilingual=False):
    plugin = Path(plugin)
    entries, unmatched = select_translations(catalogue, [plugin / 'Dictionaries/Base.csv', plugin / 'Dictionaries/User.csv'])
    if bilingual:
        sources = {(e['namespace'], e['key']): e['source'] for e in catalogue}
        entries = [(n, k, h, text + ' (' + sources[(n, k)] + ')') for n, k, h, text in entries]
    # Validate and serialize everything before replacing the active resource.
    payload = locres.encode(entries)
    root = plugin / 'Content/Localization' / TARGET
    atomic_write(root / CULTURE / (TARGET + '.locres'), payload)
    atomic_write(root / 'en' / (TARGET + '.locres'), locres.encode([]))
    atomic_write(root / (TARGET + '.locmeta'), locres.metadata(TARGET))
    identities = {(n, k) for n, k, _, _ in entries}
    groups = Counter(entry['category'] for entry in catalogue if (entry['namespace'], entry['key']) in identities)
    return {'translated_entries': len(entries), 'categories': dict(groups),
            'catalogue_entries': len(catalogue), 'unmatched_sources': unmatched,
            'culture': CULTURE}


def export_pending(plugin, catalogue, destination, observed=(), current_only=False):
    import io
    from .live import useful
    from .auto_translate import normalized
    from .long_text import eligible
    from .term_keys import canonical,Resolver
    entries, _ = select_translations(catalogue, [Path(plugin) / 'Dictionaries/Base.csv', Path(plugin) / 'Dictionaries/User.csv'])
    translated = {(n, k) for n, k, _, _ in entries}
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, quoting=csv.QUOTE_ALL)
    writer.writerow(['Key','Value'])
    candidates = {}
    contexts = {}
    for item in sorted(catalogue, key=lambda x: (x['category'], x['source'])):
        if current_only:
            continue
        if (item['namespace'], item['key']) in translated:
            continue
        if item['builtin'] and item['builtin'] != item['source'] and re.search('[\u3400-\u9fff]', item['builtin']):
            continue
        # Machine-only identifiers and punctuation do not make useful translation work.
        if not useful(item['source']) or eligible(item['source']):
            continue
        source=canonical(item['source'])
        candidates.setdefault(normalized(source),source)
        contexts.setdefault(item['source'],[]).append({k:item[k] for k in ('namespace','key','category')})
    # Include runtime-generated text that does not have a localization identity.
    from .bridge import export_dictionary
    display_terms = export_dictionary(plugin)
    resolver=Resolver(display_terms)
    known = {normalized(s) for s in display_terms}
    for source in sorted(set(observed)):
        if not useful(source) or eligible(source) or resolver.translated(source):
            continue
        source=canonical(source)
        candidates.setdefault(normalized(source),source)
    # Keep prior translations in the editable queue; never discard work in progress.
    destination = Path(destination)
    existing = load_dictionary(destination, include_empty=True)
    filled = {r['Source']:r['Translation'] for r in existing if r['Translation']}
    for source,translation in filled.items():writer.writerow([source,translation])
    filled_normal = {normalized(s) for s in filled}
    pending = [s for key,s in candidates.items() if not resolver.translated(s) and key not in filled_normal]
    for source in pending:writer.writerow([source,''])
    count = len(pending)
    payload = stream.getvalue().encode('utf-8-sig')
    destination = Path(destination)
    if destination.exists() and destination.read_bytes() != payload:
        # Preserve an export the user may already have started translating.
        backup = destination.with_name(destination.stem + '.backup-' + str(time.time_ns()) + destination.suffix)
        atomic_write(backup, destination.read_bytes())
    atomic_write(destination, payload)
    write_json(destination.with_suffix('.contexts.json'),contexts)
    return count
