"""Read-only build environment discovery and explicit dependency installation."""
from pathlib import Path
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
import manager_core as core
import engine_discovery


def source_info(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > core.MAX_DOWNLOAD:
        raise ValueError('请选择插件编译源码 ZIP。')
    with zipfile.ZipFile(path) as z:
        names = core.zip_members(z)
        prefix = 'XHNodeChinese/'
        required = ('XHNodeChinese.uplugin', 'Tools/build-config.json', 'Tools/build_bridge.py',
                    'Tools/msvc_toolchain.py', 'Source/SlateBridge/Bridge.cpp', 'Source/SlateBridge/ModuleIndex.cpp')
        if not all(prefix + n in names for n in required):
            raise ValueError('需要 0.2.16-source-r2 或更新的源码包；安装包不能用于编译。')
        config = json.loads(z.read(prefix + 'Tools/build-config.json'))
        if config.get('compiler_selection') != 'ubt_response_file':
            raise ValueError('源码包未包含自动编译器适配，请使用新版授权源码包。')
        descriptor = json.loads(z.read(prefix + 'XHNodeChinese.uplugin'))
        # Read header requirements as data. Never import/execute code from a ZIP while detecting.
        tree = ast.parse(z.read(prefix + 'Tools/build_bridge.py').decode('utf-8-sig'))
        headers = []
        for node in ast.walk(tree):
            if isinstance(node, ast.For) and isinstance(node.target, ast.Name) and node.target.id == 'relative':
                try: value = ast.literal_eval(node.iter)
                except (ValueError, TypeError): continue
                if isinstance(value, (list, tuple)):
                    headers = [str(core.safe_relative(v)) for v in value if isinstance(v, str)]
        if not headers:
            raise ValueError('源码包缺少可检查的 SDK 头文件要求。')
    return dict(path=str(path.resolve()), version=descriptor['VersionName'], headers=headers)


def discover_source(saved, base, state, output):
    candidates = [Path(saved)] if saved else []
    for folder in (Path(state)/'source-packages', Path(state)/'authorized-source', Path(base)/'source-packages', Path(base), Path(output)):
        candidates.extend(sorted(folder.glob('*source*.zip'), key=lambda p:p.stat().st_mtime, reverse=True)[:20])
    for path in candidates:
        try: return source_info(path)
        except (OSError, ValueError, KeyError, zipfile.BadZipFile): pass
    return None


def remember_source(path, state):
    info = source_info(path)
    dest = Path(state)/'source-packages'/('XHNodeChinese-'+info['version']+'-source-'+core.digest(path)[:12]+'.zip')
    if not dest.exists(): core.atomic(dest, Path(path).read_bytes())
    return str(dest)


def obtain_source(feed_location, base, state, log=print):
    """Use a hash-verified release source archive, with a bundled offline fallback."""
    errors=[]
    for location in dict.fromkeys((str(feed_location),str(Path(base)/'release/manifest.json'))):
        try:
            feed=core.load_feed(location,Path(state)/'cache',allow_cached=True)
            item=feed.get('source')
            if not item:raise ValueError('更新清单没有编译源码包')
            log('下载并校验编译源码：'+item['version'])
            archive=core.fetch(item,Path(state)/'cache')
            return remember_source(archive,state)
        except (OSError,ValueError,KeyError) as error:errors.append(str(error))
    raise ValueError('未能取得编译源码。请检查网络后点“继续自动安装”，或在高级设置中选择已下载的源码 ZIP。\n'+'\n'.join(errors))


def python_candidates(engine, saved=''):
    candidates = [saved]
    if not getattr(sys, 'frozen', False): candidates.append(sys.executable)
    candidates += [str(Path(engine)/'Binaries/ThirdParty/Python3/Win64'/p) for p in ('python.exe','python3.exe')]
    candidates += [shutil.which('python.exe') or '', shutil.which('python3.exe') or '']
    for folder in (Path(os.environ.get('LOCALAPPDATA',''))/'Programs/Python', Path('C:/')):
        candidates += [str(p) for p in folder.glob('Python*/python.exe')]
    try:
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(hive, r'Software\Python\PythonCore') as key:
                    for i in range(winreg.QueryInfoKey(key)[0]):
                        name=winreg.EnumKey(key,i)
                        try:
                            with winreg.OpenKey(key,name+r'\InstallPath') as child:
                                candidates.append(str(Path(winreg.QueryValue(child,''))/'python.exe'))
                        except OSError: pass
            except OSError: pass
    except ImportError: pass
    return list(dict.fromkeys(p for p in candidates if p and 'windowsapps' not in p.lower()))


def find_python(engine, saved=''):
    for path in python_candidates(engine,saved):
        if not Path(path).is_file(): continue
        try:
            result=subprocess.run([path,'-I','-c','import sys,json,struct; print(json.dumps([list(sys.version_info[:2]),struct.calcsize("P")]))'],
                                  capture_output=True, timeout=5, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            version,bits=json.loads(result.stdout)
            if result.returncode==0 and version>=[3,9] and bits==8: return path
        except (OSError,ValueError,subprocess.TimeoutExpired): pass
    return ''


def sdk_policy(engine):
    try:return core.json_read(Path(engine)/'Config/Windows/Windows_SDK.json')
    except (OSError,ValueError):return {}


def supported_toolset(version, policy):
    version=core.version_tuple(version)
    if version<core.version_tuple(policy.get('MinimumVisualCppVersion','0')):return False
    for banned in policy.get('BannedVisualCppVersions',[]):
        if '-' in banned:
            low,high=banned.split('-',1)
            if core.version_tuple(low)<=version<=core.version_tuple(high):return False
    return True


def compiler_file_version(path, fallback):
    """Servicing updates can change cl.exe while retaining the MSVC family folder."""
    if os.name!='nt':return fallback
    try:
        import ctypes
        api=ctypes.windll.version;handle=ctypes.c_ulong()
        size=api.GetFileVersionInfoSizeW(str(path),ctypes.byref(handle))
        if not size:return fallback
        data=ctypes.create_string_buffer(size)
        if not api.GetFileVersionInfoW(str(path),0,size,data):return fallback
        pointer=ctypes.c_void_p();length=ctypes.c_uint()
        if not api.VerQueryValueW(data,'\\',ctypes.byref(pointer),ctypes.byref(length)) or length.value<52:return fallback
        fixed=ctypes.cast(pointer,ctypes.POINTER(ctypes.c_uint32*13)).contents
        major=fixed[2]>>16;minor=fixed[2]&65535;build=fixed[3]>>16
        if 19<=major<=29:return f'{major-5}.{minor}.{build}'
    except (OSError,ValueError,AttributeError):pass
    return fallback


def find_vcvars(saved='', engine=''):
    candidates=[Path(saved)] if saved else []
    vswhere=Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))/'Microsoft Visual Studio/Installer/vswhere.exe'
    if vswhere.is_file():
        try:
            result=subprocess.run([str(vswhere),'-all','-products','*','-property','installationPath'],capture_output=True,
                                  timeout=8,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            candidates += [Path(p)/'VC/Auxiliary/Build/vcvars64.bat' for p in result.stdout.decode('utf-8-sig').splitlines() if p.strip()]
        except (OSError,subprocess.TimeoutExpired): pass
    for base in ('C:/Program Files (x86)/Microsoft Visual Studio','C:/Program Files/Microsoft Visual Studio'):
        candidates += list(Path(base).glob('*/*/VC/Auxiliary/Build/vcvars64.bat'))
    found=[];policy=sdk_policy(engine)
    for path in dict.fromkeys(candidates):
        if not path.is_file():continue
        for p in (path.parents[2]/'Tools/MSVC').glob('*'):
            compiler=p/'bin/Hostx64/x64/cl.exe'
            if compiler.is_file() and (p/'bin/Hostx64/x64/link.exe').is_file():
                actual=compiler_file_version(compiler,p.name)
                if supported_toolset(actual,policy):found.append((core.version_tuple(actual),str(path)))
    return max(found,default=((),''))[1]


def find_windows_sdk(engine):
    roots=[Path('C:/Program Files (x86)/Windows Kits/10')]
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'SOFTWARE\Microsoft\Windows Kits\Installed Roots') as key:
            roots.insert(0,Path(winreg.QueryValueEx(key,'KitsRoot10')[0]))
    except (ImportError,OSError):pass
    policy=sdk_policy(engine)
    for root in roots:
        for lib in sorted((root/'Lib').glob('*'),reverse=True):
            version=core.version_tuple(lib.name)
            if not core.version_tuple(policy.get('MinVersion','0'))<=version<=core.version_tuple(policy.get('MaxVersion','999')):continue
            if all((root/path).is_file() for path in (f'Lib/{lib.name}/um/x64/kernel32.lib',f'Lib/{lib.name}/ucrt/x64/ucrt.lib',f'Include/{lib.name}/um/Windows.h')):
                return str(root/'Include'/lib.name)
    return ''


def sdk_problem(target, sdk, headers):
    try:
        target=core.engine_path(target);sdk=core.engine_path(sdk)
        v=core.json_read(target/'Build/Build.version');other=core.json_read(sdk/'Build/Build.version')
        if any(v[k]!=other[k] for k in ('MajorVersion','MinorVersion','PatchVersion')):
            return 'SDK 的 UE 版本与目标引擎不一致'
        for name in ('Build/BatchFiles/RunUAT.bat','Build/BatchFiles/Build.bat','Binaries/DotNET/UnrealBuildTool/UnrealBuildTool.dll'):
            if not (sdk/name).is_file(): return '缺少 '+name
        modules=('Core','CoreUObject','Slate','SlateCore','ApplicationCore','InputCore','RenderCore','RHI','TraceLog','Engine','UnrealEd','GraphEditor','Projects')
        paths=[f'Intermediate/Build/Win64/x64/UnrealEditor/Development/{m}/UnrealEditor-{m}.lib' for m in modules]
        paths += [f'Plugins/FX/Niagara/Intermediate/Build/Win64/x64/UnrealEditor/Development/{m}/UnrealEditor-{m}.lib'
                  for m in ('NiagaraEditor','NiagaraEditorWidgets','Niagara','NiagaraCore')]
        for name in paths:
            if not (sdk/name).is_file(): return '缺少引擎开发库：'+name
        for name in headers:
            if (target/name).read_bytes() != (sdk/name).read_bytes(): return 'SDK 头文件与目标引擎不匹配：'+name
    except (OSError,ValueError,KeyError) as error: return str(error)
    return ''


def inspect(engine, source, sdk, vcvars, python, output, base, state):
    target=core.engine_path(engine)
    source=discover_source(source,base,state,output)
    candidates=[str(target),sdk]+[p for _,p,_ in engine_discovery.registered_engines()]
    found='';problems=[]
    if source:
        for candidate in dict.fromkeys(p for p in candidates if p):
            error=sdk_problem(target,candidate,source['headers'])
            if not error: found=str(core.engine_path(candidate));break
            problems.append(candidate+'：'+error)
    py=find_python(target,python);vc=find_vcvars(vcvars,target);windows_sdk=find_windows_sdk(target)
    issues=[]
    if not source: issues.append(dict(kind='source',title='自动下载编译源码',detail='从发布清单获取源码并校验，保存在本机供后续复用。'))
    elif not found: issues.append(dict(kind='sdk',title='选择完整的同版本 UE',detail='目标引擎缺少编译依赖，请选择完整 UE 的根目录或 Engine 目录。'+('\n'+problems[0] if problems else '')))
    if not vc or not windows_sdk: issues.append(dict(kind='vcvars',title='安装 C++ 编译环境',detail='缺少当前 UE 支持的 C++ 工具或 Windows SDK。下载微软官方安装器，自动选好 C++ 工具与推荐组件。可能需要 Windows 管理员授权。'))
    if not py: issues.append(dict(kind='python',title='安装 Python',detail='未找到可用的 64 位 Python 3.9+。可自动下载 Python 官方安装器并为当前用户安装。'))
    return dict(engine=str(target),source=source['path'] if source else '',sdk=found,vcvars=vc,python=py,windows_sdk=windows_sdk,
                output=str(Path(output).resolve()),compiler_version='auto',issues=issues,diagnostics=problems)


def install_dependency(kind, state, log=print):
    specs={
        'vcvars':('https://aka.ms/vs/17/release/vs_BuildTools.exe','vs_BuildTools.exe','Microsoft Corporation',
                  ['--add','Microsoft.VisualStudio.Workload.VCTools','--includeRecommended','--passive','--norestart','--wait']),
        'python':('https://www.python.org/ftp/python/3.13.16/python-3.13.16-amd64.exe','python-3.13.16-amd64.exe','Python Software Foundation',
                  ['/passive','InstallAllUsers=0','PrependPath=0','Include_test=0','Include_launcher=0'])}
    if kind not in specs: raise ValueError('不支持自动安装的环境。')
    url,name,publisher,args=specs[kind]
    dest=Path(state)/'installers'/name
    log('下载官方安装器：'+url);core.download(url,dest)
    env=dict(os.environ,XH_INSTALLER=str(dest))
    script='$s=Get-AuthenticodeSignature -LiteralPath $env:XH_INSTALLER; [pscustomobject]@{status=[string]$s.Status;subject=$s.SignerCertificate.Subject}|ConvertTo-Json -Compress'
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],env=env,
                          capture_output=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    signature=json.loads(result.stdout.decode('utf-8-sig'))
    if result.returncode or signature.get('status')!='Valid' or not re.search(r'(?:^|,\s*)(?:CN|O)='+re.escape(publisher)+r'(?=,|$)',signature.get('subject','')):
        raise ValueError('安装器数字签名校验失败，已停止。请从官方页面安装后重试检测。')
    log('签名已验证。安装中；如 Windows 请求授权，请在系统弹窗中确认。下载组件可能需要数分钟，请保持联网。')
    if kind=='vcvars':
        # Only elevate the signed Microsoft installer; manager/project writes stay unelevated.
        env['XH_INSTALLER_ARGS']=subprocess.list2cmdline(args)
        script=("try {$p=Start-Process -FilePath $env:XH_INSTALLER -ArgumentList $env:XH_INSTALLER_ARGS "
                "-Verb RunAs -WindowStyle Hidden -Wait -PassThru -ErrorAction Stop; exit $p.ExitCode} "
                "catch {exit 1223}")
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],env=env,
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    else:result=subprocess.run([str(dest)]+args,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode in (1223,1602):raise ValueError('已取消环境安装。重新点击“自动适配并安装”可继续；需要允许微软安装器的 Windows 授权。')
    if result.returncode in (1618,1001):raise ValueError('已有其他安装器正在运行。等它完成后再点“继续自动安装”。')
    if result.returncode not in (0,3010): raise ValueError('环境安装未完成（退出码 '+str(result.returncode)+'）。可点“微软官方下载”安装 C++ 桌面开发及 Windows SDK，然后继续自动安装。')
    return result.returncode
