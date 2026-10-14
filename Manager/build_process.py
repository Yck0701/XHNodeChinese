"""Cancelable build supervision; only the spawned build process tree can be stopped."""
import os
from pathlib import Path
import queue
import subprocess
import threading
import time


def stop_tree(process):
    if process.poll() is not None:return
    if os.name=='nt':
        subprocess.run(['taskkill.exe','/PID',str(process.pid),'/T','/F'],capture_output=True,
                       timeout=20,creationflags=subprocess.CREATE_NO_WINDOW)
    else:process.kill()
    try:process.wait(timeout=10)
    except subprocess.TimeoutExpired:raise RuntimeError('编译进程尚未退出，请查看日志。')


def run(args,cwd,log,log_path,cancel=None,timeout=1200,idle_timeout=300,heartbeat=20,display_limit=None):
    env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUTF8='1',PYTHONUNBUFFERED='1')
    path=Path(log_path);path.parent.mkdir(parents=True,exist_ok=True)
    started=time.monotonic();last_output=started;last_heartbeat=started
    events=queue.Queue()
    with path.open('a',encoding='utf-8') as saved:
        displayed=0
        def emit(text,force=False):
            nonlocal displayed
            saved.write(text+'\n');saved.flush()
            if force or display_limit is None or displayed<display_limit:log(text)
            elif displayed==display_limit:log('详细输出已写入构建日志，界面仅显示摘要：'+str(path))
            if not force:displayed+=1
        if cancel is not None and cancel.is_set():raise RuntimeError('编译已取消。')
        process=subprocess.Popen([str(a) for a in args],cwd=cwd,env=env,stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        emit('启动编译子进程 PID '+str(process.pid)+'；完整日志：'+str(path))
        def read():
            try:
                for line in iter(process.stdout.readline,b''):events.put(line)
            finally:events.put(None)
        reader=threading.Thread(target=read,daemon=True);reader.start();eof=False
        try:
            while True:
                now=time.monotonic()
                if cancel is not None and cancel.is_set():raise RuntimeError('编译已取消；保留工作目录和日志。')
                if now-started>=timeout:raise RuntimeError('编译超过总时限，已停止本次编译。工作目录和日志已保留。')
                if now-last_output>=idle_timeout:raise RuntimeError('编译连续 '+str(round(idle_timeout/60))+' 分钟没有日志输出，已停止等待；请查看编译日志。')
                try:
                    line=events.get(timeout=min(.2,max(.01,timeout-(now-started))))
                    if line is None:eof=True
                    else:last_output=time.monotonic();emit(line.decode('utf-8',errors='replace').rstrip())
                except queue.Empty:pass
                if eof and process.poll() is not None:break
                if now-last_heartbeat>=heartbeat:
                    emit('编译进行中 · 已用 '+str(int(now-started))+' 秒 · 最近输出 '+str(int(now-last_output))+' 秒前',True);last_heartbeat=now
            if process.returncode:raise RuntimeError('编译子进程退出码 '+str(process.returncode)+'；日志：'+str(path))
            emit('本阶段完成，用时 '+format(time.monotonic()-started,'.1f')+' 秒。',True)
        except BaseException:
            stop_tree(process)
            raise
        finally:
            reader.join(timeout=2)
            if not reader.is_alive():process.stdout.close()
