"""XH plugin manager GUI and publisher CLI."""
import argparse
import json
import os
from pathlib import Path
import queue
import shutil
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser
import manager_core as core

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
        self.title('星河插件管理器 · 安装、共享词典与编译')
        self.geometry('1080x900'); self.minsize(980,820)
        # Dependency-free dark tool-panel styling.
        self.configure(background='#0b1220')
        style=ttk.Style(self); style.theme_use('clam')
        style.configure('.',font=('Microsoft YaHei UI',10))
        style.configure('TFrame',background='#0b1220')
        style.configure('TLabel',background='#0b1220',foreground='#e8f0ff')
        style.configure('TRadiobutton',background='#0b1220',foreground='#d8e5fa')
        style.configure('TCheckbutton',background='#0b1220',foreground='#d8e5fa')
        style.configure('TNotebook',background='#0b1220',borderwidth=0)
        style.configure('TNotebook.Tab',padding=(20,10),background='#16243d',foreground='#9fb0ca')
        style.map('TNotebook.Tab',background=[('selected','#263b63'),('active','#1d3152')],foreground=[('selected','#5de1ff')])
        style.configure('TButton',padding=(12,7),background='#16243d',foreground='#e8f0ff',bordercolor='#2b4166')
        style.map('TButton',background=[('active','#263b63'),('disabled','#111a2b')],foreground=[('disabled','#60708a')])
        style.configure('Accent.TButton',background='#27c7ed',foreground='#06111e',bordercolor='#55e3ff')
        style.map('Accent.TButton',background=[('active','#62e7ff')])
        style.configure('Title.TLabel',font=('Microsoft YaHei UI',21,'bold'),foreground='#eff8ff',background='#0b1220')
        style.configure('Logo.TLabel',font=('Segoe UI Symbol',16,'bold'),foreground='#5de1ff',background='#0b1220')
        style.configure('Hint.TLabel',foreground='#9fb0ca',background='#0b1220')
        style.configure('Section.TLabel',font=('Microsoft YaHei UI',14,'bold'),foreground='#5de1ff',background='#0b1220')
        style.configure('TEntry',fieldbackground='#101d33',foreground='#e8f0ff',insertcolor='#5de1ff')
        style.configure('Card.TFrame',background='#132239')
        style.configure('Card.TLabel',background='#132239',foreground='#e8f0ff',font=('Microsoft YaHei UI',10,'bold'))
        style.configure('CardHint.TLabel',background='#132239',foreground='#70accd',font=('Microsoft YaHei UI',9))
        style.configure('Horizontal.TProgressbar',background='#27c7ed',troughcolor='#132239',bordercolor='#132239')
        self.messages=queue.Queue(); self.busy=False; self.feed=None; self.feed_origin=''
        self.checking=False
        self.closing=False
        self.info=None; self.checked_engine=''; self.selected=None
        settings={}
        try: settings=core.json_read(STATE/'settings.json')
        except (OSError,ValueError): pass
        self.project=tk.StringVar(value=settings.get('project',''))
        self.engine=tk.StringVar(value=settings.get('engine',''))
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
        top=ttk.Frame(self,padding=20); top.pack(fill='x')
        title_row=ttk.Frame(top); title_row.pack(fill='x')
        ttk.Label(title_row,text='◈',style='Logo.TLabel').pack(side='left',padx=(0,8))
        ttk.Label(title_row,text='星河插件管理器',style='Title.TLabel').pack(side='left')
        ttk.Label(title_row,text='XH  /  v'+core.VERSION,style='Logo.TLabel').pack(side='right')
        ttk.Label(top,text='选工程 → 检查版本 → 安装或更新。词典替换前自动备份。',style='Hint.TLabel').pack(anchor='w',pady=(5,12))
        cards=ttk.Frame(top);cards.pack(fill='x',pady=(0,10))
        self.card_vars={}
        for index,(key,title,initial) in enumerate((('manager','01  更新工具','当前 v'+core.VERSION),('plugin','02  引擎插件','选择工程和引擎'),('shared','03  共享词库','启动后自动检查'))):
            cards.columnconfigure(index,weight=1,uniform='status')
            card=ttk.Frame(cards,style='Card.TFrame',padding=(14,10));card.grid(row=0,column=index,sticky='nsew',padx=(0,8 if index<2 else 0))
            ttk.Label(card,text=title,style='CardHint.TLabel').pack(anchor='w')
            self.card_vars[key]=tk.StringVar(value=initial)
            ttk.Label(card,textvariable=self.card_vars[key],style='Card.TLabel',wraplength=290).pack(anchor='w',pady=(5,0))
        self.path_row(top,'工程',self.project,lambda:self.choose_project())
        self.path_row(top,'引擎',self.engine,lambda:self.choose_dir(self.engine))
        book=ttk.Notebook(self); book.pack(fill='both',expand=True,padx=20)
        install=ttk.Frame(book,padding=16); shared=ttk.Frame(book,padding=16); build=ttk.Frame(book,padding=16)
        book.add(install,text='① 安装与更新'); book.add(shared,text='② 共享词典 / 备份'); book.add(build,text='③ 编译其他引擎')
        self.path_row(install,'更新来源',self.feed_var,self.choose_feed,button_text='离线清单…')
        ttk.Label(install,text='默认：GitHub Releases。也可选择随包附带的 release/manifest.json。',wraplength=820).pack(anchor='w',pady=6)
        bar=ttk.Frame(install);bar.pack(fill='x',pady=8)
        ttk.Button(bar,text='检查可用更新',style='Accent.TButton',command=lambda:self.check(True)).pack(side='left',padx=(0,8))
        ttk.Button(bar,text='安装 / 更新匹配版本',command=self.install).pack(side='left',padx=4)
        ttk.Button(bar,text='只下载安装包',command=self.download_plugin).pack(side='left',padx=4)
        ttk.Button(bar,text='使用随包离线版本',command=self.use_bundled).pack(side='left',padx=4)
        ttk.Checkbutton(install,text='启动时自动检查更新',variable=self.auto_check).pack(anchor='w',pady=(2,0))
        self.package_label=tk.StringVar(value='尚未检查。不同引擎构建需要不同的动态组件。')
        ttk.Label(install,textvariable=self.package_label,wraplength=820).pack(anchor='w',pady=15)
        ttk.Label(install,text='安装插件时保留个人词典与工程 Saved 数据；完整旧插件另行备份。\n安装前请关闭 UE。没有匹配版本时，到“编译其他引擎”创建测试包。',wraplength=820).pack(anchor='w',pady=5)
        links=ttk.Frame(install);links.pack(anchor='w',pady=8)
        ttk.Button(links,text='打开 GitHub 发布页',command=lambda:webbrowser.open(core.REPOSITORY+'/releases')).pack(side='left')
        ttk.Button(links,text='打开使用说明',command=lambda:self.open_path(BASE/'README.md')).pack(side='left',padx=8)
        self.manager_button=ttk.Button(links,text='下载并打开新版工具',command=self.update_manager,state='disabled')
        self.manager_button.pack(side='left',padx=8)

        ttk.Label(shared,text='共享基础词库 · 安装即用',style='Section.TLabel').pack(anchor='w')
        ttk.Label(shared,text='新版插件自带通用词条和长说明；个人译文始终优先。共享词库由本插件维护。',wraplength=920).pack(anchor='w',pady=8)
        row=ttk.Frame(shared);row.pack(anchor='w',pady=(0,12))
        ttk.Button(row,text='更新共享词库',style='Accent.TButton',command=self.update_defaults).pack(side='left')
        ttk.Label(row,text='只更新基础翻译，保留个人词典；请先关闭 UE。',style='Hint.TLabel').pack(side='left',padx=12)
        ttk.Separator(shared).pack(fill='x',pady=(0,12))
        ttk.Label(shared,text='个人词典 · 备份与替换',style='Section.TLabel').pack(anchor='w')
        ttk.Label(shared,text='以下“替换”会覆盖所选个人文件；每次先备份，可随时恢复。',wraplength=900).pack(anchor='w',pady=8)
        pick=ttk.Frame(shared);pick.pack(anchor='w',pady=5)
        for value,label in [('both','个人词典 + 长文本'),('term','仅个人词典'),('long','仅长文本')]:
            ttk.Radiobutton(pick,text=label,variable=self.selection,value=value).pack(side='left',padx=(0,20))
        bar=ttk.Frame(shared);bar.pack(anchor='w',pady=12)
        ttk.Button(bar,text='一键备份当前文件',style='Accent.TButton',command=self.backup).pack(side='left',padx=(0,8))
        ttk.Button(bar,text='从更新源替换',command=self.shared).pack(side='left',padx=4)
        ttk.Button(bar,text='从离线共享包替换',command=self.shared_offline).pack(side='left',padx=4)
        ttk.Button(bar,text='恢复备份…',command=self.restore).pack(side='left',padx=4)
        ttk.Button(shared,text='打开词典和备份目录',command=self.open_folders).pack(anchor='w')
        self.shared_label=tk.StringVar(value='先检查更新可查看共享词典版本。词典更新不要求重新编译插件。')
        ttk.Label(shared,textvariable=self.shared_label,wraplength=820).pack(anchor='w',pady=16)
        ttk.Label(shared,text='文件位置（相对于工程）：\n个人词典：Plugins/XHNodeChinese/Dictionaries/User.csv\n长文本：Saved/XHNodeChinese/LongText.csv\n备份：Saved/XHNodeChinese/UpdaterBackups',wraplength=820).pack(anchor='w')

        ttk.Label(build,text='为目标引擎编译测试包',style='Section.TLabel').pack(anchor='w')
        ttk.Label(build,text='维护者功能：先选择授权的本地源码包，再准备目标 SDK、C++ 工具链和 Python 3.9+。\n公开更新源只提供安装包；跨版本 C++ 接口差异可能需要适配源码。',wraplength=820).pack(anchor='w',pady=8)
        self.path_row(build,'本地源码包',self.source_package,lambda:self.choose_file(self.source_package,[('插件源码包','*.zip')]))
        self.path_row(build,'完整 SDK',self.sdk,lambda:self.choose_dir(self.sdk))
        self.path_row(build,'vcvars64.bat',self.vcvars,lambda:self.choose_file(self.vcvars,[('VS 环境脚本','vcvars64.bat')]))
        self.path_row(build,'python.exe',self.python,lambda:self.choose_file(self.python,[('Python','python.exe')]))
        self.path_row(build,'输出目录',self.out,lambda:self.choose_dir(self.out))
        row=ttk.Frame(build);row.pack(fill='x',pady=4)
        ttk.Label(row,text='MSVC 版本',width=13).pack(side='left');ttk.Entry(row,textvariable=self.msvc,width=12).pack(side='left')
        ttk.Label(row,text='填写目标引擎使用的工具链，例如 14.50').pack(side='left',padx=10)
        row=ttk.Frame(build);row.pack(anchor='w',pady=8)
        ttk.Button(row,text='检查编译环境',command=self.check_build).pack(side='left')
        ttk.Button(row,text='编译并生成测试包',command=self.compile).pack(side='left',padx=8)
        ttk.Button(row,text='下载 Visual Studio',command=lambda:webbrowser.open('https://visualstudio.microsoft.com/visual-cpp-build-tools/')).pack(side='left')
        ttk.Button(row,text='下载 Python',command=lambda:webbrowser.open('https://www.python.org/downloads/windows/')).pack(side='left',padx=8)
        bottom=ttk.Frame(self,padding=(20,10));bottom.pack(side='bottom',fill='x',before=book)
        ttk.Label(bottom,textvariable=self.status,wraplength=940).pack(anchor='w')
        self.progress=ttk.Progressbar(bottom,mode='indeterminate');self.progress.pack(fill='x',pady=6)
        self.logbox=tk.Text(bottom,height=4,font=('Consolas',9),state='disabled',wrap='word',
                            background='#08101e',foreground='#b9d4f0',insertbackground='#5de1ff',
                            relief='flat',highlightthickness=1,highlightbackground='#263957')
        self.logbox.pack(fill='x')
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
            sdk=self.sdk.get(),vcvars=self.vcvars.get(),python=self.python.get(),msvc=self.msvc.get(),output=self.out.get(),source_package=self.source_package.get(),auto_check=self.auto_check.get()))

    def start(self,fn,done=lambda result:None,quiet=False):
        if self.busy:
            messagebox.showinfo('正在处理','请等待当前操作完成。',parent=self);return
        self.save_settings();self.busy=True;self.status.set('正在处理，请查看进度日志…');self.progress.start(12)
        def work():
            try: self.messages.put(('done',(done,fn())))
            except Exception as e:self.messages.put(('error',(str(e),quiet)))
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
                if kind=='error':
                    error,quiet=(value if isinstance(value,tuple) else (value,False))
                    self.status.set('操作未完成：'+error)
                    if not quiet: messagebox.showerror('操作未完成',error,parent=self)
                else:
                    self.status.set('操作完成。'); callback,result=value;callback(result)
        if not self.closing:self.after(100,self.pump)

    def startup_check(self):
        """Refresh release metadata without interrupting first launch with a dialog."""
        if self.busy: return
        self.status.set('正在后台检查更新清单…')
        self.check(bool(self.engine.get()),automatic=True)

    def check(self,with_engine=True,automatic=False):
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
        if automatic:
            self.checking=True
            def work():
                try:self.messages.put(('check_done',(done,task())))
                except Exception as error:self.messages.put(('check_error',str(error)))
            threading.Thread(target=work,daemon=True).start()
        else:self.start(task,done)

    def update_manager(self):
        if not self.feed or self.feed_origin!=self.feed_var.get():self.check(False);return
        item=self.feed.get('manager')
        if not item:
            webbrowser.open(core.REPOSITORY+'/releases/latest');return
        item=dict(item)
        def done(path):
            self.log('新版工具已校验并解压：'+str(path))
            try:
                self.save_settings();os.startfile(str(path));self.closing=True;self.destroy()
            except OSError as error:messagebox.showerror('启动失败','新版已下载：'+str(path)+'\n'+str(error),parent=self)
        self.start(lambda:core.prepare_manager_update(item,STATE/'cache'),done)

    def update_defaults(self):
        project=self.project.get();source=self.feed_var.get()
        if not messagebox.askyesno('更新共享词库','请先保存并关闭 UE。\n更新基础翻译，个人译文保持不变；旧共享词库会备份。继续？',parent=self):return
        def task():
            feed=core.load_feed(source,STATE/'cache');item=feed['shared']
            return core.update_shared_defaults(project,core.fetch(item,STATE/'cache'),item['version'])
        self.start(task,lambda p:(self.log('共享词库已更新，备份：'+str(p)),self.check(True)))

    def require_package(self):
        if not self.selected or self.checked_engine!=self.engine.get() or self.feed_origin!=self.feed_var.get():
            messagebox.showinfo('先检查更新','请先选择引擎并点击“检查可用更新”。',parent=self);return False
        return True

    def install(self):
        if not self.require_package():return
        project=self.project.get();item=dict(self.selected);engine=self.engine.get()
        if not messagebox.askyesno('安装插件','请保存并关闭 UE。\n安装会保留个人词典，旧插件会备份。\n继续安装到当前工程？',parent=self):return
        def task():
            info=core.engine_info(engine,self.log)
            if not core.matching({'plugins':[item]},info):raise ValueError('引擎在检查后发生变化，请重新检查。')
            self.log('下载并校验安装包…'); archive=core.fetch(item,STATE/'cache')
            return core.install(project,archive,info)
        self.start(task,lambda p:self.log('安装完成，备份：'+str(p)))

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
        return messagebox.askyesno('替换共享译文','将覆盖所选文件中的自定义译文。\n替换前自动备份当前词典和长文本，可随时恢复。\n请保存并关闭 UE。继续？',parent=self)

    def shared(self):
        if not self.confirm_replace():return
        source=self.feed_var.get();project=self.project.get();mode=self.selection.get()
        def task():
            feed=core.load_feed(source,STATE/'cache');archive=core.fetch(feed['shared'],STATE/'cache')
            return self.replace_captured(project,mode,archive)
        self.start(task,lambda p:self.log('共享译文已替换，原文件备份：'+str(p)))

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
            self.start(lambda:self.replace_captured(project,mode,archive),lambda p:self.log('已替换；备份：'+str(p)))

    def restore(self):
        archive=filedialog.askopenfilename(parent=self,title='选择 dictionary- 或 shared- 开头的备份',filetypes=[('词典备份','*.zip')])
        if archive and messagebox.askyesno('恢复备份','当前文件会先另存备份，再恢复所选版本。\n请关闭 UE。继续？',parent=self):
            project=self.project.get();self.start(lambda:core.restore(project,archive),lambda p:self.log('已恢复；恢复前的文件备份：'+str(p)))

    def open_folders(self):
        try:project=core.project_path(self.project.get())
        except ValueError as e:messagebox.showerror('选择工程',str(e),parent=self);return
        for relative in ('Plugins/XHNodeChinese/Dictionaries','Saved/XHNodeChinese'):
            self.open_path(project/relative)

    def build_args(self):
        return dict(engine=self.engine.get(),sdk=self.sdk.get(),vcvars=self.vcvars.get(),python=self.python.get(),
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
        args=self.build_args();source=self.source_package.get()
        if not source or not Path(source).is_file():
            messagebox.showinfo('选择源码包','请先选择维护者提供的本地插件源码 ZIP。公开安装包不能用于编译。',parent=self);return
        if not messagebox.askyesno('开始编译','编译可能耗时数分钟，将在输出目录生成独立测试包，不改动当前工程。\n首次编译会运行目标 SDK 的构建工具。继续？',parent=self):return
        def task():
            return core.compile_package(source,**args)
        self.start(task,lambda p:self.log('生成测试包：'+str(p)))

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
