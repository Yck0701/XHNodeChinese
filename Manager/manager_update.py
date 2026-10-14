"""Replace a portable manager in place after its process has exited."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import os
import shutil
import subprocess
import sys
import time
import uuid
import manager_core as core

EXECUTABLES=('虚幻翻译插件.exe','XHPluginManager.exe')
OWNED=EXECUTABLES+('_internal','release','README.md','PUBLISHING.md','RELEASE_NOTES.md')


def validate(stage,target,executable):
    stage=Path(os.path.abspath(stage));target=Path(os.path.abspath(target))
    core.no_links(stage)
    # Do not traverse user source packages or other unrelated folders in target.
    for parent in (target,*target.parents):
        if parent.is_symlink() or (hasattr(parent,'is_junction') and parent.is_junction()):
            raise ValueError('管理器目录不能是链接或目录联接。')
    stage=stage.resolve();target=target.resolve()
    if target==Path(target.anchor) or stage.is_relative_to(target) or target.is_relative_to(stage):
        raise ValueError('更新缓存和安装目录必须相互独立。')
    if executable not in EXECUTABLES or not (target/executable).is_file() or not (target/'_internal').is_dir():
        raise ValueError('请选择原管理器 EXE 所在的完整目录。')
    if not all((stage/n).is_file() for n in EXECUTABLES) or not (stage/'_internal').is_dir():
        raise ValueError('新版包不完整，缺少程序入口或运行库。')
    for name in OWNED:core.no_links(target/name)
    return stage,target


def inventory(stage):
    files={}
    for name in OWNED:
        path=Path(stage)/name
        for file in (sorted(path.rglob('*')) if path.is_dir() else [path]):
            if file.is_file():files[file.relative_to(stage).as_posix()]=core.digest(file)
    return files


def prepare(stage,target,executable,state):
    stage,target=validate(stage,target,executable)
    version=core.json_read(stage/'release/manifest.json')['manager_version']
    try:installed=core.json_read(target/'release/manifest.json')['manager_version']
    except (OSError,ValueError,KeyError):installed='0'
    if core.newer_version(installed,version):raise ValueError('原目录版本更新，已阻止降级。')
    # Fail while the current application is still running if its folder isn't writable.
    probe=target/('.xh-write-test-'+uuid.uuid4().hex)
    try:
        with probe.open('xb') as f:f.write(b'')
    except OSError as error:
        raise OSError('原目录不可写，请以有权限的账号重新打开管理器：'+str(target)) from error
    finally:probe.unlink(missing_ok=True)
    folder=Path(state)/'manager-updates'/uuid.uuid4().hex
    core.no_links(folder);folder.mkdir(parents=True)
    plan=dict(schema=1,stage=str(stage),target=str(target),executable=executable,
              parent_pid=os.getpid(),original_sha256=core.digest(target/executable),
              version=version,files=inventory(stage))
    core.write_json(folder/'plan.json',plan)
    return folder/'plan.json'


def child_env():
    # A new PyInstaller process needs its own runtime, not the old bundle's DLLs.
    env=dict(os.environ,PYINSTALLER_RESET_ENVIRONMENT='1')
    return env


def launch_worker(plan):
    data=core.json_read(plan)
    return subprocess.Popen([str(Path(data['stage'])/EXECUTABLES[0]),'--apply-manager-update',str(plan)],
                            cwd=data['stage'],env=child_env(),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))


def replace_files(plan,record):
    _,target=validate(plan['stage'],plan['target'],plan['executable'])
    lock=target/'.xh-manager-update.lock'
    core.no_links(lock)
    with lock.open('a+b') as handle:
        handle.seek(0,2)
        if handle.tell()==0:handle.write(b'0');handle.flush()
        handle.seek(0)
        if os.name=='nt':
            import msvcrt
            try:msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as error:raise RuntimeError('另一个管理器更新正在执行，请稍后重试。') from error
        try:return _replace_files(plan,record)
        finally:
            if os.name=='nt':handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)


def _replace_files(plan,record):
    """Only manager-owned entries change; backups and a journal survive failure."""
    stage,target=validate(plan['stage'],plan['target'],plan['executable'])
    if inventory(stage)!=plan['files']:raise ValueError('新版暂存文件已变化，请重新下载。')
    if core.digest(target/plan['executable'])!=plan['original_sha256']:
        raise ValueError('原目录已被其他更新改变，请重新打开原目录的程序。')
    transaction=target/('.xh-update-'+uuid.uuid4().hex)
    fresh=transaction/'new';backup=transaction/'backup'
    fresh.mkdir(parents=True);backup.mkdir()
    journal=dict(status='preparing',target=str(target),version=plan['version'],backup=str(backup),moved=[],placed=[])
    core.write_json(record,journal)
    try:
        for name in OWNED:
            source=stage/name
            if source.is_dir():shutil.copytree(source,fresh/name)
            elif source.is_file():shutil.copy2(source,fresh/name)
        if inventory(fresh)!=plan['files']:raise ValueError('复制校验失败，原程序保持不变。')
        journal['status']='replacing';core.write_json(record,journal)
        for name in OWNED:
            if not (fresh/name).exists():continue
            if (target/name).exists():
                os.replace(target/name,backup/name);journal['moved'].append(name);core.write_json(record,journal)
            os.replace(fresh/name,target/name);journal['placed'].append(name);core.write_json(record,journal)
        if inventory(target)!=plan['files']:raise ValueError('原目录更新校验失败。')
        journal['status']='installed';core.write_json(record,journal)
    except Exception as error:
        failures=[]
        for name in reversed(journal['placed']):
            try:os.replace(target/name,fresh/name)
            except OSError as rollback:failures.append(str(rollback))
        for name in reversed(journal['moved']):
            try:os.replace(backup/name,target/name)
            except OSError as rollback:failures.append(str(rollback))
        journal.update(status='rollback_failed' if failures else 'rolled_back',error=str(error),rollback_errors=failures)
        core.write_json(record,journal)
        raise RuntimeError(('部分文件无法恢复，备份位于 '+str(backup) if failures else '更新未完成，原文件已保留或恢复。')+
                           '\n请关闭此目录其他管理器实例后重试。\n'+str(error)) from error
    return target/plan['executable']


def run_worker(path):
    path=Path(path).resolve();record=path.with_name('result.json');handle=None
    try:
        plan=core.json_read(path);validate(plan['stage'],plan['target'],plan['executable'])
        if Path(sys.executable).resolve().parent!=Path(plan['stage']).resolve():
            raise ValueError('更新助手必须从已校验的新版本缓存运行。')
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD];kernel.WaitForSingleObject.restype=wintypes.DWORD
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        handle=kernel.OpenProcess(0x100000,False,plan['parent_pid'])
        if not handle:raise OSError('无法等待当前管理器退出，尚未替换文件。')
        core.write_json(path.with_name('ready.json'),dict(ready=True))
        if kernel.WaitForSingleObject(handle,90000)!=0:raise TimeoutError('当前管理器未退出，尚未替换文件。')
        kernel.CloseHandle(handle);handle=None
        exe=replace_files(plan,record)
        subprocess.Popen([str(exe),'--update-result',str(record)],cwd=exe.parent,env=child_env())
    except Exception as error:
        # Keep transaction state if replacement already supplied detailed recovery info.
        try:result=core.json_read(record)
        except (OSError,ValueError):result={}
        result.update(error=str(error));core.write_json(record,result)
        if os.name=='nt':ctypes.windll.user32.MessageBoxW(None,str(error)+'\n记录：'+str(record),'管理器更新未完成',0x10)
        return 1
    finally:
        if handle:kernel.CloseHandle(handle)
    return 0
