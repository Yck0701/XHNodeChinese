"""Separate manual long-text dictionary, with no model or network dependency."""
import hashlib
from pathlib import Path
import re
from . import core
from .live import append_pairs


def eligible(source):
    if source.startswith('状态：') and '用户词典：' in source:return False
    return len(source)>=100 and len(re.findall(r'[A-Za-z]+',source))>=12


class LongTextSession:
    def __init__(self,save):
        self.save=Path(save)
        self.path=self.save/'LongText.csv'
        self.terms={};self.pending=0;self.total=0;self.error=None
        self._last_payload=None

    def sync(self,sources,known,include_known=False):
        if not self.path.exists():
            header=('# 长文本手动翻译：只编辑右列中文；保存后约三秒自动应用。\r\n'
                    '# 长文本允许字段内换行；保留双引号，正文中的英文双引号写成两个双引号。\r\n'
                    '# 留空则使用原文或已有完整译文；本文件独立于个人词典，不调用任何翻译服务。\r\nKey,Value\r\n')
            core.atomic_write(self.path,header.encode('utf-8-sig'))
        original=self.path.read_bytes()
        try:
            rows=core.load_dictionary(self.path,include_empty=True)
            values={r['Source']:r['Translation'] for r in rows}
            additions={s:known.get(s,'') if include_known else '' for s in sorted(set(sources))
                       if eligible(s) and s not in values and (include_known or s not in known)}
            if self.path.read_bytes()!=original:raise RuntimeError('长文本文件正在保存，稍后重试')
            if additions:
                original=append_pairs(original,additions)
                core.atomic_write(self.path,original)
                values.update(additions)
            translations={s:t for s,t in values.items() if t}
            changed=translations!=self.terms
            if changed:
                backup=self.save/'LongTextBackups'/(hashlib.sha256(original).hexdigest()[:16]+'.csv')
                if not backup.exists():core.atomic_write(backup,original)
                if self._last_payload is not None:
                    prior=self.save/'LongTextBackups'/(hashlib.sha256(self._last_payload).hexdigest()[:16]+'.csv')
                    if not prior.exists():core.atomic_write(prior,self._last_payload)
            self.terms=translations;self._last_payload=original
            self.total=len(values);self.pending=sum(not t and s not in known and eligible(s) for s,t in values.items());self.error=None
            return changed
        except Exception as error:
            self.error=str(error)
            raise

    def status(self):
        return {'total':self.total,'pending':self.pending,'translated':len(self.terms),'error':self.error,'path':str(self.path)}
