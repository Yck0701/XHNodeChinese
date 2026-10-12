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
        choices={}
        for source,translation in self.lookup.items():
            # Normalize changes placeholder case; restore the one supported token.
            source=source.replace('{index}','{Index}')
            key=label_key(source,pattern=True)
            if key and ('#' not in key or translation.count('{Index}')==1):
                choices.setdefault(key,set()).add(translation)
        self.aliases={k:next(iter(v)) for k,v in choices.items() if len(v)==1}

    def translated(self,source):
        if source in self.known:return self.known[source]
        if normalized(source) in self.lookup:return self.lookup[normalized(source)]
        key=label_key(source)
        if key and key in self.aliases:return self.aliases[key]
        number=re.search(r'[0-9]+',source)
        if number:
            key=label_key(source[:number.start()]+'{Index}'+source[number.end():],pattern=True)
            if key in self.aliases:return self.aliases[key].replace('{Index}',number.group())
        stem,suffix=indexed(source)
        if suffix and normalized(stem) in self.lookup:return self.lookup[normalized(stem)]+' '+suffix
        if suffix and label_key(stem) in self.aliases:return self.aliases[label_key(stem)]+' '+suffix
        return None


def label_key(source,pattern=False):
    if not source or len(source)>128:return None
    if '#' in source:return None
    if pattern and source.count('{Index}')==1:source=source.replace('{Index}','#')
    if not re.fullmatch(r'[A-Za-z #]+' if pattern else r'[A-Za-z ]+',source):return None
    if source.count('#')>1:return None
    return source.replace(' ','').casefold() or None


def compact_key(source):
    # Comparison key for complete labels, never for sentence fragments.
    if re.fullmatch(r'[A-Za-z]+(?: [A-Za-z]+)*',source):
        return source.replace(' ','').casefold()
    return None
