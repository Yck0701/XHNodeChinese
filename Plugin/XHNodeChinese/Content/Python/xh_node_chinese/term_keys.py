"""Conservative grouping for numbered compact parameter identifiers."""
import re


def normalized(text):
    return ' '.join(text.split()).casefold().replace('：', ':')


def indexed(source):
    match=re.fullmatch(r'([A-Za-z]+)([0-9]+)',source)
    if not match:return source,''
    stem,suffix=match.groups()
    # Multi-word CamelCase only. Vector3, float4, DX12, version numbers and
    # ordinary labels with numbers are NOT interchangeable numbered parameters.
    if len(re.findall(r'[a-z][A-Z]',stem))<1:return source,''
    return stem,suffix


def canonical(source):
    return indexed(source)[0]


class Resolver:
    def __init__(self,known):
        self.known=known
        self.lookup={normalized(s):t for s,t in known.items()}

    def translated(self,source):
        if source in self.known:return self.known[source]
        if normalized(source) in self.lookup:return self.lookup[normalized(source)]
        stem,suffix=indexed(source)
        if suffix and normalized(stem) in self.lookup:return self.lookup[normalized(stem)]+' '+suffix
        return None


def compact_key(source):
    # Comparison key for complete labels, never for sentence fragments.
    if re.fullmatch(r'[A-Za-z]+(?: [A-Za-z]+)*',source):
        return source.replace(' ','').casefold()
    return None
