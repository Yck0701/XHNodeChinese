"""Portable plugin manager. No third-party runtime dependencies."""
from __future__ import annotations
import csv
from contextlib import contextmanager
from functools import wraps
from datetime import datetime
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
import time
from urllib.parse import urljoin, urlparse
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import uuid
import zipfile

SOURCE_REPOSITORY = 'https://github.com/Yck0701/XHNodeChinese'
REPOSITORY = 'https://github.com/Yck0701/XHNodeChinese-new'
DEFAULT_FEED = REPOSITORY + '/releases/latest/download/manifest.json'
VERSION = '1.0.17'
PRODUCT_NAME = '虚幻翻译插件'
DOCS_URL = 'https://365.kdocs.cn/l/cpi4ASG5Izsi?source=wiki'
PROTECTED = ('Plugins/XHNodeChinese/Dictionaries/User.csv', 'Saved/XHNodeChinese/LongText.csv')
SHARED_FILES = tuple('Plugins/XHNodeChinese/Dictionaries/'+n for n in
                     ('Shared.csv','SharedLongText.csv','SharedVersion.json'))
ENGINE_FILES = tuple('Binaries/Win64/UnrealEditor-' + m + '.dll' for m in
    ('Core','CoreUObject','Slate','SlateCore','ApplicationCore','InputCore','Engine','GraphEditor')) + tuple(
    'Plugins/FX/Niagara/Binaries/Win64/UnrealEditor-' + m + '.dll' for m in
    ('NiagaraEditor','NiagaraEditorWidgets','Niagara','NiagaraCore'))
MAX_DOWNLOAD = 256 * 1024 * 1024
MAX_EXPANDED = 512 * 1024 * 1024


def version_tuple(value):
    """Return a comparable tuple for dotted release versions."""
    parts = re.findall(r'\d+', str(value or ''))
    values = tuple(int(part) for part in parts)
    return values + (0,)*max(0,4-len(values))


def newer_version(candidate, current=VERSION):
    """Whether candidate is newer than current using numeric dotted versions."""
    return version_tuple(candidate) > version_tuple(current)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temp.open('xb') as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def write_json(path, value):
    atomic(path, json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8'))


def json_read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def engine_path(path):
    p = Path(path).expanduser().resolve()
    if (p/'Engine/Build/Build.version').is_file(): p = p/'Engine'
    if not (p/'Build/Build.version').is_file(): raise ValueError('请选择含 Engine/Build/Build.version 的引擎目录。')
    return p


def engine_info(path, log=lambda _: None):
    p = engine_path(path); v = json_read(p/'Build/Build.version')
    fingerprints = {}
    for name in ENGINE_FILES:
        file = p/name
        if not file.is_file(): raise ValueError('引擎不完整，缺少：' + name)
        log('校验引擎：' + file.name)
        fingerprints[name] = digest(file)
    return {'version': '.'.join(str(v[k]) for k in ('MajorVersion','MinorVersion','PatchVersion')),
            'changelist': v.get('Changelist',0), 'sha256': fingerprints}


def cached_engine_info(path, cache, log=lambda _: None):
    """Fast startup comparison only; install always hashes the engine again."""
    root=engine_path(path)
    signature=[(str(root/n), (root/n).stat().st_size, (root/n).stat().st_mtime_ns)
               for n in ('Build/Build.version',)+ENGINE_FILES]
    key=hashlib.sha256(str(root).casefold().encode()).hexdigest()
    file=Path(cache)/('engine-'+key+'.json')
    try:
        cached=json_read(file)
        if cached['signature']==[list(v) for v in signature]:return cached['info']
    except (OSError,ValueError,KeyError,TypeError):pass
    info=engine_info(root,log)
    write_json(file,dict(signature=signature,info=info))
    return info


def project_path(path):
    raw = Path(os.path.abspath(Path(path).expanduser()))
    # Inspect the user-selected path before resolve() erases link information.
    for part in (raw, *raw.parents):
        if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
            raise ValueError('工程路径不能是符号链接或目录联接，请选择真实工程目录。')
    p = raw.resolve()
    if p.suffix.lower() == '.uproject' and p.is_file(): return p.parent
    if p.is_dir() and any(p.glob('*.uproject')): return p
    raise ValueError('请选择工程的 .uproject 文件或其所在文件夹。')


def ensure_closed():
    if os.name != 'nt': return
    output = subprocess.run(['tasklist.exe','/FO','CSV','/NH'],
                            capture_output=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW).stdout
    if re.search(rb'"(?:UnrealEditor|UE4Editor)(?:-Cmd|-Win64-(?:Debug|DebugGame|Development|Shipping))?\.exe"',output,re.I):
        raise RuntimeError('请先保存并关闭 UE 编辑器，再安装、替换或恢复文件。备份操作无需关闭。')


def feed_location(value):
    value = str(value).strip()
    if re.fullmatch(r'https://github\.com/[^/]+/[^/]+/?', value):
        return value.rstrip('/') + '/releases/latest/download/manifest.json'
    return value


def download(location, destination, expected=None, limit=MAX_DOWNLOAD):
    destination=Path(destination); location=str(location)
    temp=destination.with_name(destination.name+'.download-'+uuid.uuid4().hex)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        if location.startswith(('http://','https://')):
            if urlparse(location).scheme != 'https': raise ValueError('在线更新地址必须使用 HTTPS。')
            stream=urlopen(Request(location, headers={'User-Agent':'XHPluginManager/'+VERSION}), timeout=45)
            if urlparse(stream.geturl()).scheme != 'https':
                stream.close(); raise ValueError('拒绝不安全的下载重定向。')
        else: stream=Path(location).open('rb')
        total=0; h=hashlib.sha256()
        with stream, temp.open('xb') as out:
            while True:
                chunk=stream.read(1024*1024)
                if not chunk: break
                total+=len(chunk)
                if total>limit: raise ValueError('下载超过允许大小。')
                out.write(chunk); h.update(chunk)
        if expected and h.hexdigest()!=expected: raise ValueError('下载校验失败，文件未安装，请重新下载。')
        os.replace(temp,destination)
    finally: temp.unlink(missing_ok=True)
    return destination


def load_feed(location, cache, allow_cached=False):
    location=feed_location(location)
    file=Path(cache)/('feed-'+hashlib.sha256(str(location).encode()).hexdigest()+'.json')
    try:
        with tempfile.TemporaryDirectory(prefix='xh-feed-') as tmp:
            downloaded=download(location,Path(tmp)/'manifest.json',limit=2*1024*1024)
            feed=parse_feed(json_read(downloaded),location)
            atomic(file,downloaded.read_bytes())
        return feed
    except (OSError,ValueError) as exc:
        if allow_cached and file.is_file():
            feed=parse_feed(json_read(file),location)
            feed['_cached']=True;feed['_check_error']=str(exc)
            return feed
        if isinstance(exc,HTTPError) and exc.code==404:
            raise ValueError('尚未找到发布清单，请使用随包离线版本。') from exc
        raise


def parse_feed(feed, location):
    if feed.get('schema')!=1 or not isinstance(feed.get('plugins'),list): raise ValueError('更新清单格式不支持。')
    for item in feed['plugins']+[feed.get('shared',{})]+[feed[k] for k in ('source','manager') if feed.get(k)]:
        if not re.fullmatch('[0-9a-f]{64}',item.get('sha256','')): raise ValueError('更新清单缺少有效的 SHA-256。')
        if not item.get('url'): raise ValueError('更新清单缺少下载地址。')
        if str(location).startswith('https://'):
            item['_location']=urljoin(location,item['url'])
            if not item['_location'].startswith('https://'): raise ValueError('清单包含非 HTTPS 地址。')
        else:
            if urlparse(item['url']).scheme: raise ValueError('离线清单只能引用同目录文件。')
            rel=safe_relative(item['url'])
            base=Path(location).resolve().parent
            candidate=(base/rel).resolve()
            if not candidate.is_relative_to(base): raise ValueError('离线包路径越界。')
            item['_location']=str(candidate)
    return feed


def fetch(item, cache):
    return download(item['_location'],Path(cache)/(item['sha256']+'.zip'),item['sha256'])


def prepare_manager_update(item, cache):
    """Stage a verified new portable version; never overwrite a running EXE."""
    if not re.fullmatch(r'\d+(?:\.\d+){1,3}',str(item.get('version',''))):raise ValueError('管理器版本号无效。')
    archive=fetch(item,cache)
    with zipfile.ZipFile(archive) as z:
        members=zip_members(z)
        executable=next((n for n in ('虚幻翻译插件.exe','XHPluginManager.exe') if 'XHPluginManager/'+n in members),None)
        if not executable:raise ValueError('管理器包缺少程序。')
        if any(PurePosixPath(n).parts[0]!='XHPluginManager' for n in members):raise ValueError('管理器包包含无关目录。')
        dest=Path(cache)/'versions'/(item['version']+'-'+uuid.uuid4().hex[:8])
        no_links(dest);dest.mkdir(parents=True)
        for name,info in members.items():
            p=dest.joinpath(*PurePosixPath(name).parts);p.parent.mkdir(parents=True,exist_ok=True)
            with z.open(info) as source,p.open('xb') as output:shutil.copyfileobj(source,output)
    return dest/'XHPluginManager'/executable


def update_summary(feed, project='', selected=None):
    manager=feed.get('manager',{}).get('version',feed.get('manager_version',''))
    result={'manager':('可更新至 '+manager) if newer_version(manager) else '当前 v'+VERSION,
            'plugin':'请选择引擎并检查兼容性','shared':'可安装 '+str(feed['shared'].get('version','')),
            'manager_update':newer_version(manager),'shared_update':True}
    root=None
    if project:
        try:root=project_path(project)
        except ValueError:pass
    if selected:
        current=''
        if root:
            try:current=json_read(root/'Plugins/XHNodeChinese/XHNodeChinese.uplugin').get('VersionName','')
            except (OSError,ValueError):pass
        result['plugin']=('可更新 '+current+' → '+selected['version']) if current and newer_version(selected['version'],current) else (
            '已安装 v'+current if current else '可安装 v'+selected['version'])
    if root:
        try:
            meta=json_read(root/SHARED_FILES[2])
            valid=all(digest(root/SHARED_FILES[i])==meta['files'][name] for i,name in enumerate(('User.csv','LongText.csv')))
            if valid and meta.get('version')==feed['shared'].get('version') and meta.get('sha256')==feed['shared'].get('sha256'):
                result['shared']='已是最新 · '+meta['version'];result['shared_update']=False
            else:result['shared']='可更新 '+meta.get('version','未知')+' → '+feed['shared']['version']
        except (OSError,ValueError,KeyError,TypeError):pass
    return result


def available_updates(feed, project='', selected=None, summary=None):
    """Only offer verified updates relevant to this installation; never downgrade."""
    if feed.get('_cached'):return []
    summary=summary or update_summary(feed,project,selected)
    updates=[]
    manager=feed.get('manager')
    if manager and newer_version(manager.get('version','')):
        updates.append({'kind':'manager','label':'管理器','current':VERSION,'item':dict(manager)})
    if not project:return updates
    try:
        root=project_path(project)
        descriptor=json_read(root/'Plugins/XHNodeChinese/XHNodeChinese.uplugin')
    except (OSError,ValueError):return updates
    current=descriptor.get('VersionName','')
    if selected and selected.get('verified') is True and current and newer_version(selected['version'],current):
        updates.append({'kind':'plugin','label':'引擎插件','current':current,'item':dict(selected)})
    if descriptor.get('XHSharedDictionaryVersion',0)>=1 and summary.get('shared_update'):
        try:version=json_read(root/SHARED_FILES[2]).get('version','')
        except (OSError,ValueError):version=''
        item=feed['shared']
        if not version or version_tuple(item['version'])>=version_tuple(version):
            updates.append({'kind':'shared','label':'共享词库','current':version or '未安装','item':dict(item)})
    return updates


def matching(feed, info):
    return [p for p in feed['plugins'] if p.get('verified') is True and p.get('engine',{}).get('sha256')==info['sha256'] and
            p.get('engine',{}).get('version')==info['version']]


def safe_relative(name):
    if '\\' in name or ':' in name: raise ValueError('压缩包路径非法：'+name)
    path=PurePosixPath(name)
    if path.is_absolute() or not path.parts or '..' in path.parts: raise ValueError('压缩包路径越界：'+name)
    if any(part.rstrip(' .')!=part or part.upper().split('.')[0] in
           {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(10)),*(f'LPT{i}' for i in range(10))} for part in path.parts):
        raise ValueError('压缩包包含非法 Windows 文件名。')
    return path


def zip_members(z):
    result={}; total=0; names=set()
    for info in z.infolist():
        p=safe_relative(info.filename)
        key=str(p).casefold()
        if key in names: raise ValueError('压缩包有重复文件。')
        names.add(key)
        if (info.external_attr>>16)&0o170000==0o120000: raise ValueError('不允许压缩包符号链接。')
        total+=info.file_size
        if total>MAX_EXPANDED or len(names)>12000: raise ValueError('压缩包展开后过大。')
        if not info.is_dir(): result[str(p)]=info
    return result


def unpack_plugin(archive, dest):
    dest=Path(dest)
    with zipfile.ZipFile(archive) as z:
        members=zip_members(z)
        if 'XHNodeChinese/XHNodeChinese.uplugin' not in members: raise ValueError('不是有效的虚幻翻译插件包。')
        for name,info in members.items():
            p=PurePosixPath(name)
            if p.parts[0]!='XHNodeChinese': raise ValueError('插件包包含无关目录。')
            if any(part in ('Saved','Intermediate','__pycache__','.git') for part in p.parts):
                raise ValueError('插件包包含构建缓存或私人数据。')
            target=dest.joinpath(*p.parts[1:]); target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(info) as source,target.open('xb') as output: shutil.copyfileobj(source,output)
    return dest


def no_links(root):
    root=Path(root)
    for p in [root,*root.parents]:
        if p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()): raise ValueError('目标路径不能是符号链接或目录联接。')
    if root.is_dir():
        for p in root.rglob('*'):
            if p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()): raise ValueError('插件目录中存在链接，无法安全替换。')


def exclusive_update(fn):
    @wraps(fn)
    def run(project,*args,**kwargs):
        project=project_path(project)
        lock=project/'Saved/XHNodeChinese/UpdaterBackups/operation.lock'
        no_links(lock); lock.parent.mkdir(parents=True,exist_ok=True)
        with lock.open('a+b') as handle:
            handle.seek(0,2)
            if handle.tell()==0:handle.write(b'0');handle.flush()
            handle.seek(0)
            if os.name=='nt':
                import msvcrt
                try:msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
                except OSError as exc:raise RuntimeError('另一个更新器正在处理此工程，请稍后重试。') from exc
            try:return fn(project,*args,**kwargs)
            finally:
                if os.name=='nt':
                    handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
    return run


def backup(project):
    project=project_path(project)
    dest=project/'Saved/XHNodeChinese/UpdaterBackups'/('dictionary-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]+'.zip')
    no_links(dest.parent)
    dest.parent.mkdir(parents=True,exist_ok=True)
    temporary=dest.with_suffix('.tmp'); state={}
    try:
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as z:
            for name in PROTECTED:
                p=project/name; no_links(p)
                data=p.read_bytes() if p.exists() else None
                state[name]=None if data is None else hashlib.sha256(data).hexdigest()
                if data is not None: z.writestr(name,data)
            z.writestr('backup.json',json.dumps({'schema':1,'files':state},ensure_ascii=False))
        os.replace(temporary,dest)
    finally: temporary.unlink(missing_ok=True)
    return dest


def csv_validate(data):
    text=data.decode('utf-8-sig')
    rows=list(csv.reader(io.StringIO(text),strict=True))
    rows=[r for r in rows if r and not (len(r)==1 and r[0].startswith('#'))]
    if not rows or rows[0] not in (['Key','Value'],['Source','Translation','Namespace','Key','Category']):
        raise ValueError('共享词典表头无效。')
    width=len(rows[0]); seen=set()
    for r in rows[1:]:
        if len(r)!=width or not r[0].strip() or not r[1].strip() or '\x00' in ''.join(r): raise ValueError('共享词典存在空译文或错误行。')
        key=(r[0],*r[2:])
        if key in seen: raise ValueError('共享词典存在重复条目。')
        seen.add(key)
    return len(rows)-1


def shared_contents(archive):
    with zipfile.ZipFile(archive) as z:
        members=zip_members(z)
        if not {'User.csv','LongText.csv'}<=members.keys(): raise ValueError('共享包缺少词典或长文本。')
        if not set(members)<= {'User.csv','LongText.csv','curation-report.json','README.md'}: raise ValueError('共享包包含未知文件。')
        result={PROTECTED[0]:z.read('User.csv'),PROTECTED[1]:z.read('LongText.csv')}
        for data in result.values(): csv_validate(data)
        return result


@exclusive_update
def replace_files(project, contents):
    project=project_path(project); ensure_closed()
    if set(contents)!=set(PROTECTED): raise ValueError('不允许替换未知路径。')
    for name in PROTECTED: no_links(project/name)
    previous={name:(project/name).read_bytes() if (project/name).exists() else None for name in PROTECTED}
    saved=backup(project)
    try:
        for name,data in contents.items():
            if data is None: (project/name).unlink(missing_ok=True)
            else: atomic(project/name,data)
    except Exception:
        for name,data in previous.items():
            if data is None: (project/name).unlink(missing_ok=True)
            else: atomic(project/name,data)
        raise
    return saved


def replace_shared(project, archive):
    return replace_files(project,shared_contents(archive))


@exclusive_update
def replace_defaults(project, contents):
    """Replace only bundled shared files, keeping both personal CSVs byte-identical."""
    project=project_path(project);ensure_closed()
    if set(contents)!=set(SHARED_FILES):raise ValueError('共享基础词典路径无效。')
    descriptor=json_read(project/'Plugins/XHNodeChinese/XHNodeChinese.uplugin')
    if descriptor.get('XHSharedDictionaryVersion',0)<1:raise ValueError('请先更新插件，再安装共享基础词典。旧版仍可使用词典替换功能。')
    for name in SHARED_FILES:no_links(project/name)
    previous={name:(project/name).read_bytes() if (project/name).exists() else None for name in SHARED_FILES}
    saved=project/'Saved/XHNodeChinese/UpdaterBackups'/('shared-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]+'.zip')
    no_links(saved);saved.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(saved,'x',zipfile.ZIP_DEFLATED) as z:
        hashes={}
        for name,data in previous.items():
            hashes[name]=hashlib.sha256(data).hexdigest() if data is not None else None
            if data is not None:z.writestr(name,data)
        z.writestr('backup.json',json.dumps({'schema':2,'files':hashes}))
    try:
        for name,data in contents.items():
            if data is None:(project/name).unlink(missing_ok=True)
            else:atomic(project/name,data)
    except Exception:
        for name,data in previous.items():
            if data is None:(project/name).unlink(missing_ok=True)
            else:atomic(project/name,data)
        raise
    return saved


def update_shared_defaults(project, archive, version):
    content=shared_contents(archive)
    files={name:content[p] for name,p in zip(('User.csv','LongText.csv'),PROTECTED)}
    meta={'version':version,'sha256':digest(archive),
          'files':{name:hashlib.sha256(data).hexdigest() for name,data in files.items()}}
    payload=dict(zip(SHARED_FILES,(files['User.csv'],files['LongText.csv'],json.dumps(meta,ensure_ascii=False).encode('utf-8'))))
    return replace_defaults(project,payload)


def restore(project, archive):
    with zipfile.ZipFile(archive) as z:
        members=zip_members(z)
        meta=json.loads(z.read('backup.json'))
        allowed=SHARED_FILES if meta.get('schema')==2 else PROTECTED
        if meta.get('schema') not in (1,2) or set(meta.get('files',{}))!=set(allowed): raise ValueError('不是有效的词典备份。')
        if set(members)-set(allowed)-{'backup.json'}: raise ValueError('备份中含未知文件。')
        contents={}
        for name,h in meta['files'].items():
            data=None if h is None else z.read(name)
            if data is not None and hashlib.sha256(data).hexdigest()!=h: raise ValueError('备份校验失败。')
            contents[name]=data
    return replace_defaults(project,contents) if meta['schema']==2 else replace_files(project,contents)


def verify_bridge(plugin, info):
    p=Path(plugin)/'Binaries/Win64'; m=json_read(p/'bridge-manifest.json')
    if m.get('engine_sha256')!=info['sha256']: raise ValueError('包内引擎指纹不匹配，拒绝安装。')
    name=m.get('bridge_file','')
    if not re.fullmatch(r'XHSlateBridge[0-9]*\.dll',name): raise ValueError('动态组件名称无效。')
    if digest(p/name)!=m.get('bridge_sha256'): raise ValueError('包内动态组件校验失败。')


def replace_retry(source, destination, log=lambda _: None):
    """Retry transient Windows sharing/access errors without weakening permissions."""
    for attempt in range(4):
        try:
            os.replace(source,destination)
            return
        except OSError as error:
            if getattr(error,'winerror',None) not in (5,32,33) or attempt==3:raise
            log('Windows 暂时无法移动 '+str(source)+'，正在重试（'+str(attempt+1)+'/3）…')
            time.sleep((.25,.5,1.0)[attempt])


@contextmanager
def replacement_access(paths):
    """Preflight delete access without changing ACLs; rollback covers later races."""
    handles=[]
    if os.name!='nt':
        yield
        return
    import ctypes
    from ctypes import wintypes as w
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateFileW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,ctypes.c_void_p,w.DWORD,w.DWORD,w.HANDLE]
    kernel.CreateFileW.restype=w.HANDLE;kernel.CloseHandle.argtypes=[w.HANDLE]
    try:
        for path in paths:
            handle=kernel.CreateFileW(str(path),0x10000,7,None,3,0x02000000,None)
            if handle==ctypes.c_void_p(-1).value:
                error=ctypes.WinError(ctypes.get_last_error())
                raise RuntimeError('文件被占用或没有替换权限，原插件未修改。请关闭使用此文件的程序后重试：\n'
                                   +str(path)+'\n'+str(error)) from error
            handles.append(handle)
    finally:
        for handle in handles:kernel.CloseHandle(handle)
    # MoveFileEx cannot overwrite a destination with our own delete handle open.
    yield


def install_files(target, stage, old, saved, recovery, log):
    """Keep a Windows-held root directory while replacing files transactionally."""
    no_links(target)
    existing={p.relative_to(target):p for p in target.rglob('*') if p.is_file()}
    incoming={p.relative_to(stage):p for p in stage.rglob('*') if p.is_file()}
    original={name:digest(p) for name,p in existing.items()}
    changed=sorted((name for name in existing.keys()|incoming.keys()
                    if name not in original or name not in incoming or original[name]!=digest(incoming[name])),
                   key=lambda p:(p.name=='XHNodeChinese.uplugin',p.as_posix()))
    for name in changed:
        destination=target/name
        if destination.is_dir() or any(p.is_file() for p in destination.parents if p!=target):
            raise RuntimeError('插件路径类型冲突，原插件未修改：'+str(destination))
    # An unchanged DLL need not be touched. Changed/removed files must all permit
    # replacement before the first write; a real file lock is never bypassed.
    with replacement_access([existing[n] for n in changed if n in existing]):
        shutil.copytree(target,old)
        if original!={p.relative_to(old):digest(p) for p in old.rglob('*') if p.is_file()}:
            raise RuntimeError('旧插件备份校验失败，原插件未修改。备份：'+str(old))
        log('旧插件已完整复制并校验：'+str(old))
        details={'mode':'files','target':str(target),'old_plugin':str(old),'staged_plugin':str(stage),
                 'dictionary_backup':str(saved),'planned_files':[n.as_posix() for n in changed]}
        write_json(recovery,details)
        touched=[];created=[]
        try:
            for name in changed:
                destination=target/name
                if name in incoming:
                    missing=[];parent=destination.parent
                    while not parent.exists():missing.append(parent);parent=parent.parent
                    for directory in reversed(missing):directory.mkdir();created.append(directory)
                    replace_retry(incoming[name],destination,log)
                else:destination.unlink()
                touched.append(name)
        except BaseException as error:
            failures=[]
            for name in reversed(touched):
                try:
                    if name in existing:atomic(target/name,(old/name).read_bytes())
                    else:(target/name).unlink(missing_ok=True)
                except OSError as rollback_error:failures.append(str(target/name)+': '+str(rollback_error))
            for directory in reversed(created):
                try:directory.rmdir()
                except OSError:pass
            if failures:
                details.update(error=str(error),rollback_errors=failures)
                try:write_json(recovery,details)
                except OSError as record_error:log('恢复记录更新失败：'+str(record_error))
                raise RuntimeError('逐文件安装失败，部分文件未能自动恢复。请先恢复旧插件后再打开 UE。\n'
                                   '完整备份：'+str(old)+'\n恢复记录：'+str(recovery)) from error
            recovery.unlink(missing_ok=True)
            raise RuntimeError('逐文件安装失败，已恢复原插件。完整备份：'+str(old)+'\n系统原因：'+str(error)) from error
        recovery.unlink(missing_ok=True)
        log('已逐文件更新 '+str(len(changed))+' 项；原插件目录保留。')


@exclusive_update
def install(project, archive, info, log=lambda _: None):
    project=project_path(project); ensure_closed()
    target=project/'Plugins/XHNodeChinese'; no_links(target)
    target.parent.mkdir(exist_ok=True)
    recovery=project/'Saved/XHNodeChinese/UpdaterBackups/install-recovery.json'
    no_links(recovery)
    if recovery.exists():
        raise RuntimeError('上次安装尚未恢复，请先按此记录恢复旧插件：'+str(recovery))
    saved=backup(project)
    log('个人词典和长文本已备份：'+str(saved))
    # Keep staging and the complete old plugin outside Plugins. A failed rollback
    # must never be erased by TemporaryDirectory cleanup or discovered by UE.
    stage=Path(tempfile.mkdtemp(prefix='install-stage-',dir=saved.parent))
    old=saved.parent/('plugin-'+saved.stem)
    moved=False;finished=False;keep_stage=False
    try:
        unpack_plugin(archive,stage)
        verify_bridge(stage,info)
        # Plugin update never replaces the user's dictionary implicitly.
        personal=target/'Dictionaries/User.csv'
        if personal.is_file(): atomic(stage/'Dictionaries/User.csv',personal.read_bytes())
        # Installing an older/offline plugin must not downgrade a newer shared pack.
        try:
            old_shared=json_read(target/'Dictionaries/SharedVersion.json')
            new_shared=json_read(stage/'Dictionaries/SharedVersion.json')
            if newer_version(old_shared['version'],new_shared['version']):
                for name in ('Shared.csv','SharedLongText.csv','SharedVersion.json'):
                    atomic(stage/'Dictionaries'/name,(target/'Dictionaries'/name).read_bytes())
        except (OSError,ValueError,KeyError):pass
        ensure_closed()
        write_json(recovery,{'target':str(target),'old_plugin':str(old),'staged_plugin':str(stage),
                             'dictionary_backup':str(saved),'state':'prepared'})
        if target.exists():
            try:
                replace_retry(target,old,log)
                moved=True
                log('旧插件已完整备份：'+str(old))
            except OSError as error:
                if getattr(error,'winerror',None) in (5,32,33) and target.is_dir() and not old.exists():
                    log('整个目录无法移动，改为完整备份后逐文件更新。')
                    # Remove the directory-swap journal. The file transaction
                    # writes its own durable plan before changing any files.
                    recovery.unlink(missing_ok=True)
                    try:install_files(target,stage,old,saved,recovery,log)
                    except BaseException:
                        keep_stage=recovery.exists()
                        raise
                    finished=True
                    log('插件安装完成；个人词典和长文本已保留。')
                    return saved
                raise RuntimeError('无法移动旧插件，原插件未替换。请关闭使用插件文件的程序，并检查此目录的修改权限后重试。\n'
                                   +str(target)+'\n词典备份：'+str(saved)+'\n系统原因：'+str(error)) from error
        try:
            replace_retry(stage,target,log)
        except OSError as error:
            if moved:
                try:
                    replace_retry(old,target,log)
                    moved=False
                except OSError as rollback_error:
                    keep_stage=True
                    details={'target':str(target),'old_plugin':str(old),'staged_plugin':str(stage),
                             'dictionary_backup':str(saved),'error':str(error),'rollback_error':str(rollback_error)}
                    try:write_json(recovery,details)
                    except OSError as record_error:log('恢复记录写入失败：'+str(record_error))
                    raise RuntimeError('安装失败，自动恢复也被 Windows 阻止。完整旧插件已保留，请先恢复后再打开 UE。\n'
                                       '旧插件：'+str(old)+'\n恢复到：'+str(target)+'\n恢复记录：'+str(recovery)
                                       +'\n系统原因：'+str(rollback_error)) from error
                raise RuntimeError('安装失败，已恢复原插件。词典备份：'+str(saved)+'\n系统原因：'+str(error)) from error
            raise RuntimeError('未能安装插件。请检查文件占用和目录修改权限后重试。\n'+str(error)) from error
        log('插件安装完成；个人词典和长文本已保留。')
        finished=True
        return saved
    finally:
        keep_stage=keep_stage or (moved and not finished)
        if not keep_stage:
            try:recovery.unlink(missing_ok=True)
            except OSError as error:log('恢复记录清理失败：'+str(recovery)+'；'+str(error))
        if stage.exists() and not keep_stage:
            try:shutil.rmtree(stage)
            except OSError as error:log('暂存文件稍后可清理：'+str(stage)+'；'+str(error))


def zip_plugin(plugin, dest):
    plugin=Path(plugin); dest=Path(dest); dest.parent.mkdir(parents=True,exist_ok=True)
    tmp=dest.with_suffix('.zip.tmp')
    m=json_read(plugin/'Binaries/Win64/bridge-manifest.json')
    with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(plugin.rglob('*')):
            rel=p.relative_to(plugin)
            if not p.is_file() or any(s in ('Saved','Intermediate','__pycache__','.git') for s in rel.parts): continue
            if p.name.startswith('XHSlateBridge') and p.suffix=='.dll' and p.name!=m['bridge_file']: continue
            if str(rel.as_posix())=='Dictionaries/User.csv': continue
            z.write(p,'XHNodeChinese/'+rel.as_posix())
        z.writestr('XHNodeChinese/Dictionaries/User.csv','Key,Value\n')
    os.replace(tmp,dest)
    return dest


def target_documentation(plugin,info):
    plugin=Path(plugin)
    target='UE '+info['version']+' / CL '+str(info.get('changelist',0))
    p=plugin/'README.md'
    if p.is_file():
        lines=p.read_text(encoding='utf-8').splitlines()
        lines=[('**引擎版本：**本包为 **'+target+'** 编译，必须匹配同一引擎构建。请通过配套管理器校验；不能仅按版本号强行安装。')
               if line.startswith('**引擎版本：**') else line for line in lines]
        atomic(p,('\n'.join(lines)+'\n').encode('utf-8'))
    p=plugin/'ADVANCED.md'
    if p.is_file():
        text=p.read_text(encoding='utf-8').replace('本包的动态显示组件针对当前定制 **UE 5.8.3** 构建。','本包的动态显示组件针对 **'+target+'** 构建。')
        atomic(p,text.encode('utf-8'))
    write_json(plugin/'BUILD_INFO.json',{'engine':info,'note':'Compatibility is gated by engine DLL fingerprints.'})


def run_logged(args, cwd, log):
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    env=os.environ.copy(); env['PYTHONIOENCODING']='utf-8'; env['PYTHONUTF8']='1'
    with subprocess.Popen([str(a) for a in args],cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                          encoding='utf-8',errors='replace',env=env,creationflags=flags) as process:
        for line in process.stdout: log(line.rstrip())
        if process.wait(): raise RuntimeError('构建命令失败，请查看上方日志。')


def compile_package(source, engine, sdk, vcvars, python, output, log=print, compiler_version='auto',cancel_event=None):
    import build_process
    engine=engine_path(engine); sdk=engine_path(sdk); output=Path(output).resolve()
    for p in (engine,sdk,Path(vcvars),output,Path(python)):
        if re.search(r'[\r\n"%&|<>!^]',str(p)): raise ValueError('编译路径不能包含引号或命令行特殊字符。')
    if not Path(vcvars).is_file(): raise ValueError('请选择 Visual Studio 的 vcvars64.bat。')
    if not Path(python).is_file(): raise ValueError('编译需要 Python 3.9 或更新版本，请选择 python.exe。')
    if compiler_version!='auto' and not re.fullmatch(r'\d+\.\d+(?:\.\d+)?',compiler_version): raise ValueError('MSVC 版本应为 auto 或已安装的工具集版本。')
    if not (sdk/'Build/BatchFiles/RunUAT.bat').is_file(): raise ValueError('SDK 缺少 RunUAT.bat。')
    info=engine_info(engine,log); output.mkdir(parents=True,exist_ok=True)
    # Unique workspace keeps source distribution and installed plugin untouched.
    build=output/('build-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
    stage=unpack_plugin(source,build/'XHNodeChinese')
    if not (stage/'Tools/build_bridge.py').is_file() or not (stage/'Source/SlateBridge/Bridge.cpp').is_file():
        raise ValueError('请选择维护者提供的源码包；公开安装包不包含编译源码。')
    config=stage/'Tools/build-config.json'
    if not config.is_file() or json_read(config).get('schema',0)<2:
        raise ValueError('源码包中的构建工具过旧，可能卡在 UBA。请使用 0.2.14-source-r2 或更新的授权源码包；本次尚未启动编译。')
    if compiler_version=='auto' and json_read(config).get('compiler_selection')!='ubt_response_file':
        raise ValueError('自动适配需要 0.2.16-source-r2 或更新的授权源码包。请重新选择源码包后继续。')
    for file in (stage/'Binaries/Win64').glob('*'): file.unlink()
    log('开始构建动态组件；其他 UE 版本可能需要适配 C++ 源码。')
    build_process.run([python,stage/'Tools/build_bridge.py','--engine',engine,'--sdk',sdk,'--vcvars',vcvars,
                '--compiler-version',compiler_version],stage,log,build/'build.log',cancel_event)
    verify_bridge(stage,info)
    log('为目标引擎重新生成语言资源。')
    build_process.run([python,stage/'Tools/build.py','--engine',engine],stage,log,build/'build.log',cancel_event,display_limit=20)
    target_documentation(stage,info)
    fingerprint=hashlib.sha256(json.dumps(info['sha256'],sort_keys=True).encode()).hexdigest()[:12]
    plugin_version=json_read(stage/'XHNodeChinese.uplugin')['VersionName']
    if not re.fullmatch(r'\d+(?:\.\d+){1,3}',plugin_version):raise ValueError('插件版本号无效。')
    dest=output/('XHNodeChinese-'+plugin_version+'-UE'+info['version']+'-'+fingerprint+'-UNVERIFIED.zip')
    zip_plugin(stage,dest)
    report={'schema':1,'engine':info,'package':dest.name,'sha256':digest(dest),
            'verified':False,'note':'编译成功不代表兼容，必须在该目标引擎的独立工程验证后才能发布。'}
    write_json(dest.with_suffix('.json'),report)
    if cancel_event is not None and cancel_event.is_set():log('取消请求到达时安装包已生成，已保留输出。')
    log('编译完成：'+str(dest)); log(report['note'])
    return dest
