"""XH plugin manager GUI and publisher CLI."""
import argparse
import json
import os
from pathlib import Path
import queue
import shutil
import sys
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser
import manager_core as core
import editor_process
import interface
import community
import build_preflight

BASE=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
STATE=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'XHPluginManager'


def find_vcvars():
    candidates=[]
    for base in ('C:/Program Files (x86)/Microsoft Visual Studio','C:/Program Files/Microsoft Visual Studio'):
        for p in Path(base).glob('*/*/VC/Auxiliary/Build/vcvars64.bat'):
            versions=[]
            for v in (p.parents[2]/'Tools/MSVC').glob('*'):
                if v.name.replace('.','').isdigit():versions.append(tuple(map(int,v.name.split('.'))))
            candidates.append((max(versions,default=(0,)),str(p)))
    return max(candidates,default=((0,),''))[1]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(core.PRODUCT_NAME+' · 安装、共享词典与编译')
        interface.configure(self)
        self.messages=queue.Queue(); self.busy=False; self.feed=None; self.feed_origin=''
        self.checking=False
        self.closing=False
        self.update_prompts=set()
        self.info=None; self.checked_engine=''; self.selected=None
        settings={}
        try: settings=core.json_read(STATE/'settings.json')
        except (OSError,ValueError): pass
        self.project=tk.StringVar(value=settings.get('project',''))
        self.engine=tk.StringVar(value=settings.get('engine',''))
        self.build_engine=tk.StringVar(value=settings.get('build_engine',settings.get('engine','')))
        self.feed_var=tk.StringVar(value=settings.get('feed',core.REPOSITORY))
        if core.feed_location(self.feed_var.get())==core.feed_location(core.SOURCE_REPOSITORY):
            self.feed_var.set(core.REPOSITORY)
        self.source_package=tk.StringVar(value=settings.get('source_package',''))
        self.sdk=tk.StringVar(value=settings.get('sdk',''))
        self.vcvars=tk.StringVar(value=settings.get('vcvars',find_vcvars()))
        python=shutil.which('python.exe') or ''
        if not getattr(sys,'frozen',False): python=sys.executable
        self.python=tk.StringVar(value=settings.get('python',python))
        self.msvc=tk.StringVar(value=settings.get('msvc','14.50'))
        self.out=tk.StringVar(value=settings.get('output',str(Path.home()/'Documents/XHBuilds')))
        self.auto_check=tk.BooleanVar(value=bool(settings.get('auto_check',True)))
        self.selection=tk.StringVar(value='both')
        self.status=tk.StringVar(value='先选择工程和引擎。已有用户可直接备份词典。')
        self.cloud_status=tk.StringVar(value='编译前检查云端；官方与定制投稿分区保存，审核通过后共享。')
        self.last_compiled=None
        self.build_cancel=None
        interface.build(self,core,BASE)
        self.protocol('WM_DELETE_WINDOW',self.close)
        if not self.closing:self.after(100,self.pump)
        if self.auto_check.get():
            self.after(450,self.startup_check)

    def path_row(self,parent,label,var,browse,label_width=13,**kw):
        row=ttk.Frame(parent);row.pack(fill='x',pady=3)
        ttk.Label(row,text=label,width=label_width).pack(side='left')
        ttk.Entry(row,textvariable=var).pack(side='left',fill='x',expand=True,padx=(0,8))
        ttk.Button(row,text=kw.get('button_text','选择…'),command=browse).pack(side='left')

    def choose_dir(self,var):
        p=filedialog.askdirectory(parent=self)
        if p:var.set(p)

    def choose_file(self,var,types):
        p=filedialog.askopenfilename(parent=self,filetypes=types)
        if p:var.set(p)

    def choose_project(self): self.choose_file(self.project,[('UE 工程','*.uproject')])
    def choose_feed(self): self.choose_file(self.feed_var,[('更新清单','manifest.json')])
    def use_bundled(self):
        path=BASE/'release/manifest.json'
        if not path.is_file():
            messagebox.showerror('缺少离线包','请完整解压便携包，保留 release 文件夹。',parent=self);return
        self.feed_var.set(str(path));self.check(True)
    def log(self,text): self.messages.put(('log',str(text)))
    def open_path(self,path):
        if Path(path).exists(): os.startfile(str(path))
        else: messagebox.showinfo('尚无文件','文件夹尚未创建：'+str(path),parent=self)

    def save_settings(self):
        core.write_json(STATE/'settings.json',dict(project=self.project.get(),engine=self.engine.get(),feed=self.feed_var.get(),
            sdk=self.sdk.get(),build_engine=self.build_engine.get(),vcvars=self.vcvars.get(),python=self.python.get(),msvc=self.msvc.get(),output=self.out.get(),source_package=self.source_package.get(),auto_check=self.auto_check.get()))

    def start(self,fn,done=lambda result:None,quiet=False):
        if self.busy:
            messagebox.showinfo('正在处理','请等待当前操作完成。',parent=self);return
        self.save_settings();self.busy=True;self.status.set('正在处理，请查看进度日志…');self.progress.start(12)
        def work():
            try: self.messages.put(('done',(done,fn())))
            except Exception as e:
                self.log('操作失败：'+traceback.format_exc())
                self.messages.put(('error',(str(e),quiet)))
        threading.Thread(target=work,daemon=False).start()

    def pump(self):
        while True:
            try:kind,value=self.messages.get_nowait()
            except queue.Empty:break
            if kind=='log':
                self.logbox.configure(state='normal');self.logbox.insert('end',value+'\n');self.logbox.see('end');self.logbox.configure(state='disabled')
                STATE.mkdir(parents=True,exist_ok=True)
                with (STATE/'manager.log').open('a',encoding='utf-8') as f:f.write(value+'\n')
            elif kind=='check_done':
                self.checking=False
                callback,result=value
                if not self.busy:callback(result)
            elif kind=='check_error':
                self.checking=False
                if not self.busy:self.status.set('自动检查未完成，可手动重试或使用离线包：'+value)
            else:
                self.busy=False;self.progress.stop()
                if self.build_cancel is not None:
                    self.build_cancel=None;self.cancel_build_button.configure(state='disabled')
                if kind=='error':
                    error,quiet=(value if isinstance(value,tuple) else (value,False))
                    self.status.set('操作未完成：'+error)
                    if not quiet: messagebox.showerror('操作未完成',error,parent=self)
                else:
                    self.status.set('操作完成。'); callback,result=value;callback(result)
        if not self.closing:self.after(100,self.pump)

    def startup_check(self):
        """Check in the background, then ask before downloading available updates."""
        if self.busy: return
        self.status.set('正在后台检查更新清单…')
        self.check(bool(self.engine.get()),automatic=True)

    def check(self,with_engine=True,automatic=False,notify=True):
        if self.checking:return
        source=self.feed_var.get();engine=self.engine.get();project=self.project.get()
        def task():
            self.log('读取更新清单：'+source)
            feed=core.load_feed(source,STATE/'cache',allow_cached=True)
            info=None;engine_error=''
            if with_engine and engine:
                try:info=core.cached_engine_info(engine,STATE/'cache',self.log)
                except Exception as error:engine_error=str(error)
            return feed,info,engine_error
        def done(result):
            if source!=self.feed_var.get() or engine!=self.engine.get() or project!=self.project.get():
                self.status.set('选择已改变，请重新检查更新。');return
            self.feed,self.info,engine_error=result;self.feed_origin=source;self.checked_engine=engine
            matched=core.matching(self.feed,self.info) if self.info else []
            self.selected=matched[0] if matched else None
            self.package_label.set(('找到匹配包：'+self.selected['label']) if self.selected else '没有匹配包，或尚未选择引擎。可以使用编译页生成测试包。')
            s=self.feed['shared'];self.shared_label.set('共享版本：'+s['version']+' · '+str(s.get('terms','?'))+' 条词典 / '+str(s.get('long_texts','?'))+' 段长文本')
            self.log(self.package_label.get())
            summary=core.update_summary(self.feed,project,self.selected)
            for key,var in self.card_vars.items():var.set(summary[key])
            self.manager_button.configure(state='normal' if summary['manager_update'] else 'disabled')
            prefix='离线缓存，尚未确认最新版本' if self.feed.get('_cached') else '检查完成'
            self.status.set(prefix+' · '+('引擎路径需检查：'+engine_error if engine_error else '工具、插件与共享词库状态已更新。'))
            if self.feed.get('_cached'):self.log('在线检查失败：'+self.feed['_check_error'])
            if notify:self.offer_updates(summary,automatic)
        if automatic:
            self.checking=True
            def work():
                try:self.messages.put(('check_done',(done,task())))
                except Exception as error:self.messages.put(('check_error',str(error)))
            threading.Thread(target=work,daemon=True).start()
        else:self.start(task,done)

    def offer_updates(self,summary,automatic=False):
        updates=core.available_updates(self.feed,self.project.get(),self.selected,summary)
        if not updates or self.busy or self.closing:return
        key=(self.feed_origin,self.project.get(),self.engine.get(),tuple((u['kind'],u['item']['version'],u['item']['sha256']) for u in updates))
        if automatic and key in self.update_prompts:return
        self.update_prompts.add(key)
        detail='\n'.join(u['label']+'：'+u['current']+' → '+u['item']['version'] for u in updates)
        if not messagebox.askyesno('发现新版本',detail+'\n\n是否下载以上更新？\n本步只下载，不关闭 UE，也不修改工程。',parent=self):return
        def task():
            results=[]
            for update in updates:
                self.log('下载并校验：'+update['label']+' '+update['item']['version'])
                path=(core.prepare_manager_update(update['item'],STATE/'cache') if update['kind']=='manager'
                      else core.fetch(update['item'],STATE/'cache'))
                results.append((update['kind'],path))
            return results
        def done(results):
            for kind,path in results:self.log('已下载：'+str(path))
            self.status.set('更新已下载。插件请点击“安装 / 更新插件”；词库请点击“更新共享词库”。')
            manager=next((p for kind,p in results if kind=='manager'),None)
            if manager:
                if messagebox.askyesno('新版工具已下载','是否现在打开新版管理器？\n当前管理器会退出，UE 保持运行。\n插件和词库如有更新，可在新版管理器中继续安装。',parent=self):self.open_manager(manager)
            else:messagebox.showinfo('下载完成','更新包已下载并校验。\n插件请点击“安装 / 更新插件”；词库请点击“更新共享词库”。',parent=self)
        self.start(task,done)

    def open_manager(self,path):
        try:
            self.save_settings();os.startfile(str(path));self.closing=True;self.destroy()
        except OSError as error:messagebox.showerror('启动失败','新版已下载：'+str(path)+'\n'+str(error),parent=self)

    def update_manager(self):
        if not self.feed or self.feed_origin!=self.feed_var.get():self.check(False);return
        item=self.feed.get('manager')
        if not item:
            webbrowser.open(core.DOCS_URL);return
        item=dict(item)
        def done(path):
            self.log('新版工具已校验并解压：'+str(path))
            self.open_manager(path)
        self.start(lambda:core.prepare_manager_update(item,STATE/'cache'),done)

    def start_file_update(self,project,prepare,apply,done):
        """Download first; ask to close UE before any project file replacement."""
        if self.busy:
            messagebox.showinfo('正在处理','请等待当前操作完成。',parent=self);return
        try:core.project_path(project)
        except ValueError as error:messagebox.showerror('选择工程',str(error),parent=self);return
        context=(project,self.engine.get(),self.feed_var.get())
        def ready(result):
            prepared,editors=result
            if context!=(self.project.get(),self.engine.get(),self.feed_var.get()):
                self.status.set('选择已改变，更新已暂停；下载包已保留。');return
            if editors:
                labels='\n'.join((p['title'] or p['name'])+'  (PID '+str(p['pid'])+')' for p in editors)
                prompt=('检测到以下虚幻进程正在运行：\n'+labels+
                        '\n\n请先保存工作。是否请求正常关闭以上 UE，并在全部退出后继续更新？'
                        '\n如 UE 弹出保存提示，请在 UE 中处理。取消退出或 90 秒内未退出，更新会暂停；不会强制结束。')
                if not messagebox.askyesno('更新前关闭虚幻编辑器',prompt,parent=self,default=messagebox.NO):
                    self.status.set('更新已暂停，UE 保持运行；下载包已保留。');return
            def write():
                if editors:editor_process.close_and_wait(editors,self.log)
                # The core repeats its running-process check immediately before writes.
                return apply(prepared)
            self.start(write,done)
        self.start(lambda:(prepare(),editor_process.list_editors()),ready)

    def update_defaults(self):
        project=self.project.get();source=self.feed_var.get()
        if not messagebox.askyesno('更新共享词库','更新基础翻译，个人译文保持不变；旧共享词库会备份。继续？',parent=self):return
        def task():
            feed=core.load_feed(source,STATE/'cache');item=feed['shared']
            return core.fetch(item,STATE/'cache'),item['version']
        self.start_file_update(project,task,lambda data:core.update_shared_defaults(project,*data),
                               lambda p:(self.log('共享词库已更新，备份：'+str(p)),self.check(True,notify=False)))

    def require_package(self):
        if not self.selected or self.checked_engine!=self.engine.get() or self.feed_origin!=self.feed_var.get():
            messagebox.showinfo('先检查更新','请先选择引擎并点击“检查更新”。',parent=self);return False
        return True

    def install(self):
        if not self.require_package():return
        project=self.project.get();item=dict(self.selected);engine=self.engine.get()
        if not messagebox.askyesno('安装插件','安装会保留个人词典，旧插件会备份。\n继续安装到工程：'+project+'？',parent=self):return
        def task():
            info=core.engine_info(engine,self.log)
            if not core.matching({'plugins':[item]},info):raise ValueError('引擎在检查后发生变化，请重新检查。')
            self.log('下载并校验安装包…'); archive=core.fetch(item,STATE/'cache')
            return archive,info
        self.start_file_update(project,task,lambda data:core.install(project,*data,self.log),
                               lambda p:(self.log('安装完成，备份：'+str(p)),self.check(True,notify=False)))

    def download_plugin(self):
        if not self.require_package():return
        path=filedialog.asksaveasfilename(parent=self,defaultextension='.zip',initialfile=Path(self.selected['url']).name)
        if path:
            item=dict(self.selected)
            self.start(lambda:core.download(item['_location'],path,item['sha256']),lambda p:self.log('已下载：'+str(p)))

    def backup(self):
        project=self.project.get()
        self.start(lambda:core.backup(project),lambda p:self.log('备份完成：'+str(p)))

    def confirm_replace(self):
        return messagebox.askyesno('替换共享译文','将覆盖所选文件中的自定义译文。\n替换前自动备份当前词典和长文本，可随时恢复。继续？',parent=self)

    def shared(self):
        if not self.confirm_replace():return
        source=self.feed_var.get();project=self.project.get();mode=self.selection.get()
        def task():
            feed=core.load_feed(source,STATE/'cache');archive=core.fetch(feed['shared'],STATE/'cache')
            return archive
        self.start_file_update(project,task,lambda archive:self.replace_captured(project,mode,archive),
                               lambda p:self.log('共享译文已替换，原文件备份：'+str(p)))

    @staticmethod
    def replace_captured(project,mode,archive):
        contents=core.shared_contents(archive)
        if mode!='both':
            leave=core.PROTECTED[1] if mode=='term' else core.PROTECTED[0]
            file=core.project_path(project)/leave
            contents[leave]=file.read_bytes() if file.exists() else None
        return core.replace_files(project,contents)

    def shared_offline(self):
        archive=filedialog.askopenfilename(parent=self,filetypes=[('共享词典包','*.zip')])
        if archive and self.confirm_replace():
            project=self.project.get();mode=self.selection.get()
            self.start_file_update(project,lambda:archive,lambda path:self.replace_captured(project,mode,path),
                                   lambda p:self.log('已替换；备份：'+str(p)))

    def restore(self):
        archive=filedialog.askopenfilename(parent=self,title='选择 dictionary- 或 shared- 开头的备份',filetypes=[('词典备份','*.zip')])
        if archive and messagebox.askyesno('恢复备份','当前文件会先另存备份，再恢复所选版本。继续？',parent=self):
            project=self.project.get()
            self.start_file_update(project,lambda:archive,lambda path:core.restore(project,path),
                                   lambda p:self.log('已恢复；恢复前的文件备份：'+str(p)))

    def open_folders(self):
        try:project=core.project_path(self.project.get())
        except ValueError as e:messagebox.showerror('选择工程',str(e),parent=self);return
        for relative in ('Plugins/XHNodeChinese/Dictionaries','Saved/XHNodeChinese'):
            self.open_path(project/relative)

    def build_args(self):
        return dict(engine=self.build_engine.get(),sdk=self.sdk.get(),vcvars=self.vcvars.get(),python=self.python.get(),
                    output=self.out.get(),compiler_version=self.msvc.get(),log=self.log)

    def check_build(self):
        args=self.build_args()
        def task():
            for name in ('engine','sdk'):self.log(name+'：'+str(core.engine_path(args[name])))
            for name in ('vcvars','python'):
                if not Path(args[name]).is_file():raise ValueError(name+' 文件不存在。')
                self.log(name+'：'+args[name])
            core.run_logged([args['python'],'--version'],BASE,self.log)
            self.log('基础路径检查通过。头文件、链接库和编译器版本将在实际编译时检查。')
        self.start(task)

    def compile(self):
        self.check_versions(then_compile=True)

    def use_sdk_target(self):
        try:self.build_engine.set(str(core.engine_path(self.sdk.get())))
        except ValueError as error:messagebox.showerror('SDK 路径需检查',str(error),parent=self)

    def check_versions(self,then_compile=False):
        args=self.build_args();source=self.source_package.get();project=self.project.get();feed=self.feed_var.get()
        def task():
            return build_preflight.probe(args['engine'],source,args['output'],STATE/'cache',BASE/'release',project,feed,self.log)
        def ready(result):
            if args['engine']!=self.build_engine.get() or source!=self.source_package.get() or args['output']!=self.out.get():
                self.cloud_status.set('编译设置已改变，请重新检测版本。');return
            self.log('编译目标：'+args['engine']+' / UE '+result['engine']['version'])
            if result['cloud_error']:self.log('云端检查失败，本地检测仍有效：'+result['cloud_error'])
            origin,item=build_preflight.preferred(result)
            if item:
                label=item.get('label','兼容插件包')+' · v'+item['version']
                self.cloud_status.set(('本地可用：' if origin=='local' else '云端可用：')+label)
                if origin=='local':
                    detail='检测到'+label+'。\n'+item['path']+'\n\n'
                    detail+=('这是未经过发布验证的本地测试包，只供隔离测试。\n' if item['kind']=='package' and not item['verified'] else '')
                    if messagebox.askyesno('已有本地版本',detail+'是否使用现有版本并打开所在目录？选择“否”也不会自动开始重复编译。',parent=self):
                        self.start(lambda:build_preflight.reuse(item,args['output']),lambda p:(self.log('使用本地版本：'+str(p)),self.open_path(p if Path(p).is_dir() else Path(p).parent)))
                else:
                    if messagebox.askyesno('云端已有匹配版本',label+'\n无需重复编译，是否下载到输出目录？',parent=self):
                        def download():
                            cached=core.fetch(item,STATE/'cache')
                            candidate={'kind':'package','path':str(cached),'sha256':item['sha256'],'filename':Path(item['url']).name}
                            return build_preflight.reuse(candidate,args['output'])
                        self.start(download,lambda p:(self.log('已下载匹配包：'+str(p)),self.open_path(Path(p).parent)))
                return
            self.cloud_status.set('未找到可复用的本地版本。'+('云端检查未完成。' if result['cloud_error'] else '云端暂无匹配包。'))
            if not then_compile:return
            if not source or not Path(source).is_file():
                messagebox.showinfo('需要源码包','未找到可复用版本，请先选择维护者提供的新版源码 ZIP。',parent=self);return
            if result['cloud_error'] and not messagebox.askyesno('云端检查未完成','本地没有可复用版本，但无法确认云端状态。是否继续本地编译？',parent=self):return
            contribution=result.get('contribution')
            if contribution and contribution['state'] in ('pending_review','approved'):
                self.cloud_status.set('云端已有投稿，等待验证／正式发布；暂不能直接安装。')
                if not messagebox.askyesno('已有待发布构建',self.cloud_status.get()+'\n是否仍为本机编译测试包？',parent=self):return
            # A failed query is never treated as a confirmed missing cloud build.
            self.compile_local(source,args,contribution or ({'state':'missing'} if not result['cloud_error'] else None))
        self.start(task,ready)

    def show_cloud_result(self,result):
        kind='官方指纹已确认' if result['kind']=='official' else '定制／未认证指纹'
        states={'available':'已有兼容共享包，可直接下载','missing':'云端尚未收录','pending_review':'已收录，等待审核',
                'approved':'已审核，等待正式发布','rejected':'此前投稿未通过，可重新提交'}
        self.cloud_status.set(kind+' · '+states[result['state']]);self.log(self.cloud_status.get())

    def check_cloud(self):
        self.check_versions()

    def compile_local(self,source,args,cloud_result):
        target=core.engine_path(args['engine']);sdk=core.engine_path(args['sdk'])
        detail='编译目标：'+str(target)+'\n依赖 SDK：'+str(sdk)+'\n输出目录：'+args['output']+'\n\n'
        if target!=sdk:detail+='目标与 SDK 路径不同。生成的插件适用于上面的编译目标；如果要编译 SDK 对应引擎，请先使用“以 SDK 为编译目标”。\n\n'
        if not messagebox.askyesno('确认编译目标',detail+'本次使用独立目录。连续 5 分钟无输出或单阶段超过 20 分钟会停止，并保留日志；也可随时取消。继续？',parent=self):return
        cancel=threading.Event();self.build_cancel=cancel;self.cancel_build_button.configure(state='normal')
        def task():
            return core.compile_package(source,**args,cancel_event=cancel)
        def done(path):
            self.last_compiled=path;self.log('生成测试包：'+str(path))
            if cloud_result and cloud_result['state'] in ('missing','rejected'):self.submit_compiled(path)
        self.start(task,done)

    def cancel_compile(self):
        if self.build_cancel is not None:
            self.build_cancel.set();self.cloud_status.set('正在停止本次编译，保留工作目录和日志…')
            self.cancel_build_button.configure(state='disabled')

    def submit_compiled(self,package=None):
        if package is None:
            package=filedialog.askopenfilename(parent=self,title='选择编译生成的测试 ZIP（同目录需有构建报告 JSON）',filetypes=[('编译测试包','*.zip')])
        if not package:return
        package=Path(package)
        def task():
            report=core.json_read(package.with_suffix('.json'))
            if core.digest(package)!=report['sha256']:raise ValueError('编译包与报告不一致。')
            return community.check(report['engine'],community.source_version(package),STATE/'cache')
        def ready(result):
            self.show_cloud_result(result)
            if result['state'] not in ('missing','rejected'):
                messagebox.showinfo('无需重复投稿',self.cloud_status.get(),parent=self);return
            consent=False
            if result['kind']=='custom':
                consent=messagebox.askyesno('是否公开分享定制构建？',
                    '这个引擎的指纹尚未登记为官方构建。\n\n是否同意将插件编译组件、引擎指纹和版本信息公开投稿到 GitHub？\n'
                    '它会存入独立的“定制／未认证”区。投稿包不包含引擎文件、源码、个人词典或工程内容。\n\n选择“否”会保留本地编译结果，不创建投稿。',parent=self)
                if not consent:
                    self.cloud_status.set('已保留本地结果；未同意分享，未创建定制投稿。');return
            def prepared(data):
                path,url=data;self.log('投稿包已准备，尚未上传：'+str(path))
                self.cloud_status.set('投稿包已就绪，等待在 GitHub 上传附件并提交。')
                if messagebox.askyesno('提交到 GitHub',
                    '投稿包已准备。接下来登录你自己的 GitHub 账号，将下列 ZIP 拖入投稿正文，等待上传完成后提交。\n\n'+str(path)+
                    '\n\n提交后云端会校验、去重并分区收录；通过维护者验证后才会供其他用户安装。\n是否打开投稿页面和文件夹？',parent=self):
                    webbrowser.open(url);self.open_path(path.parent)
            self.start(lambda:community.prepare(package,result,package.parent/'contributions',consent),prepared)
        self.start(task,ready)

    def close(self):
        if self.busy:
            messagebox.showinfo('正在处理','请等待当前操作完成后关闭，避免中断文件替换或编译。',parent=self);return
        self.save_settings();self.closing=True;self.destroy()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--check',metavar='MANIFEST')
    parser.add_argument('--engine')
    parser.add_argument('--backup',metavar='UPROJECT')
    args=parser.parse_args()
    if args.backup:print(core.backup(args.backup))
    elif args.check:
        feed=core.load_feed(args.check,STATE/'cache')
        if args.engine:print(json.dumps(core.matching(feed,core.engine_info(args.engine)),ensure_ascii=False,indent=2))
        else:print(json.dumps(feed,ensure_ascii=False,indent=2))
    else:App().mainloop()


if __name__=='__main__':main()
