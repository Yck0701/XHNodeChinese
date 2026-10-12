"""Cloud availability and browser-based GitHub contributions; no client publishing credentials."""
import json
from pathlib import Path
import tempfile
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request,urlopen
import zipfile

import manager_core as core
import contribution_protocol as protocol

REPO='Yck0701/XHNodeChinese-new'
CATALOG='https://raw.githubusercontent.com/'+REPO+'/main/catalog/official-engines.json'
ISSUES='https://github.com/'+REPO+'/issues/new'


def read_json(url,limit=2*1024*1024):
    request=Request(url,headers={'User-Agent':'XHPluginManager/'+core.VERSION,'Accept':'application/vnd.github+json'})
    with urlopen(request,timeout=30) as response:
        data=response.read(limit+1)
        if len(data)>limit:raise ValueError('云端回复过大。')
    return json.loads(data)


def check(info,plugin_version,cache):
    """Fetch public metadata first; send no local fingerprint in a URL for unknown builds."""
    info=protocol.engine_identity(info);protocol.version(plugin_version)
    catalog=read_json(CATALOG)
    kind=protocol.official_kind(info,catalog)
    feed=core.load_feed(core.DEFAULT_FEED,cache)
    released=[p for p in core.matching(feed,info) if core.version_tuple(p['version'])>=core.version_tuple(plugin_version)]
    result=dict(kind=kind,catalog=catalog,engine=info,plugin_version=plugin_version,
                state='available' if released else 'missing',item=released[0] if released else None,
                tag=protocol.release_tag(info,plugin_version,kind))
    if released:return result
    # Download one public index for all users. Custom fingerprints remain on the device until consent.
    index=read_json('https://raw.githubusercontent.com/'+REPO+'/main/catalog/community-builds.json')
    if index.get('schema')!=1 or not isinstance(index.get('builds'),dict):raise ValueError('云端投稿目录无效。')
    pending=index['builds'].get(result['tag'])
    if pending:
        if pending.get('state') not in ('pending_review','approved','rejected'):raise ValueError('云端收录状态无效。')
        result.update(state=pending['state'],submission=pending)
    return result


def source_version(source):
    with zipfile.ZipFile(source) as z:
        core.zip_members(z)
        if z.getinfo('XHNodeChinese/XHNodeChinese.uplugin').file_size>65536:raise ValueError('插件描述文件过大。')
        return protocol.version(json.loads(z.read('XHNodeChinese/XHNodeChinese.uplugin'))['VersionName'])


def prepare(package,result,output,custom_consent=False):
    """Only share the two native plugin components, reconstructed manifests and safe metadata."""
    if result['state'] not in ('missing','rejected'):raise ValueError('云端已存在此构建，无需重复投稿。')
    kind=protocol.official_kind(result['engine'],result['catalog'])
    if kind=='custom' and custom_consent is not True:raise ValueError('尚未同意公开分享定制构建。')
    package=Path(package);report=core.json_read(package.with_suffix('.json'))
    if report['sha256']!=core.digest(package):raise ValueError('编译包与构建报告不匹配。')
    if protocol.engine_identity(report['engine'])!=result['engine']:raise ValueError('编译包属于另一引擎。')
    files={}
    with zipfile.ZipFile(package) as z:
        core.zip_members(z)
        if source_version(package)!=result['plugin_version']:raise ValueError('插件版本不匹配。')
        base='XHNodeChinese/Binaries/Win64/'
        for i,name in enumerate(protocol.MANIFESTS):
            if z.getinfo(base+name).file_size>16384:raise ValueError('编译清单过大。')
            original=json.loads(z.read(base+name))
            manifest={key:original[key] for key in ('engine_sha256','bridge_file','bridge_sha256')}
            prefix='XHSlateBridge' if i==0 else 'XHModuleIndex'
            import re
            if not re.fullmatch(prefix+r'\d+\.dll',str(manifest['bridge_file'])):raise ValueError('组件名称无效。')
            files['Binaries/Win64/'+name]=protocol.canonical(manifest)
            dll=base+manifest['bridge_file']
            if z.getinfo(dll).file_size>protocol.MAX_EXPANDED//2:raise ValueError('组件过大。')
            files['Binaries/Win64/'+manifest['bridge_file']]=z.read(dll)
    meta=dict(schema=1,engine=result['engine'],platform='Win64',plugin_version=result['plugin_version'],
              kind=kind,custom_consent=bool(custom_consent),fingerprint=protocol.fingerprint(result['engine']),
              files={n:protocol.sha(data) for n,data in files.items()})
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    name='XH-contribution-'+kind+'-'+meta['plugin_version']+'-'+meta['fingerprint'][:16]+'.zip'
    dest=output/name
    with tempfile.TemporaryDirectory(dir=output) as tmp:
        staging=Path(tmp)/name
        with zipfile.ZipFile(staging,'w',zipfile.ZIP_DEFLATED) as z:
            for relative,data in files.items():z.writestr(relative,data)
            z.writestr('contribution.json',protocol.canonical(meta))
        protocol.validate_bundle(staging,result['catalog'])
        core.atomic(dest,staging.read_bytes())
    body=issue_body(meta,core.digest(dest))
    core.atomic(dest.with_suffix('.txt'),body.encode('utf-8'))
    return dest,ISSUES+'?'+urlencode({'title':'[构建投稿] '+('官方' if kind=='official' else '定制／未认证')+' UE '+meta['engine']['version']+' / 插件 '+meta['plugin_version'],
                                    'body':body})


def issue_body(meta,archive_hash):
    return ('虚幻翻译插件编译结果投稿（等待维护者验证，不能直接安装）\n\n'
            '请将管理器生成的 XH-contribution-*.zip 拖到下面，等待上传完成，再点击 Submit new issue。\n\n'
            '投稿类型：'+('已登记官方指纹' if meta['kind']=='official' else '定制／未认证构建，独立存放')+'\n'
            'UE '+meta['engine']['version']+' / Win64 / 插件 '+meta['plugin_version']+'\n\n'
            '<!-- XH-CONTRIBUTION-SHA256:'+archive_hash+' -->\n'
            + ('- [x] 我同意公开分享此定制或未认证构建的插件组件及引擎指纹。\n' if meta['kind']=='custom' else '')+
            '\n附件：\n')
