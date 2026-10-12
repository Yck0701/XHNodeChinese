"""Explicit incremental indexing. Deep scans load assets but never save them."""
import json
import re
import time
from pathlib import Path
from . import core
from .auto_translate import Translator
from .term_keys import Resolver, canonical
from .live import useful, append_pairs, runtime_noise
from .long_text import eligible, LongTextSession


def source_text(value):
    value = str(value or '').strip()
    if value.startswith(('NSLOCTEXT(', 'LOCTEXT(', 'INVTEXT(')):
        strings = re.findall(r'"((?:\\.|[^"\\])*)"', value)
        if not strings: return ''
        # UE exported FText quoting uses these escapes. Avoid unicode_escape,
        # which corrupts non-ASCII text and literal asset paths.
        return re.sub(r'\\([\\"nrt])', lambda m: {'n':'\n','r':'\r','t':'\t'}.get(m[1],m[1]), strings[-1])
    return value


def display_name(name):
    name = str(name).replace('_',' ')
    name = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', name)
    return re.sub(r'([A-Z])([A-Z][a-z])',r'\1 \2',name)


class Indexer:
    def __init__(self, plugin, save, catalogue, cached_only=False):
        self.plugin, self.save = Path(plugin), Path(save)
        self.phase = 'idle' if cached_only else 'waiting'
        self.catalogue = catalogue
        self.error = None
        self.assets = []; self.position = 0; self.total = 0
        self.matched = 0; self.pending = {}; self.found = set(); self.translations = {}
        self.missing_descriptions = 0; self.asset_count = 0
        self.deep_position=0; self.deep_sources=0; self.failures={}; self.reader=None
        self.next_step=0; self.paused_phase=None

    def persist(self):
        core.write_json(self.save/'ModuleIndexStatus.json', {
            'phase':self.phase, 'position':self.position, 'total':self.total,
            'assets':self.asset_count, 'matched':self.matched, 'pending':len(self.pending),
            'missing_descriptions':self.missing_descriptions, 'error':self.error,
            'deep_position':self.deep_position, 'deep_total':len(self.assets),
            'deep_sources':self.deep_sources, 'failed_assets':self.failures,
            'time':time.strftime('%Y-%m-%d %H:%M:%S')})

    def label(self):
        if self.phase == 'done':return f'索引完成：{self.asset_count} 个模块，含内部参数与说明；{self.matched} 条已有译文，{len(self.pending)} 条待译，{len(self.failures)} 个模块读取失败。'
        if self.phase == 'error':return '索引失败：'+str(self.error)
        if self.phase == 'idle':return '可手动扫描未打开模块；扫描结果保留在当前工程。'
        if self.phase=='paused':return f'索引已暂停：内部模块 {self.deep_position}/{len(self.assets)}；点击扫描继续。'
        if self.phase=='deep':return f'正在读取内部参数与说明：{self.deep_position}/{len(self.assets)}，待译 {len(self.pending)} 条（可暂停）'
        return f'正在索引模块名称与摘要：{self.position}/{self.total}'

    def pause(self):
        if self.phase in ('waiting','scanning','deep'):
            if self.phase!='waiting':self.flush()
            self.paused_phase=self.phase;self.phase='paused';self.persist()

    def resume(self):
        if self.phase=='paused':self.phase=self.paused_phase;self.persist()

    def add(self, source):
        source=source_text(source)
        if not source or runtime_noise(source):return
        if not eligible(source):source=canonical(source)
        if source in self.found or not re.search('[A-Za-z]{2}',source):return
        if not eligible(source) and not useful(source):return
        self.found.add(source)
        if self.resolver.translated(source):self.matched+=1;return
        translated=self.translator.translate(source)
        if translated:self.translations[source]=translated[0];self.matched+=1
        else:self.pending[source]=''

    def step(self):
        import unreal
        if self.phase in ('paused','idle','done','error'):return False
        if self.phase == 'waiting':
            registry=unreal.AssetRegistryHelpers.get_asset_registry()
            if registry.is_loading_assets():return False
            from .bridge import export_dictionary
            long_terms={r['Source']:r['Translation'] for r in core.load_dictionary(self.save/'LongText.csv')}
            known=export_dictionary(self.plugin,long_terms)
            self.resolver=Resolver(known);self.translator=Translator(self.catalogue,known)
            self.assets=list(registry.get_assets_by_class(unreal.TopLevelAssetPath('/Script/Niagara','NiagaraScript'),True))
            self.total=len(self.catalogue)+len(self.assets);self.phase='scanning';self.persist()
        if self.phase=='deep':
            if time.monotonic()<self.next_step:return False
            if self.reader is None:
                from .module_metadata import Reader
                self.reader=Reader(self.plugin,unreal.Paths.engine_dir())
            if self.deep_position<len(self.assets):
                asset=self.assets[self.deep_position]
                path=str(asset.package_name)+'.'+str(asset.asset_name)
                try:
                    before=len(self.found)
                    for source in self.reader.read(path):self.add(source)
                    self.deep_sources+=len(self.found)-before
                except Exception as error:self.failures[path]=str(error)
                self.deep_position+=1
                self.next_step=time.monotonic()+0.15
                if self.deep_position%10==0:self.persist()
                return False
            self.flush();self.phase='done';self.persist();return True
        deadline=time.perf_counter()+0.004
        count=0
        while self.position<self.total and count<100 and time.perf_counter()<deadline:
            index=self.position;self.position+=1;count+=1
            if index<len(self.catalogue):self.add(self.catalogue[index]['source']);continue
            asset=self.assets[index-len(self.catalogue)]
            self.asset_count+=1
            self.add(display_name(asset.asset_name))
            description=False
            for tag in ('Description','Category','DisplayName','InlineOverviewDisplayName'):
                value=unreal.AssetRegistryHelpers.get_tag_value(asset,tag)
                if isinstance(value,tuple):value=value[-1] if value[0] else ''
                if value:
                    self.add(value)
                    if tag=='Description':description=True
            if not description:self.missing_descriptions+=1
        if self.position<self.total:return False
        self.flush();self.phase='deep';self.persist();return False

    def flush(self):
        # Merge only at completion, retaining manually filled rows on reruns.
        # Official translation memory is a rebuildable cache, not thousands
        # of unsolicited additions to the user's personal dictionary.
        core.atomic_write(self.save/'IndexedTranslations.csv',append_pairs(b'Key,Value\n',self.translations))
        core.write_json(self.save/'ModuleIndexSources.json',{'sources':sorted(self.found),'assets':self.asset_count})
        long_session=LongTextSession(self.save)
        from .bridge import export_dictionary
        known=export_dictionary(self.plugin,self.translations)
        long_session.sync([s for s in self.pending if eligible(s)],known)
        from .live import LiveSession
        LiveSession(self.plugin,self.save,'Indexed.csv').sync(
            [s for s in self.pending if not eligible(s)],known,separate_long=True)
