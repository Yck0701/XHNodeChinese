"""Read-only project-to-engine discovery. Never changes EngineAssociation."""
import os
from pathlib import Path
import re
import manager_core as core


def registered_engines():
    """Collect launcher and custom registrations, without scanning whole drives."""
    records=[]
    try:
        import winreg
    except ImportError:
        return records
    for view in (winreg.KEY_WOW64_64KEY,winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Epic Games\Unreal Engine\Builds',0,winreg.KEY_READ|view) as key:
                for i in range(winreg.QueryInfoKey(key)[1]):
                    name,path,kind=winreg.EnumValue(key,i)
                    if kind in (winreg.REG_SZ,winreg.REG_EXPAND_SZ):
                        records.append((name,os.path.expandvars(path),'自定义引擎登记'))
        except OSError:pass
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'SOFTWARE\EpicGames\Unreal Engine',0,winreg.KEY_READ|view) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    name=winreg.EnumKey(key,i)
                    try:
                        with winreg.OpenKey(key,name) as child:
                            path=winreg.QueryValueEx(child,'InstalledDirectory')[0]
                            if isinstance(path,str):records.append((name,path,'官方引擎登记'))
                    except OSError:pass
        except OSError:pass
    data=Path(os.environ.get('PROGRAMDATA',r'C:\ProgramData'))/'Epic/UnrealEngineLauncher/LauncherInstalled.dat'
    try:
        if data.stat().st_size<=2*1024*1024:
            for item in core.json_read(data).get('InstallationList',[]):
                name=item.get('AppName','')
                if name.startswith('UE_'):
                    records.append((name[3:],item.get('InstallLocation',''),'Epic 安装记录'))
    except (OSError,ValueError,TypeError,AttributeError):pass
    return records


def discover(project,registrations=None):
    folder=core.project_path(project)
    descriptor=Path(project).expanduser().resolve()
    if descriptor.is_dir():
        files=list(folder.glob('*.uproject'))
        if len(files)!=1:raise ValueError('目录内有多个工程，请选择具体的 .uproject 文件。')
        descriptor=files[0]
    if descriptor.stat().st_size>2*1024*1024:raise ValueError('工程描述文件过大。')
    data=core.json_read(descriptor)
    if not isinstance(data,dict):raise ValueError('工程描述格式无效。')
    association=data.get('EngineAssociation','')
    if not isinstance(association,str):raise ValueError('工程引擎关联格式无效。')
    association=association.strip()
    found={}
    def add(path,reason,linked=True):
        if not path:return
        try:
            engine=core.engine_path(path)
            if not (engine/'Binaries/Win64/UnrealEditor.exe').is_file():return
            version=core.json_read(engine/'Build/Build.version')
            version='.'.join(str(int(version[k])) for k in ('MajorVersion','MinorVersion','PatchVersion'))
            key=str(engine).casefold()
            item=found.get(key)
            if item:
                item['linked']|=linked
                if reason not in item['reasons']:item['reasons'].append(reason)
            else:found[key]=dict(path=str(engine),version=version,reasons=[reason],linked=linked)
        except (OSError,ValueError,KeyError,TypeError):pass
    records=registered_engines() if registrations is None else registrations
    normal=lambda value:value.strip().strip('{}').casefold()
    for name,path,reason in records:
        if association and normal(name)==normal(association):add(path,'工程关联 · '+reason)
    # EngineAssociation may be a relative or absolute path for portable projects.
    if association and (Path(association).is_absolute() or '/' in association or '\\' in association):
        add(folder/association,'工程关联路径')
    for path in (folder/'UE',folder,folder/'UnrealEngine'):
        add(path,'工程附带引擎')
    # Empty associations are used for projects underneath an engine source tree.
    if not association:
        for parent in list(folder.parents)[:6]:
            if parent==parent.parent:break
            add(parent,'工程上级引擎')
    linked=[item for item in found.values() if item['linked']]
    if not linked:
        for name,path,reason in records:add(path,reason+'（需要手动确认）',False)
    choices=linked or list(found.values())
    choices.sort(key=lambda item:(item['version'],item['path']))
    selected=choices[0] if len(linked)==1 else None
    return dict(project=str(descriptor),association=association,candidates=choices,selected=selected)
