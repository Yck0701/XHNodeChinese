"""Fingerprint-gated read-only Niagara metadata reader; explicit scans only."""
import ctypes
import hashlib
import json
from pathlib import Path


class Reader:
    def __init__(self, plugin, engine):
        root=Path(plugin)/'Binaries/Win64'
        manifest=root/'module-index-manifest.json'
        if not manifest.exists():
            raise RuntimeError('当前安装包缺少内部参数索引组件，请更新对应引擎版本的插件。')
        data=json.loads(manifest.read_text(encoding='utf-8'))
        for name,expected in data['engine_sha256'].items():
            if hashlib.sha256((Path(engine)/name).read_bytes()).hexdigest()!=expected:
                raise RuntimeError('内部参数索引组件与当前引擎不匹配，请安装对应版本。')
        path=root/data['bridge_file']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=data['bridge_sha256']:
            raise RuntimeError('内部参数索引组件校验失败。')
        self.dll=ctypes.CDLL(str(path))
        self.dll.XH_IndexAsset.argtypes=[ctypes.c_wchar_p]
        self.dll.XH_IndexAsset.restype=ctypes.c_int
        self.dll.XH_IndexText.argtypes=[ctypes.c_int]
        self.dll.XH_IndexText.restype=ctypes.c_wchar_p

    def read(self, path):
        count=self.dll.XH_IndexAsset(str(path))
        if count<0:raise RuntimeError('无法读取模块元数据：'+str(path))
        return [self.dll.XH_IndexText(i) for i in range(count)]
