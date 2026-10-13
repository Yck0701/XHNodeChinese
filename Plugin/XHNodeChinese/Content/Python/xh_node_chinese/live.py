"""Incremental two-column capture with validated, backed-up personal imports."""
import csv
import hashlib
import io
import re
from itertools import chain
from pathlib import Path
from . import core


def runtime_noise(source):
    text=source.strip()
    modifier=r'(?:Ctrl|Control|Alt|Shift|Cmd|Command|Win|Windows)'
    key=r'(?:[A-Za-z0-9]+|Page Up|Page Down|Left Mouse Button|Right Mouse Button|Middle Mouse Button)'
    if re.fullmatch(modifier+r'(?:\s*\+\s*'+key+r')*',text,re.I):return True
    if re.fullmatch(r'[\d.,]+\s*(?:[KMGTPE]i?B|bytes?|fps|ms|Hz)(?:/s)?',text,re.I):return True
    return bool(re.fullmatch(r'[\d.,]+\s+(?:loaded|selected|items?|actors?|objects?|widgets?|entries|files|rows|nodes)',text,re.I))


def useful(source):
    text=source.strip()
    if not 2 <= len(text) <= 4000 or not re.search(r'[A-Za-z]{2}',text):return False
    if re.search(r'[\u3400-\u9fff]',text):return False
    if re.fullmatch(r'[\d.,%+\- ]+\s*(fps|ms|MiB|MB|GiB|GB|kb|Hz)',text,re.I):return False
    if runtime_noise(text):return False
    if text.startswith(('/', '\\')) or re.match(r'^[A-Za-z]:[\\/]', text):return False
    if re.search(r'https?://|\.(?:uasset|umap|dll|exe|py|csv|json)\b',text,re.I):return False
    if re.match(r'^(?:NS|NE|MI|M|BP|T|SM|SK|S|FX|DA|DT|MPC|MF|Lvl)_',text):return False
    if re.fullmatch(r'[A-Za-z0-9]+(?:_[A-Za-z0-9]+)+',text):return False
    if re.fullmatch(r'[\da-fA-F]{8}-(?:[\da-fA-F]{4}-){3}[\da-fA-F]{12}',text):return False
    if re.match(r'^\d+\s+(?:particles?|items?|actors?|objects?|selected|loaded)\b',text,re.I):return False
    if re.fullmatch(r'[A-Z]{2,4}',text):return False
    return True


def append_pairs(payload, pairs):
    """Append without rewriting existing comments, multiline fields, or scopes."""
    text=payload.decode('utf-8-sig')
    stream=io.StringIO(text,newline='');header=None
    for first in stream:
        if not first.strip() or first.lstrip().startswith('#'):continue
        fields=next(csv.reader(chain((first,),stream),strict=True))
        names=[s.strip() for s in fields]
        if {'Source','Translation'}.issubset(names):header=names
        elif len(names)==2 and set(names)=={'Key','Value'}:
            header=[{'Key':'Source','Value':'Translation'}[s] for s in names]
        break
    output=io.StringIO(newline='');writer=csv.writer(output,quoting=csv.QUOTE_ALL)
    for source,translation in pairs.items():
        values={'Source':source,'Translation':translation}
        writer.writerow([values.get(name,'') for name in header] if header else [source,translation])
    prefix=payload+(b'' if not payload or payload.endswith(b'\n') else b'\r\n')
    return prefix+output.getvalue().encode('utf-8')


class LiveSession:
    def __init__(self,plugin,save,filename='Live.csv'):
        self.plugin=Path(plugin);self.save=Path(save)
        self.path=self.save/filename
        self.state_path=self.save/(Path(filename).stem+'ImportState.json')
        self.last_imported={}
        try:
            import json
            self.last_imported=json.loads(self.state_path.read_text(encoding='utf-8'))
        except (OSError,ValueError):pass
        self.pending=0
        self.total=0
        self.imported=0
        self._sync_key=None
        self._known_snapshot=None

    def sync(self,observed,known,translator=None, separate_long=False):
        from . import personal
        from .auto_translate import normalized
        from .long_text import eligible
        from .term_keys import canonical,Resolver
        observed=tuple(observed)
        sync_key=(core.file_stamp(self.path),core.file_stamp(self.plugin/'Dictionaries/User.csv'),
                  observed,id(translator),separate_long)
        if sync_key==self._sync_key and known==self._known_snapshot:
            return dict(self._last_report,new=0,imported=0,automatic=0,removed=0)
        # Failed/interrupted synchronizations are always retried.
        self._sync_key=None
        input_known=known
        self.save.mkdir(parents=True,exist_ok=True)
        if not self.path.exists():
            core.atomic_write(self.path,('# 待译词条：填写右列中文并保存，约三秒导入个人词典。\r\n'
                '# 已解决的空行自动移除；已填写译文保留。\r\nKey,Value\r\n').encode('utf-8-sig'))
        original=self.path.read_bytes()
        rows=core.load_dictionary(self.path,include_empty=True)
        if self.path.read_bytes()!=original:raise RuntimeError('实时词条正在保存，稍后重试')
        values={r['Source']:r['Translation'] for r in rows}
        filled={s:t for s,t in values.items() if t}
        changed={s:t for s,t in filled.items() if self.last_imported.get(s)!=t}
        imported=0
        if changed:
            report=personal.update(self.plugin,self.save,changed,guard=lambda:self.path.read_bytes()==original)
            imported=report['written']
            self.last_imported.update(changed)
            core.write_json(self.state_path,self.last_imported)
        existing={r['Source']:r['Translation'] for r in core.load_dictionary(self.plugin/'Dictionaries/User.csv')
                  if not any(r[k] for k in personal.SCOPES)}
        known=dict(known,**existing)
        resolver=Resolver(known)
        known_normal={normalized(s) for s in known}
        automatic={};provenance={}
        raw_candidates=list(dict.fromkeys(list(observed)+list(values)))
        candidates=list(dict.fromkeys(canonical(s) for s in raw_candidates
                         if not resolver.translated(s) or not resolver.translated(canonical(s))))
        if translator is not None:
            for source in candidates:
                if len(automatic)>=100:break
                if separate_long and eligible(source):continue
                if not useful(source) or source in filled or resolver.translated(source):continue
                result=translator.translate(source)
                if result:
                    automatic[source]=result[0];provenance[source]=result[1]
            if automatic:
                report=personal.update(self.plugin,self.save,automatic,overwrite=False,guard=lambda:self.path.read_bytes()==original)
                imported+=report['written']
                known_normal.update(normalized(s) for s in automatic)
                known.update(automatic)
                resolver=Resolver(known)
                audit=self.save/'AutoTranslations.json'
                import json
                previous=json.loads(audit.read_text(encoding='utf-8')) if audit.exists() else {}
                previous.update({s:{'translation':t,'method':provenance[s]} for s,t in automatic.items()})
                core.write_json(audit,previous)
        # Completed user edits are retained; unresolved rows are deduplicated,
        # filtered and removed once an exact/normalized dictionary match exists.
        cleaned=dict(filled)
        seen={normalized(s) for s in filled}
        for source in candidates:
            key=normalized(source)
            if separate_long and eligible(source):continue
            if useful(source) and key not in seen and not resolver.translated(source):
                cleaned[source]='';seen.add(key)
        additions={s:t for s,t in cleaned.items() if s not in values}
        removed=len(set(values)-set(cleaned))
        if cleaned!=values or len(rows)!=len(values):
            if self.path.read_bytes()!=original:raise RuntimeError('实时词条正在保存，稍后补充新词')
            # Preserve raw formatting for simple appends. Back up before cleanup.
            if not removed and len(rows)==len(values) and all(cleaned.get(s)==t for s,t in values.items()):
                payload=append_pairs(original,additions)
            else:
                backup=self.save/'ExportBackups'/(self.path.stem+'-'+hashlib.sha256(original).hexdigest()[:16]+'.csv')
                if not backup.exists():core.atomic_write(backup,original)
                payload=append_pairs('# 待译词条：填写中文保存后自动导入；已填写内容保留。\r\nKey,Value\r\n'.encode('utf-8-sig'),cleaned)
            core.atomic_write(self.path,payload)
        values=cleaned
        self.total=len(values)
        self.pending=sum(not value for value in values.values())
        self.imported+=imported
        report={'new':len(additions),'imported':imported,'automatic':len(automatic),'removed':removed,'total':self.total,'pending':self.pending,
                'grouped':sum(canonical(s)!=s for s in raw_candidates),'retained_filled':len(filled)}
        if len(automatic)<100:
            self._sync_key=(core.file_stamp(self.path),core.file_stamp(self.plugin/'Dictionaries/User.csv'),
                            observed,id(translator),separate_long)
            self._known_snapshot=dict(input_known)
            self._last_report=report
        return report
