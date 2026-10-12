"""Read common copied web answers; bind every translation to a known request."""
import csv
import io
import json
import re
from . import multi_translate as mt


def decode(text):
    if not isinstance(text, str) or len(text) > 1000000:
        raise ValueError('回答超过 1 MB，请分批复制')
    decoder = json.JSONDecoder()
    # JSON can be surrounded by a code fence or explanatory prose. Only
    # recognize response envelopes, never a nested example or arbitrary object.
    candidates = []
    for match in re.finditer(r'[\[{]', text):
        try: value, _ = decoder.raw_decode(text[match.start():])
        except ValueError: continue
        if isinstance(value, dict) and 'translations' in value:
            candidates.append(value)
    if candidates:
        if len(candidates) != 1: raise ValueError('发现多个 JSON 回答，请只复制要导入的那一份')
        return candidates[0]
    stripped = re.sub(r'^```[^\n]*\n|\n```\s*$', '', text.strip())
    try:
        value = json.loads(stripped)
        if isinstance(value, list): return {'translations': value}
        if isinstance(value, dict):
            return {'translations': [{'source': k, 'translation': v} for k, v in value.items()]}
    except ValueError: pass
    rows = []
    if any(line.strip().startswith('|') for line in text.splitlines()):
        for line in text.splitlines():
            if not line.strip().startswith('|'): continue
            cells = [c.strip().strip('`') for c in re.split(r'(?<!\\)\|', line.strip().strip('|'))]
            if len(cells) == 2: rows.append(cells)
            elif len(cells) == 3: rows.append([cells[0], cells[2]])
    else:
        # Keep quoted multiline explanations intact.
        delimiter = '\t' if '\t' in stripped and not stripped.startswith('"') else ','
        try: rows = list(csv.reader(io.StringIO(stripped), delimiter=delimiter, strict=True))
        except csv.Error: raise ValueError('表格未复制完整；请复制完整 JSON、Markdown 表格或两列 CSV') from None
    records = []
    for row in rows:
        if len(row) != 2: continue
        key, value = [s.strip() for s in row]
        if key.casefold() in ('id', 'key', 'source', '英文', '原文', '编号', '词条id'): continue
        if re.fullmatch(r'[:\- ]+', key): continue
        if key and value: records.append({'source': key, 'translation': value})
    if not records: raise ValueError('未识别到译文。请复制含编号或英文原文的 JSON、表格或两列 CSV；原回答已保存到任务文件夹')
    return {'translations': records}


def normalize(batch, text):
    data = decode(text)
    if data.get('request_id', batch['request_id']) != batch['request_id']:
        raise ValueError('回答属于另一个任务，请从“任务进度”打开对应任务后导入')
    rows, skips = data.get('translations', []), data.get('skipped', [])
    if not isinstance(rows, list) or not isinstance(skips, list): raise ValueError('译文应为列表')
    by_id = {i['id']: i for i in batch['items']}
    by_source = {i['source']: i['id'] for i in batch['items']}
    accepted, rejected, seen = {'request_id': batch['request_id'], 'translations': [], 'skipped': []}, [], set()
    for field, records in (('translations', rows), ('skipped', skips)):
        for row in records:
            if not isinstance(row, dict): raise ValueError('译文条目不是对象')
            key = str(row.get('id', '')) if 'id' in row else by_source.get(row.get('source', ''), row.get('source', ''))
            if key not in by_id: raise ValueError('包含不属于当前批次的编号或原文：' + str(key)[:80])
            if key in seen: raise ValueError('编号重复：' + key)
            seen.add(key)
            record = {'id': key, 'translation' if field == 'translations' else 'reason': row.get('translation' if field == 'translations' else 'reason')}
            single = dict(accepted, translations=[], skipped=[])
            single[field] = [record]
            try: mt.validate_batch(dict(batch, items=[by_id[key]]), single)
            except (ValueError, TypeError) as error:
                rejected.append({'id': key, 'source': by_id[key]['source'], 'reason': str(error)})
            else: accepted[field].append(record)
    accepted_ids = {i['id'] for i in accepted['translations'] + accepted['skipped']}
    missing = [i['id'] for i in batch['items'] if i['id'] not in accepted_ids]
    if not accepted_ids: raise ValueError('本次没有可导入译文：' + (rejected[0]['reason'] if rejected else '回答为空'))
    return accepted, {'accepted': len(accepted_ids), 'remaining': len(missing), 'remaining_ids': missing, 'rejected': rejected}
