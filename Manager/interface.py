"""Static, dependency-free control-panel UI; all actions stay in App."""
import tkinter as tk
from tkinter import ttk
import webbrowser
import branding

BG='#080e19'
PANEL='#101c2e'
LINE='#21354e'
TEXT='#e7f0ff'
MUTED='#8dabc8'
CYAN='#55dcf4'


def configure(app):
    app.geometry('1180x870');app.minsize(1040,800)
    app.configure(background=BG)
    s=ttk.Style(app);s.theme_use('clam')
    s.configure('.',font=('Microsoft YaHei UI',10),background=BG,foreground=TEXT)
    for name in ('TFrame','TLabel'):s.configure(name,background=BG,foreground=TEXT)
    s.configure('Panel.TFrame',background=PANEL)
    s.configure('Panel.TLabel',background=PANEL,foreground=TEXT)
    s.configure('Muted.TLabel',foreground=MUTED)
    s.configure('PanelMuted.TLabel',background=PANEL,foreground=MUTED,font=('Microsoft YaHei UI',9))
    s.configure('Title.TLabel',font=('Microsoft YaHei UI',23,'bold'))
    s.configure('Section.TLabel',font=('Microsoft YaHei UI',16,'bold'))
    s.configure('Eyebrow.TLabel',foreground=CYAN,font=('Consolas',10))
    s.configure('Card.TLabel',background=PANEL,foreground=TEXT,font=('Microsoft YaHei UI',11,'bold'))
    s.configure('TEntry',fieldbackground='#0b1524',foreground=TEXT,insertcolor=CYAN,
                bordercolor=LINE,lightcolor=LINE,darkcolor=LINE,padding=7)
    s.map('TEntry',bordercolor=[('focus',CYAN)],lightcolor=[('focus',CYAN)])
    s.configure('TButton',padding=(13,9),background='#172940',foreground=TEXT,
                borderwidth=1,bordercolor='#294663',lightcolor='#172940',darkcolor='#172940')
    s.map('TButton',background=[('active','#22435f'),('disabled','#101c2c')],
          foreground=[('disabled','#63788e')],bordercolor=[('focus',CYAN)])
    s.configure('Accent.TButton',background=CYAN,foreground='#061523',bordercolor=CYAN,
                lightcolor=CYAN,darkcolor=CYAN,font=('Microsoft YaHei UI',10,'bold'))
    s.map('Accent.TButton',background=[('active','#90edff'),('disabled','#1b3a4c')],
          foreground=[('disabled','#7fa2b6')])
    s.configure('Nav.TButton',anchor='w',padding=(15,15),background=BG,borderwidth=0,
                bordercolor=BG,foreground=MUTED,lightcolor=BG,darkcolor=BG)
    s.map('Nav.TButton',background=[('active','#132338')],foreground=[('active',TEXT)])
    s.configure('Active.Nav.TButton',background='#17344a',foreground=CYAN)
    s.configure('Ghost.TButton',background=BG,foreground=MUTED,borderwidth=0,lightcolor=BG,darkcolor=BG)
    s.map('Ghost.TButton',background=[('active','#132338')],foreground=[('active',TEXT)])
    for name in ('TCheckbutton','TRadiobutton'):
        s.configure(name,background=BG,foreground=TEXT,indicatorbackground='#172940',indicatorforeground=CYAN)
        s.map(name,background=[('active',BG)],foreground=[('active',CYAN)])
    s.configure('TSeparator',background=LINE,lightcolor=LINE,darkcolor=LINE,bordercolor=LINE)
    s.configure('Body.TNotebook',background=BG,borderwidth=0,tabmargins=0,bordercolor=BG,lightcolor=BG,darkcolor=BG)
    s.layout('Body.TNotebook.Tab',[])
    s.configure('Horizontal.TProgressbar',background=CYAN,troughcolor='#172940',borderwidth=0,
                lightcolor=CYAN,darkcolor=CYAN,bordercolor=LINE)
    s.configure('Vertical.TScrollbar',background='#263e56',troughcolor=BG,arrowcolor=MUTED,
                bordercolor=BG,lightcolor=BG,darkcolor=BG,width=12)
    s.map('Vertical.TScrollbar',background=[('active','#3a667e')])


def logo(parent):
    return branding.logo(parent, BG)


def heading(parent,number,title,description):
    ttk.Label(parent,text=number,style='Eyebrow.TLabel').pack(anchor='w')
    ttk.Label(parent,text=title,style='Section.TLabel').pack(anchor='w',pady=(3,5))
    ttk.Label(parent,text=description,style='Muted.TLabel',wraplength=760).pack(anchor='w',pady=(0,14))


def build(app,core,base):
    header=ttk.Frame(app,padding=(24,18,24,16));header.pack(fill='x')
    logo(header).pack(side='left',padx=(0,14))
    brand=ttk.Frame(header);brand.pack(side='left')
    ttk.Label(brand,text=core.PRODUCT_NAME,style='Title.TLabel').pack(anchor='w')
    ttk.Label(brand,text='安装 · 汉化词库 · 引擎构建',style='Muted.TLabel').pack(anchor='w',pady=(3,0))
    version=ttk.Frame(header);version.pack(side='right')
    ttk.Label(version,text='UE TRANSLATE  /  '+core.VERSION,style='Eyebrow.TLabel').pack(anchor='e')
    ttk.Label(version,text='虚幻引擎工具箱',style='Muted.TLabel').pack(anchor='e',pady=(5,0))
    beam=tk.Canvas(app,height=2,bg=LINE,highlightthickness=0);beam.pack(fill='x',padx=24)
    beam.create_line(0,1,140,1,fill=CYAN,width=2)
    shell=ttk.Frame(app,padding=(16,14,24,14));shell.pack(fill='both',expand=True)
    rail=ttk.Frame(shell,width=176);rail.pack(side='left',fill='y',padx=(0,20));rail.pack_propagate(False)
    ttk.Label(rail,text='工作空间',style='Muted.TLabel').pack(anchor='w',padx=14,pady=(10,12))
    nav=ttk.Frame(rail);nav.pack(fill='x')
    rail_bottom=ttk.Frame(rail);rail_bottom.pack(side='bottom',fill='x')
    ttk.Separator(rail_bottom).pack(fill='x',padx=12,pady=12)
    ttk.Button(rail_bottom,text='使用说明  ↗',style='Ghost.TButton',command=lambda:webbrowser.open(core.DOCS_URL)).pack(fill='x')
    ttk.Button(rail_bottom,text='维护与下载  ↗',style='Ghost.TButton',command=lambda:webbrowser.open(core.DOCS_URL)).pack(fill='x')
    ttk.Button(rail_bottom,text='离线说明',style='Ghost.TButton',command=lambda:app.open_path(base/'README.md')).pack(fill='x')
    ttk.Label(rail_bottom,text='个人译文优先\n替换前自动备份',style='Muted.TLabel').pack(anchor='w',padx=14,pady=(16,10))
    main=ttk.Frame(shell);main.pack(side='left',fill='both',expand=True)
    cards=ttk.Frame(main);cards.pack(fill='x',pady=(0,14))
    app.card_vars={}
    for i,(key,title,value,color) in enumerate((
        ('manager','管理器','当前 v'+core.VERSION,CYAN),
        ('plugin','引擎插件','等待选择工程','#8aafff'),
        ('shared','共享词库','等待检查更新','#b4a3ff'))):
        cards.columnconfigure(i,weight=1,uniform='cards')
        card=ttk.Frame(cards,style='Panel.TFrame',padding=(14,11))
        card.grid(row=0,column=i,sticky='nsew',padx=(0,10 if i<2 else 0))
        top=ttk.Frame(card,style='Panel.TFrame');top.pack(fill='x')
        ttk.Label(top,text=title,style='PanelMuted.TLabel').pack(side='left')
        tk.Label(top,text='●',bg=PANEL,fg=color,font=('Segoe UI',9)).pack(side='right')
        app.card_vars[key]=tk.StringVar(value=value)
        ttk.Label(card,textvariable=app.card_vars[key],style='Card.TLabel',wraplength=190).pack(anchor='w',pady=(6,0))
    context=ttk.Frame(main);context.pack(fill='x',pady=(0,10))
    app.path_row(context,'目标工程',app.project,app.choose_project,label_width=9)
    app.path_row(context,'虚幻引擎',app.engine,lambda:app.choose_dir(app.engine),label_width=9)
    row=ttk.Frame(context);row.pack(fill='x',pady=(2,0))
    ttk.Checkbutton(row,text='根据工程自动识别 UE',variable=app.auto_engine,command=app.toggle_auto_engine).pack(side='left')
    ttk.Button(row,text='从工程识别',style='Ghost.TButton',command=lambda:app.detect_project_engine(manual=True)).pack(side='right')
    ttk.Label(context,textvariable=app.engine_status,style='Muted.TLabel',wraplength=760).pack(anchor='w')
    ttk.Separator(main).pack(fill='x',pady=(6,14))
    footer=ttk.Frame(main);footer.pack(side='bottom',fill='x',pady=(10,0))
    statusrow=ttk.Frame(footer);statusrow.pack(fill='x')
    ttk.Label(statusrow,textvariable=app.status,wraplength=540,style='Muted.TLabel').pack(side='left',fill='x',expand=True)
    app.progress=ttk.Progressbar(footer,mode='indeterminate');app.progress.pack(fill='x',pady=(8,0))
    logpanel=ttk.Frame(footer)
    app.logbox=tk.Text(logpanel,height=4,font=('Consolas',9),state='disabled',wrap='word',
        background='#060b13',foreground='#9dc5e5',insertbackground=CYAN,relief='flat',
        highlightthickness=1,highlightbackground=LINE,padx=10,pady=6)
    app.logbox.pack(fill='x',pady=(8,0))
    def toggle_log():
        if logpanel.winfo_manager():logpanel.pack_forget();logbutton.configure(text='日志 +')
        else:logpanel.pack(fill='x');logbutton.configure(text='日志 −')
    logbutton=ttk.Button(statusrow,text='日志 +',style='Ghost.TButton',command=toggle_log);logbutton.pack(side='right')
    book=ttk.Notebook(main,style='Body.TNotebook');book.pack(fill='both',expand=True)
    app.book=book
    # A bounded page viewport keeps all controls reachable at smaller sizes and
    # when the log is expanded. Scrolling is event-driven, with no animation loop.
    pages=[]
    for _ in range(3):
        outer=ttk.Frame(book)
        canvas=tk.Canvas(outer,bg=BG,highlightthickness=0,width=1,height=1)
        scrollbar=ttk.Scrollbar(outer,orient='vertical',command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
        page=ttk.Frame(canvas,padding=(2,0,12,8))
        item=canvas.create_window(0,0,anchor='nw',window=page)
        canvas.bind('<Configure>',lambda e,c=canvas,i=item:c.itemconfigure(i,width=e.width))
        page.bind('<Configure>',lambda e,c=canvas:c.configure(scrollregion=c.bbox('all')))
        def wheel(event,c=canvas):
            if c.yview()!=(0.0,1.0):c.yview_scroll(-int(event.delta/120),'units')
        canvas.bind('<MouseWheel>',wheel)
        pages.append((outer,page,wheel))
    install,shared,buildpage=[p[1] for p in pages]
    buttons=[]
    def navigate(index):
        book.select(index)
        for i,b in enumerate(buttons):b.configure(style='Active.Nav.TButton' if i==index else 'Nav.TButton')
    app.navigate=navigate
    for i,(page,name) in enumerate(((install,'安装与更新'),(shared,'词库与备份'),(buildpage,'引擎编译'))):
        book.add(pages[i][0],text=name)
        b=ttk.Button(nav,text=f'0{i+1}   {name}',style='Nav.TButton',command=lambda i=i:navigate(i))
        b.pack(fill='x',pady=4);buttons.append(b)
    navigate(0)

    heading(install,'01  /  DEPLOY','安装与更新','选择工程，自动识别引擎；已有适配包可直接使用。')
    actions=ttk.Frame(install);actions.pack(fill='x',pady=(0,10))
    ttk.Button(actions,text='检查更新',command=lambda:app.check(True,compatibility=True)).pack(side='left',padx=(0,8))
    ttk.Button(actions,text='安装 / 更新插件  →',style='Accent.TButton',command=app.install).pack(side='left',padx=(0,8))
    ttk.Button(actions,text='只下载安装包',command=app.download_plugin).pack(side='left')
    app.package_label=tk.StringVar(value='尚未检查匹配版本。')
    ttk.Label(install,textvariable=app.package_label,wraplength=760).pack(anchor='w',pady=(4,12))
    ttk.Checkbutton(install,text='启动时检测适配和更新，下载或编译前询问',variable=app.auto_check,command=app.save_settings).pack(anchor='w')
    app.manager_button=ttk.Button(install,text='下载并打开新版工具',command=app.update_manager,state='disabled')
    app.manager_button.pack(anchor='w',pady=(10,12))
    ttk.Separator(install).pack(fill='x',pady=(0,12))
    app.path_row(install,'更新来源',app.feed_var,app.choose_feed,label_width=9,button_text='本地清单')
    ttk.Button(install,text='使用随包离线版本',style='Ghost.TButton',command=app.use_bundled).pack(anchor='w')
    ttk.Label(install,text='安装前自动备份旧插件，保留个人词典。\nUE 正在运行时会询问是否正常关闭，请先保存工作。',
              style='Muted.TLabel',wraplength=760).pack(anchor='w',pady=(10,0))

    heading(shared,'02  /  LIBRARY','词库与备份','共享词库开箱即用，个人译文优先。')
    row=ttk.Frame(shared);row.pack(fill='x')
    ttk.Button(row,text='更新共享词库  →',style='Accent.TButton',command=app.update_defaults).pack(side='left')
    ttk.Label(row,text='保留你的个人译文',style='Muted.TLabel').pack(side='left',padx=14)
    app.shared_label=tk.StringVar(value='检查更新后显示词库版本和词条数量。')
    ttk.Label(shared,textvariable=app.shared_label,wraplength=760).pack(anchor='w',pady=(10,16))
    ttk.Separator(shared).pack(fill='x',pady=(0,16))
    ttk.Label(shared,text='个人词典',style='Section.TLabel').pack(anchor='w')
    ttk.Label(shared,text='替换会覆盖所选个人文件；操作前自动备份，可随时恢复。',style='Muted.TLabel').pack(anchor='w',pady=(5,10))
    pick=ttk.Frame(shared);pick.pack(anchor='w')
    for value,label in [('both','词条 + 长文本'),('term','仅词条'),('long','仅长文本')]:
        ttk.Radiobutton(pick,text=label,variable=app.selection,value=value).pack(side='left',padx=(0,22))
    row=ttk.Frame(shared);row.pack(anchor='w',pady=12)
    for text,fn in [('备份当前文件',app.backup),('从更新源替换',app.shared),('离线包替换',app.shared_offline),('恢复备份',app.restore)]:
        ttk.Button(row,text=text,command=fn).pack(side='left',padx=(0,8))
    ttk.Button(shared,text='打开词典与备份目录  ↗',style='Ghost.TButton',command=app.open_folders).pack(anchor='w')

    heading(buildpage,'03  /  BUILD','引擎编译','先检测本地与云端版本；需要编译时，为下方“编译目标”生成插件，SDK 仅提供依赖。')
    app.path_row(buildpage,'编译目标',app.build_engine,lambda:app.choose_dir(app.build_engine),label_width=9)
    ttk.Button(buildpage,text='以 SDK 为编译目标',style='Ghost.TButton',command=app.use_sdk_target).pack(anchor='w')
    rows=[('插件源码包',app.source_package,lambda:app.choose_file(app.source_package,[('插件源码包','*.zip')])),
          ('完整 SDK',app.sdk,lambda:app.choose_dir(app.sdk)),
          ('VC 环境',app.vcvars,lambda:app.choose_file(app.vcvars,[('VS 环境脚本','vcvars64.bat')])),
          ('Python',app.python,lambda:app.choose_file(app.python,[('Python','python.exe')])),
          ('输出目录',app.out,lambda:app.choose_dir(app.out))]
    for label,var,fn in rows:app.path_row(buildpage,label,var,fn,label_width=9)
    row=ttk.Frame(buildpage);row.pack(fill='x',pady=(6,10))
    ttk.Label(row,text='MSVC 版本',width=9).pack(side='left')
    ttk.Entry(row,textvariable=app.msvc,width=12).pack(side='left',padx=(0,12))
    ttk.Label(row,text='与目标引擎一致，例如 14.50',style='Muted.TLabel').pack(side='left')
    row=ttk.Frame(buildpage);row.pack(anchor='w')
    ttk.Button(row,text='检查编译环境',command=app.check_build).pack(side='left',padx=(0,8))
    ttk.Button(row,text='编译测试包  →',style='Accent.TButton',command=app.compile).pack(side='left')
    app.cancel_build_button=ttk.Button(row,text='取消编译',command=app.cancel_compile,state='disabled')
    app.cancel_build_button.pack(side='left',padx=(8,0))
    row=ttk.Frame(buildpage);row.pack(anchor='w',pady=(8,0))
    ttk.Button(row,text='检测已有版本',command=app.check_cloud).pack(side='left',padx=(0,8))
    ttk.Button(row,text='投稿已有编译包  ↗',command=app.submit_compiled).pack(side='left')
    ttk.Label(buildpage,textvariable=app.cloud_status,style='Muted.TLabel',wraplength=760).pack(anchor='w',pady=(8,0))
    row=ttk.Frame(buildpage);row.pack(anchor='w',pady=(8,0))
    ttk.Button(row,text='Visual Studio  ↗',style='Ghost.TButton',command=lambda:webbrowser.open('https://visualstudio.microsoft.com/visual-cpp-build-tools/')).pack(side='left')
    ttk.Button(row,text='Python  ↗',style='Ghost.TButton',command=lambda:webbrowser.open('https://www.python.org/downloads/windows/')).pack(side='left')
    def bind_wheel(widget,callback):
        widget.bind('<MouseWheel>',callback,add='+')
        for child in widget.winfo_children():bind_wheel(child,callback)
    for _,page,wheel in pages:bind_wheel(page,wheel)
