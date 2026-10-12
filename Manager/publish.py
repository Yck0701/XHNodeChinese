"""Create a GitHub Releases asset set locally. Never upload credentials or user data."""
import argparse
import json
from pathlib import Path
import shutil
import zipfile
import manager_core as core


def public_plugin(package,dest):
    """Remove maintainer sources while leaving all runtime bytes unchanged."""
    dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True)
    temp=dest.with_suffix('.zip.tmp')
    with zipfile.ZipFile(package) as old,zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as new:
        members=core.zip_members(old)
        for name,info in members.items():
            p=Path(name);parts=p.parts
            if len(parts)<2 or parts[0]!='XHNodeChinese':raise ValueError('插件包根目录无效。')
            relative='/'.join(parts[1:])
            if parts[1] in ('Source','Intermediate','Saved','__pycache__'):continue
            if parts[1]=='Tools' and relative!='Tools/ReloadInEditor.py':continue
            data=old.read(info)
            if relative=='ADVANCED.md':
                text=data.decode('utf-8')
                text=text.split('## 引擎兼容与重新编译')[0]
                text+='## 引擎兼容与重新编译\n\n本包仅适配随包指纹记录对应的引擎构建。即使版本号相同，也不能强行加载不匹配的动态组件。\n\n公开安装包不包含 C++ 源码或维护工具。需要编译其他版本时，请向维护者申请授权源码包，在星河插件管理器的编译页选择本地源码包进行构建与验证。\n'
                data=text.encode('utf-8')
            new.writestr(info,data)
    with zipfile.ZipFile(temp) as z:
        core.zip_members(z)
        assert not any('/Source/' in n or n.endswith('/build_bridge.py') or '/CompilerHost/' in n for n in z.namelist())
        if z.testzip():raise ValueError('公开插件包校验失败。')
    temp.replace(dest)
    return dest


def prepare(plugin_zip,shared,dest,engine_version='5.8.3',label='定制 UE 5.8.3',verification=None):
    dest=Path(dest);dest.mkdir(parents=True,exist_ok=True);shared=Path(shared)
    with zipfile.ZipFile(plugin_zip) as z:
        core.zip_members(z)
        bridge=json.loads(z.read('XHNodeChinese/Binaries/Win64/bridge-manifest.json'))
        descriptor=json.loads(z.read('XHNodeChinese/XHNodeChinese.uplugin'))
        assert z.read('XHNodeChinese/Dictionaries/User.csv').strip()==b'Key,Value', 'Release must contain empty personal dictionary'
    if not verification or not core.json_read(verification).get('passed'):raise ValueError('发布插件包需要目标引擎通过验证的记录。')
    fingerprint=core.digest(plugin_zip)[:12]
    plugin_name='XHNodeChinese-'+descriptor['VersionName']+'-UE'+engine_version+'-'+fingerprint+'.zip'
    public_plugin(plugin_zip,dest/plugin_name)
    shared_name='XHShared-2026.10.10.zip'
    with zipfile.ZipFile(dest/shared_name,'w',zipfile.ZIP_DEFLATED) as z:
        for name in ('User.csv','LongText.csv','curation-report.json','README.md'):
            if (shared/name).is_file():z.write(shared/name,name)
    contents=core.shared_contents(dest/shared_name)
    manifest={'schema':1,'manager_version':core.VERSION,'repository':core.REPOSITORY,
              'plugins':[{'label':label+' / 星河 '+descriptor['VersionName'],'version':descriptor['VersionName'],
                          'url':plugin_name,'sha256':core.digest(dest/plugin_name),'verified':True,
                          'engine':{'version':engine_version,'sha256':bridge['engine_sha256']}}],
              'shared':{'version':'2026.10.10','url':shared_name,'sha256':core.digest(dest/shared_name),
                        'terms':core.csv_validate(contents[core.PROTECTED[0]]),'long_texts':core.csv_validate(contents[core.PROTECTED[1]])}}
    core.write_json(dest/'manifest.json',manifest)
    return manifest


def add_verified(manifest_file,package,report,verification,label):
    manifest_file=Path(manifest_file);report=core.json_read(report);verification=core.json_read(verification)
    if report['sha256']!=core.digest(package):raise ValueError('编译报告与安装包不匹配。')
    if not verification.get('passed') or verification.get('package_sha256')!=report['sha256']:
        raise ValueError('验证记录必须含 passed=true 和对应 package_sha256。')
    with zipfile.ZipFile(package) as z:
        core.zip_members(z)
        bridge=json.loads(z.read('XHNodeChinese/Binaries/Win64/bridge-manifest.json'))
        descriptor=json.loads(z.read('XHNodeChinese/XHNodeChinese.uplugin'))
        if bridge['engine_sha256']!=report['engine']['sha256']:raise ValueError('引擎记录不匹配。')
    dest=manifest_file.parent/Path(package).name.replace('-UNVERIFIED','')
    public_plugin(package,dest)
    manifest=core.json_read(manifest_file)
    entry={'label':label,'version':descriptor['VersionName'],'url':dest.name,'sha256':core.digest(dest),'engine':report['engine'],'verified':True}
    manifest['plugins']=[entry]+[p for p in manifest['plugins'] if p['engine']['sha256']!=entry['engine']['sha256']]
    core.write_json(manifest_file,manifest)


def update_shared(manifest_file,shared,version):
    import re
    if not re.fullmatch(r'[0-9A-Za-z][0-9A-Za-z._-]{0,48}',version):raise ValueError('共享版本号格式无效。')
    manifest_file=Path(manifest_file);shared=Path(shared);manifest=core.json_read(manifest_file)
    dest=manifest_file.parent/('XHShared-'+version+'.zip')
    temp=dest.with_suffix('.zip.tmp')
    with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as z:
        for name in ('User.csv','LongText.csv','curation-report.json','README.md'):
            if (shared/name).is_file():z.write(shared/name,name)
    contents=core.shared_contents(temp)
    temp.replace(dest)
    manifest['shared']={'version':version,'url':dest.name,'sha256':core.digest(dest),
        'terms':core.csv_validate(contents[core.PROTECTED[0]]),'long_texts':core.csv_validate(contents[core.PROTECTED[1]])}
    core.write_json(manifest_file,manifest)


if __name__=='__main__':
    p=argparse.ArgumentParser(description='在本地生成发布文件，不自动上传。')
    sub=p.add_subparsers(dest='action',required=True)
    first=sub.add_parser('prepare'); first.add_argument('--plugin',required=True);first.add_argument('--shared',required=True)
    first.add_argument('--output',required=True);first.add_argument('--verification',required=True)
    more=sub.add_parser('add');more.add_argument('--manifest',required=True);more.add_argument('--package',required=True)
    more.add_argument('--report',required=True);more.add_argument('--verification',required=True);more.add_argument('--label',required=True)
    shared=sub.add_parser('shared');shared.add_argument('--manifest',required=True);shared.add_argument('--shared',required=True);shared.add_argument('--version',required=True)
    a=p.parse_args()
    if a.action=='prepare':print(json.dumps(prepare(a.plugin,a.shared,a.output,verification=a.verification),ensure_ascii=False,indent=2))
    elif a.action=='add':add_verified(a.manifest,a.package,a.report,a.verification,a.label)
    else:update_shared(a.manifest,a.shared,a.version)
