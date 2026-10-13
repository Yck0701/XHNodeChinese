"""Optional, fingerprint-gated native Slate display adapter."""
import ctypes
import hashlib
import json
from pathlib import Path
from . import core


def dictionary(plugin, long_terms=None):
    result = {}
    for name in ('Base.csv', 'UI.csv', 'Descriptions.csv', 'Shared.csv', 'SharedLongText.csv', 'User.csv'):
        if name == 'User.csv':
            result.update(long_terms or {})
        for row in core.load_dictionary(Path(plugin)/'Dictionaries'/name):
            # Material/Blueprint scoped base rows already use locres identities.
            # Do not turn e.g. the material term "Normal" into a global override.
            if name == 'Base.csv' and row.get('Category') not in ('', 'Niagara'):
                continue
            if name in ('Shared.csv','SharedLongText.csv','User.csv') and row.get('Category') not in ('','Niagara'):
                continue
            if not row.get('Namespace') and not row.get('Key'):
                result[row['Source']] = row['Translation']
    return result


def graph_dictionary(plugin, long_terms=None):
    # Only graph menu widgets/actions receive these ambiguous scoped terms.
    result = {}
    for name in ('Base.csv', 'Graph.csv', 'Shared.csv', 'SharedLongText.csv'):
        for row in core.load_dictionary(Path(plugin)/'Dictionaries'/name):
            if not row.get('Namespace') and not row.get('Key') and row.get('Category') in ('','Material','Blueprint'):
                result[row['Source']] = row['Translation']
    result.update(long_terms or {})
    for row in core.load_dictionary(Path(plugin)/'Dictionaries/User.csv'):
        if not row.get('Namespace') and not row.get('Key') and row.get('Category') in ('','Material','Blueprint'):
            result[row['Source']] = row['Translation']
    return result


def export_dictionary(plugin, long_terms=None):
    # Known graph labels must not keep returning to the translation queue.
    # This map is for export deduplication, never for global Slate replacement.
    result = graph_dictionary(plugin, long_terms)
    result.update(dictionary(plugin, long_terms))
    return result


class Bridge:
    def __init__(self, plugin, engine):
        root = Path(plugin)/'Binaries/Win64'
        manifest = json.loads((root/'bridge-manifest.json').read_text(encoding='utf-8'))
        for relative, expected in manifest['engine_sha256'].items():
            path = Path(engine)/relative
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != expected:
                raise RuntimeError('引擎版本不匹配，已跳过动态显示组件：'+relative)
        dll = root/manifest.get('bridge_file', 'XHSlateBridge.dll')
        if hashlib.sha256(dll.read_bytes()).hexdigest() != manifest['bridge_sha256']:
            raise RuntimeError('显示组件校验失败，请重新安装本插件')
        self.dll = ctypes.CDLL(str(dll))
        self.dll.XH_Clear.argtypes = []
        self.dll.XH_Clear.restype = None
        self.dll.XH_Add.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        self.dll.XH_Add.restype = None
        self.dll.XH_Enable.argtypes = [ctypes.c_int, ctypes.c_int]
        self.dll.XH_Enable.restype = None
        self.dll.XH_Tick.argtypes = []
        self.dll.XH_Tick.restype = ctypes.c_int
        self.dll.XH_ObservedCount.argtypes = []
        self.dll.XH_ObservedCount.restype = ctypes.c_int
        self.dll.XH_Observed.argtypes = [ctypes.c_int]
        self.dll.XH_Observed.restype = ctypes.c_wchar_p
        for name in ('XH_AddLegacy','XH_AddGraph'):
            getattr(self.dll,name).argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
            getattr(self.dll,name).restype = None
        self.dll.XH_Preview.argtypes = [ctypes.c_wchar_p]
        self.dll.XH_Preview.restype = ctypes.c_wchar_p
        self.dll.XH_CurrentCount.argtypes = []
        self.dll.XH_CurrentCount.restype = ctypes.c_int
        self.dll.XH_Current.argtypes = [ctypes.c_int]
        self.dll.XH_Current.restype = ctypes.c_wchar_p
        self.dll.XH_BoundText.argtypes = [ctypes.c_int, ctypes.c_int]
        self.dll.XH_BoundText.restype = ctypes.c_wchar_p
        self.dll.XH_BindingCount.argtypes = []
        self.dll.XH_BindingCount.restype = ctypes.c_int
        self.dll.XH_BoundOverview.argtypes = [ctypes.c_int]
        self.dll.XH_BoundOverview.restype = ctypes.c_int
        self.dll.XH_Service.argtypes = [ctypes.c_int]
        self.dll.XH_Service.restype = None
        self.dll.XH_SearchCount.argtypes = []
        self.dll.XH_ParameterPanelCount.restype = ctypes.c_int
        self.dll.XH_ParameterCount.restype = ctypes.c_int
        self.dll.XH_ParameterProbe.argtypes = [ctypes.c_wchar_p]
        self.dll.XH_ParameterProbe.restype = ctypes.c_wchar_p
        self.dll.XH_SearchCount.restype = ctypes.c_int
        self.dll.XH_SearchName.argtypes = [ctypes.c_int]
        self.dll.XH_SearchName.restype = ctypes.c_wchar_p
        self.dll.XH_SearchProbe.argtypes = [ctypes.c_wchar_p]
        self.dll.XH_SearchProbe.restype = ctypes.c_wchar_p
        self.dll.XH_GraphPreview.argtypes = [ctypes.c_wchar_p]
        self.dll.XH_GraphPreview.restype = ctypes.c_wchar_p
        self.dll.XH_GraphCount.restype = ctypes.c_int
        self.dll.XH_GraphName.argtypes = [ctypes.c_int]
        self.dll.XH_GraphName.restype = ctypes.c_wchar_p
        self.dll.XH_GraphProbe.argtypes = [ctypes.c_wchar_p]
        self.dll.XH_GraphProbe.restype = ctypes.c_wchar_p
        self.dll.XH_Collect.argtypes = [ctypes.c_int]
        self.dll.XH_Collect.restype = None
        self.dll.XH_AckCapture.argtypes = [ctypes.c_int]
        self.dll.XH_AckCapture.restype = None
        self.dll.XH_IsCollecting.restype = ctypes.c_int
        self.dll.XH_ScanMs.restype = ctypes.c_double
        self.terms = {}

    def rebuild(self, plugin, enabled, bilingual, long_terms=None):
        terms = dictionary(plugin, long_terms)  # Parse fully before changing the live map.
        personal = {r['Source']:r['Translation'] for r in core.load_dictionary(Path(plugin)/'Dictionaries/User.csv')
                    if not any(r[k] for k in ('Namespace','Key','Category'))}
        graph_terms = graph_dictionary(plugin, long_terms)
        known_terms = export_dictionary(plugin, long_terms)
        self.dll.XH_Clear()
        for source, translation in terms.items():
            self.dll.XH_Add(source, translation)
        # Load personal entries last so normalized variants also override Base.
        for source, translation in personal.items():
            self.dll.XH_Add(source, translation)
            self.dll.XH_AddLegacy(source, translation)
        for source, translation in graph_terms.items():
            self.dll.XH_AddGraph(source, translation)
        # Normalized personal aliases win over all base variants.
        for source, translation in personal.items():
            self.dll.XH_AddGraph(source, translation)
        self.terms = terms
        self.known_terms = known_terms
        self.personal = personal
        self.enable(enabled, bilingual)

    def enable(self, enabled, bilingual):
        self.dll.XH_Enable(enabled, bilingual)

    def collect(self, enabled):
        self.dll.XH_Collect(int(enabled))

    def ack_capture(self, count):
        self.dll.XH_AckCapture(count)

    def tick(self):
        # New bridges spread refreshes over frames; older adapters remain loadable.
        if hasattr(self.dll,'XH_Slice'):self.dll.XH_Slice()
        else:self.dll.XH_Tick()

    @property
    def count(self):
        return self.dll.XH_BindingCount()

    def start(self):
        self.dll.XH_Service(1)

    def shutdown(self):
        self.dll.XH_Service(0)
        self.enable(False,False)

    def preload(self, sources):
        for source in sources:
            self.preview(source)

    def observed(self):
        return [self.dll.XH_Observed(i) for i in range(self.dll.XH_ObservedCount())]

    def current(self):
        return sorted({self.dll.XH_Current(i) for i in range(self.dll.XH_CurrentCount())})

    def preview(self, source):
        return self.dll.XH_Preview(source)

    def search_index(self, detailed=True):
        if not detailed:
            return {'items':self.dll.XH_SearchCount(),'translated':self.dll.XH_SearchTranslatedCount()}
        names = [self.dll.XH_SearchName(i) for i in range(self.dll.XH_SearchCount())]
        return {'items': len(names), 'names': names,
                'translated': sum(self.preview(name) != name for name in names)}

    def search_probe(self, query):
        return self.dll.XH_SearchProbe(query).splitlines()

    def parameter_index(self):
        return {'panels':self.dll.XH_ParameterPanelCount(),'items':self.dll.XH_ParameterCount()}

    def parameter_probe(self, query):
        return self.dll.XH_ParameterProbe(query).splitlines()

    def graph_index(self, detailed=True):
        if not detailed:
            return {'items':self.dll.XH_GraphCount(),'translated':self.dll.XH_GraphTranslatedCount()}
        names = [self.dll.XH_GraphName(i) for i in range(self.dll.XH_GraphCount())]
        return {'items': len(names), 'names': names,
                'translated': sum(self.dll.XH_GraphPreview(name) != name for name in names)}

    def bindings(self):
        return [{'source':self.dll.XH_BoundText(i,0),'display':self.dll.XH_BoundText(i,1),
                 'area':'NiagaraOverview' if self.dll.XH_BoundOverview(i) else 'Other'}
                for i in range(max(0,self.count))]
