"""Offline translation memory. No network requests or unfinished phrase writes."""
import re
from collections import defaultdict
from . import core
from .term_keys import normalized,compact_key


def chinese(text):
    return bool(re.search('[\u3400-\u9fff]', text))


class Translator:
    def __init__(self, catalogue, terms):
        candidates = defaultdict(set)
        for item in catalogue:
            source, translation = item['source'], item.get('builtin', '')
            if chinese(translation) and core.placeholders(source) == core.placeholders(translation):
                candidates[normalized(source)].add(translation)
        # An identical English label with conflicting official translations must
        # remain scoped in UE, rather than becoming an arbitrary global override.
        self.memory = {s: next(iter(ts)) for s, ts in candidates.items() if len(ts) == 1}
        self.memory.update({normalized(s): t for s, t in terms.items() if chinese(t)})
        compact=defaultdict(set)
        for source,translation in self.memory.items():
            key=compact_key(source)
            if key:compact[key].add(translation)
        self.compact={key:next(iter(values)) for key,values in compact.items() if len(values)==1}

    def translate(self, source):
        match = self.memory.get(normalized(source))
        if match is None and re.fullmatch(r'[A-Za-z]+',source) and re.search(r'[a-z][A-Z]',source):
            match=self.compact.get(compact_key(source))
        if match and core.placeholders(source) == core.placeholders(match):
            return match, '本地词库整条匹配'
        # Word-by-word concatenation can turn technical labels into misleading
        # Chinese. Only complete translation-memory hits are persisted.
        return None
