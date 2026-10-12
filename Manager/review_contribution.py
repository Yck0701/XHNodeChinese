"""Maintainer: assemble contributed native components with trusted runtime files for isolated verification."""
import argparse
import json
from pathlib import Path
import zipfile
import manager_core as c
import contribution_protocol as protocol


def assemble(bundle,catalog,base,expected_base_sha256,output):
    if c.digest(base)!=expected_base_sha256:raise ValueError('可信基础包 SHA-256 不符。')
    meta=protocol.validate_bundle(bundle,c.json_read(catalog))
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():raise ValueError('输出已存在，未覆盖。')
    with zipfile.ZipFile(base) as old,zipfile.ZipFile(bundle) as components:
        members=c.zip_members(old)
        descriptor=json.loads(old.read('XHNodeChinese/XHNodeChinese.uplugin'))
        if descriptor['VersionName']!=meta['plugin_version']:raise ValueError('基础包插件版本不一致。')
        with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED) as z:
            for name,entry in members.items():
                if not name.startswith('XHNodeChinese/'):raise ValueError('基础包格式无效。')
                if name.startswith('XHNodeChinese/Binaries/') or name.endswith('/BUILD_INFO.json'):continue
                z.writestr(name,old.read(entry))
            for name in meta['files']:z.writestr('XHNodeChinese/'+name,components.read(name))
    c.write_json(output.with_suffix('.json'),dict(schema=1,engine=meta['engine'],package=output.name,
        sha256=c.digest(output),verified=False,contribution_sha256=c.digest(bundle),kind=meta['kind'],
        note='Only staged for isolated target-engine verification; never execute submitted DLLs on a production project.'))
    return output


if __name__=='__main__':
    p=argparse.ArgumentParser(description='将投稿组件与可信基础包组合，供隔离验证；不会安装或运行 DLL。')
    for name in ('bundle','catalog','base','expected-base-sha256','output'):p.add_argument('--'+name,required=True)
    a=p.parse_args();print(assemble(a.bundle,a.catalog,a.base,a.expected_base_sha256,a.output))
