"""Find reusable installed, bundled, cached and locally compiled plugins before building."""
import hashlib
import json
from pathlib import Path
import zipfile
import manager_core as c
import community


def package_info(path,engine,minimum):
    with zipfile.ZipFile(path) as z:
        names=c.zip_members(z);root='XHNodeChinese/';binary=root+'Binaries/Win64/'
        def read(name):
            if names[name].file_size>65536:raise ValueError('包元数据过大。')
            return json.loads(z.read(name))
        descriptor=read(root+'XHNodeChinese.uplugin');version=descriptor['VersionName']
        community.protocol.version(version)
        if c.version_tuple(version)<c.version_tuple(minimum):return None
        manifests=['bridge-manifest.json']
        if descriptor.get('XHModuleIndexVersion',0)>=1:manifests.append('module-index-manifest.json')
        for name in manifests:
            manifest=read(binary+name)
            if manifest['engine_sha256']!=engine['sha256']:return None
            dll=manifest['bridge_file']
            if '/' in dll or '\\' in dll or ':' in dll:raise ValueError('组件名称无效。')
            h=hashlib.sha256()
            with z.open(binary+dll) as stream:
                for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
            if h.hexdigest()!=manifest['bridge_sha256']:raise ValueError('本地组件校验失败。')
        return version


def local_candidates(engine,minimum,output,cache,bundled,project='',extra_feed=None,log=lambda _:None):
    cache=Path(cache);bundled=Path(bundled);output=Path(output)
    feeds=[];trusted={};paths={}
    manifest_paths=list(cache.glob('feed-*.json'))[:100]
    if (bundled/'manifest.json').is_file():manifest_paths.append(bundled/'manifest.json')
    for file in manifest_paths:
        try:
            feed=c.json_read(file)
            if feed.get('schema')!=1:continue
            feeds.append((feed,file.parent))
        except (OSError,ValueError):continue
    if extra_feed:feeds.append((extra_feed,cache))
    for feed,folder in feeds:
        for item in c.matching(feed,engine):
            if c.version_tuple(item['version'])<c.version_tuple(minimum):continue
            trusted[item['sha256']]=item
            for file in (cache/(item['sha256']+'.zip'),folder/Path(item['url']).name,output/Path(item['url']).name):
                if file.is_file():paths[str(file.resolve())]=file
    for file in output.glob('*.zip'):
        if len(paths)>=200:break
        if file.with_suffix('.json').is_file():paths[str(file.resolve())]=file
    found=[]
    for file in paths.values():
        try:
            if file.stat().st_size>c.MAX_DOWNLOAD:continue
            version=package_info(file,engine,minimum)
            if not version:continue
            sha=c.digest(file);item=trusted.get(sha)
            report=None
            if item is None:
                report=c.json_read(file.with_suffix('.json'))
                if report['sha256']!=sha or report['engine']['sha256']!=engine['sha256'] or report['engine']['version']!=engine['version']:continue
            found.append(dict(kind='package',path=str(file),version=version,sha256=sha,
                filename=Path(item['url']).name if item else file.name,
                verified=item is not None,label='已验证本地安装包' if item else '本地测试包（未经发布验证）'))
        except (OSError,ValueError,KeyError,TypeError,zipfile.BadZipFile) as error:
            log('跳过无效本地包：'+file.name+'（'+type(error).__name__+'）')
    if project:
        try:
            plugin=c.project_path(project)/'Plugins/XHNodeChinese'
            descriptor=c.json_read(plugin/'XHNodeChinese.uplugin');version=descriptor['VersionName']
            if c.version_tuple(version)>=c.version_tuple(minimum):
                c.verify_bridge(plugin,engine)
                if descriptor.get('XHModuleIndexVersion',0)>=1:
                    manifest=c.json_read(plugin/'Binaries/Win64/module-index-manifest.json')
                    name=manifest['bridge_file']
                    if '/' in name or '\\' in name or ':' in name:raise ValueError('组件名称无效。')
                    if manifest['engine_sha256']!=engine['sha256'] or c.digest(plugin/'Binaries/Win64'/name)!=manifest['bridge_sha256']:
                        raise ValueError('本地索引组件不完整。')
                found.append(dict(kind='installed',path=str(plugin),version=version,verified=False,label='当前工程已安装的匹配版本'))
        except (OSError,ValueError,KeyError,TypeError,RuntimeError):pass
    found.sort(key=lambda item:(c.version_tuple(item['version']),item.get('verified',False),item['kind']=='installed'),reverse=True)
    return found


def probe(engine,source,output,cache,bundled,project='',feed=c.DEFAULT_FEED,log=lambda _:None):
    info=c.engine_info(engine,log)
    minimum=community.source_version(source) if source and Path(source).is_file() else '0'
    local=local_candidates(info,minimum,output,cache,bundled,project,log=log)
    if local:
        log('已找到满足目标版本的本地包，跳过重复下载与编译。')
        return dict(engine=info,minimum=minimum,local=local,cloud=None,cloud_error='',cloud_checked=False)
    cloud=None;error='';remote_feed=None
    try:
        remote_feed=c.load_feed(feed,cache)
        matched=[p for p in c.matching(remote_feed,info) if c.version_tuple(p['version'])>=c.version_tuple(minimum)]
        matched.sort(key=lambda p:c.version_tuple(p['version']),reverse=True)
        cloud=matched[0] if matched else None
        # A fresh feed can authenticate archives downloaded before any previous feed was cached.
        local=local_candidates(info,minimum,output,cache,bundled,project,extra_feed=remote_feed,log=log)
    except (OSError,ValueError,KeyError,TypeError) as exc:error=str(exc)
    contribution=None
    if not local and not cloud and not error and minimum!='0':
        try:
            contribution=community.check(info,minimum,cache)
            if contribution['state']=='available':cloud=contribution['item']
        except (OSError,ValueError,KeyError,TypeError) as exc:
            error='投稿状态检查失败：'+str(exc)
    return dict(engine=info,minimum=minimum,local=local,cloud=cloud,cloud_error=error,contribution=contribution)


def preferred(result):
    local=result['local'][0] if result['local'] else None
    remote=result['cloud']
    if remote and (not local or c.newer_version(remote['version'],local['version']) or
                   (local['kind']=='package' and not local['verified'])):
        return 'cloud',remote
    if local:return 'local',local
    if remote:return 'cloud',remote
    return None,None


def install_choice(local,remote=None,download_only=False):
    """Use the newest usable archive, or keep an equally/newer installed plugin."""
    packages=sorted((item for item in local if item['kind']=='package'),
                    key=lambda item:(c.version_tuple(item['version']),item.get('verified',False)),reverse=True)
    item=packages[0] if packages else None
    origin='local' if item else None
    if remote and (not item or c.newer_version(remote['version'],item['version']) or
                   (c.version_tuple(remote['version'])==c.version_tuple(item['version']) and not item.get('verified'))):
        origin,item='cloud',remote
    installed=max((item for item in local if item['kind']=='installed'),
                  key=lambda item:c.version_tuple(item['version']),default=None)
    if not download_only and installed and (not item or not c.newer_version(item['version'],installed['version'])):
        return 'installed',installed
    return origin,item


def reuse(item,output):
    """Revalidate immediately before returning or copying an existing local archive."""
    source=Path(item['path'])
    if item['kind']=='installed':return source
    if c.digest(source)!=item['sha256']:raise ValueError('本地包在检查后发生变化，请重新检测。')
    target=Path(output)/Path(item.get('filename',source.name)).name
    if source.resolve()==target.resolve():return source
    if target.exists():
        if c.digest(target)==item['sha256']:return target
        raise ValueError('输出目录已有不同内容的同名文件，未覆盖。')
    c.atomic(target,source.read_bytes())
    return target
