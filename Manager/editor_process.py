"""Request normal editor shutdown only after the UI obtains explicit consent."""
import json
import os
from pathlib import Path
import re
import subprocess
import time

NAME_PATTERN=r'(?:UnrealEditor|UE4Editor)(?:-Cmd|-Win64-(?:Debug|DebugGame|Development|Shipping))?'


def _powershell(script,targets=None):
    executable=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    env=dict(os.environ)
    if targets is not None:env['XH_MANAGER_CLOSE_TARGETS']=json.dumps(targets)
    prefix="$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); "
    result=subprocess.run([str(executable),'-NoLogo','-NoProfile','-NonInteractive','-Command',prefix+script],
                          env=env,capture_output=True,encoding='utf-8',errors='replace',
                          timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise RuntimeError('无法检查或请求关闭虚幻编辑器，请手动关闭后重试。\n'+result.stderr.strip()[-800:])
    return json.loads(result.stdout.strip() or '[]')


def list_editors():
    if os.name!='nt':return []
    script="""
$items=@(Get-Process | Where-Object { $_.ProcessName -match '^(?:UnrealEditor|UE4Editor)(?:-Cmd|-Win64-(?:Debug|DebugGame|Development|Shipping))?$' } | ForEach-Object {
    $started=''; try { $started=$_.StartTime.ToUniversalTime().Ticks.ToString() } catch {}
    [pscustomobject]@{pid=$_.Id; name=$_.ProcessName; title=$_.MainWindowTitle; started=$started; window=($_.MainWindowHandle -ne 0)}
}); ConvertTo-Json -InputObject $items -Compress
"""
    return _powershell(script)


def request_close(targets):
    """Send CloseMainWindow to the exact process identities the user approved."""
    if not targets:return
    for item in targets:
        if (not isinstance(item.get('pid'),int) or item['pid']<=0 or
            not re.fullmatch(NAME_PATTERN,item.get('name',''),re.I) or
            not re.fullmatch(r'\d+',item.get('started',''))):
            raise RuntimeError('无法确认虚幻进程身份，请手动关闭后重试。')
        if not item.get('window'):
            raise RuntimeError('部分虚幻进程没有可关闭的窗口，请先手动退出：'+item['name'])
    script="""
$targets=ConvertFrom-Json $env:XH_MANAGER_CLOSE_TARGETS
$results=@(foreach ($target in $targets) {
    $editor=Get-Process -Id $target.pid -ErrorAction SilentlyContinue
    if (-not $editor) { continue }
    if ($editor.ProcessName -ne $target.name -or $editor.StartTime.ToUniversalTime().Ticks.ToString() -ne $target.started) {
        throw 'The editor process changed. Please check again.'
    }
    [pscustomobject]@{pid=$editor.Id; sent=$editor.CloseMainWindow()}
}); ConvertTo-Json -InputObject $results -Compress
"""
    results=_powershell(script,targets)
    if any(not item['sent'] for item in results):
        raise RuntimeError('无法请求关闭部分虚幻窗口。请手动保存并关闭 UE 后重试；尚未更新工程文件。')


def close_and_wait(targets,log=lambda _:None,timeout=90):
    request_close(targets)
    log('已请求正常关闭 UE；如有保存提示，请在 UE 中处理。不会强制结束进程。')
    deadline=time.monotonic()+timeout
    approved={(item['pid'],item['started']) for item in targets}
    while True:
        remaining=list_editors()
        if not remaining:return
        if any((item['pid'],item['started']) not in approved for item in remaining):
            raise RuntimeError('检测到新的虚幻进程，更新已暂停。请关闭 UE 后重新安装。')
        if time.monotonic()>=deadline:
            raise RuntimeError('UE 尚未退出，更新已暂停。请处理 UE 保存提示或手动关闭后重试；尚未更新工程文件。')
        time.sleep(.5)
