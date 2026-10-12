"""Editor integration. All UObject/ToolMenus work runs on UE's game thread."""
import json
import hashlib
import os
import time
import traceback
from pathlib import Path
import unreal
from . import core
from .hotkey import ForegroundHotkey

RUNTIME_VERSION = '0.2.11'
PLUGIN = Path(__file__).resolve().parents[3]
SAVE = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir())) / 'XHNodeChinese'
_catalogue = None
_state = None
_tick_handle = None
_last_check = 0.0
_last_codex_check = 0.0
_codex_resources_pending = False
_codex_last_batch = 0.0
_dictionary_stamp = None
_last_error = None
_hotkey = ForegroundHotkey()
_bridge = None
_bridge_error = None
_last_slate = 0.0
_live = None
_live_error = None
_export_status = {'phase':'idle','last_time':'','total':0,'pending':0,'imported':0}
_preloaded = 0
_translator = None
_pending = None
_auto_total = 0
_long_text = None
_last_auto_result = None
_last_live_report = None
_codex = None
_external = None
_last_import_stamp = None
_indexer = None
_indexed = None
_indexed_terms = {}


def status_display(kind):
    if kind == 'capture':
        active=state()['capture_untranslated']
        return {'label':'采集：'+('开' if active else '关'),
                'icon':'Icons.Search',
                'tooltip':('点击关闭' if active else '点击开启')+'未翻译文本采集。关闭后保留已有汉化、中英文搜索和译文导入，停止新增待译记录并降低后台扫描频率。开启后打开菜单即可采集节点说明；悬浮说明关闭后也不会丢失。'}
    if kind == 'codex':
        if state()['translation_provider']=='codex':return codex_session().display()
        from .multi_translate import PROVIDERS
        session=external_session()
        if session.state.get('provider')==state()['translation_provider']:return session.display()
        return {'label':PROVIDERS[state()['translation_provider']][0]+'翻译','tooltip':'点击开始；可在节点汉化 → 翻译方式中选择网页工具、API 或 Codex。','icon':'Icons.Comment'}
    if kind == 'auto':
        active=state()['auto_translate']
        detail=f'本次会话自动写入 {_auto_total} 条。'
        if _last_auto_result:
            detail+=f" 上次手动执行：新增 {_last_auto_result['written']} 条，待译 {_last_auto_result['before']} → {_last_auto_result['after']} 条。"
        return {'label':'自动翻译：'+('开' if active else '关'),
                'icon':'AutomationTools.MenuIcon',
                'tooltip':('点击关闭' if active else '点击开启')+'本地自动翻译。'+detail+'\n只复用本地完整译文。未知词条和长文本可选择网页、API 或 Codex 翻译，也可手动填写。'}
    if kind == 'language':
        if _bridge_error or _last_error:
            return {'label':'汉化：异常', 'icon':'Icons.Warning', 'tooltip':str(_bridge_error or _last_error)}
        active=state()['enabled']
        label='已启用' if active else '已停用'
        return {'label':'汉化：'+label,'icon':'Icons.Localization',
                'tooltip':f'当前：{label}；已预加载 {_preloaded} 条缓存。点击或 Ctrl+Alt+L 启用／停用汉化；停用恢复启用前语言。'}
    if _live_error or _export_status['phase']=='error':
        return {'label':'导出：异常','icon':'Icons.Warning','tooltip':str(_live_error or _export_status.get('error','导出失败'))}
    phase=_export_status['phase']
    mode='导出中' if phase=='writing' else ('采集中' if state()['live_export'] and state()['capture_untranslated'] else '已暂停')
    if time.monotonic() < _export_status.get('notice_until',0):
        mode=f"已导出 {_export_status['last_manual_count']} 条"
    return {'label':f"导出：{mode} · {_export_status['pending']} 待译",'icon':'Icons.Toolbar.Export',
            'tooltip':f"最近写入：{_export_status['last_time'] or '尚无'}\n实时待译 {_export_status['pending']} 条；已填写保留 {_export_status['total']-_export_status['pending']} 条；本次会话已导入 {_export_status['imported']} 条。\n手动导出文件待译：{_pending.pending if _pending else 0} 条。\n点击打开实时词条；数量按去重后的基础词条计算。"}


def state():
    global _state
    if _state is None:
        path = SAVE / 'settings.json'
        try:
            _state = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        except (ValueError, OSError):
            _state = {}
        _state.setdefault('enabled', True)
        _state.setdefault('bilingual', False)
        _state.setdefault('live_export', True)
        _state.setdefault('capture_untranslated', False)
        _state.setdefault('auto_translate', True)
        _state.setdefault('translation_provider', 'codex' if (SAVE/'CodexConnection.json').exists() else 'doubao')
        if _state['translation_provider'] not in ('codex','doubao','deepseek','manual','api'):_state['translation_provider']='doubao'
    return _state


def save_state():
    core.write_json(SAVE / 'settings.json', state())


def catalogue(force=False):
    global _catalogue
    if _catalogue is None or force:
        engine = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.engine_dir()))
        signature = [(str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in core.resources(engine)]
        cache = SAVE / 'catalogue.json'
        try:
            saved = json.loads(cache.read_text(encoding='utf-8')) if cache.exists() and not force else {}
        except (ValueError, OSError):
            saved = {}
        if saved.get('signature') == [list(item) for item in signature]:
            _catalogue = saved['entries']
        else:
            _catalogue = core.build_catalogue(engine)
            core.write_json(cache, {'signature': signature, 'entries': _catalogue})
    return _catalogue


def supplemental_terms():
    return dict(_indexed_terms, **(_long_text.terms if _long_text else {}))


def dictionary_stamp():
    return tuple((PLUGIN / 'Dictionaries' / name).stat().st_mtime_ns if (PLUGIN / 'Dictionaries' / name).exists() else 0 for name in ('Base.csv','Graph.csv','UI.csv','Descriptions.csv','Shared.csv','SharedLongText.csv','User.csv'))


def refresh_language():
    library = unreal.InternationalizationLibrary
    old = library.get_current_language()
    if 'previous_language' not in state() and old != core.CULTURE:
        state()['previous_language'] = old
        save_state()
    # Changing language asks UE to reload localization resources. Locale stays intact.
    if old == core.CULTURE:
        library.set_current_language('zh-Hans', False)
    if not library.set_current_language(core.CULTURE, False):
        library.set_current_language(old, False)
        raise RuntimeError('This UE build did not accept zh-Hans-CN')


def rebuild(force=False):
    global _dictionary_stamp, _translator, _codex_resources_pending
    report = core.compile_dictionary(PLUGIN, catalogue(force), bilingual=state()['bilingual'])
    core.write_json(SAVE / 'report.json', report)
    user_data = (PLUGIN / 'Dictionaries/User.csv').read_bytes()
    backup_name = hashlib.sha256(user_data).hexdigest()[:16] + '.csv'
    backup = SAVE / 'DictionaryBackups' / backup_name
    if not backup.exists():
        core.atomic_write(backup, user_data)
    _dictionary_stamp = dictionary_stamp()
    if state()['enabled']:
        refresh_language()
    if _bridge is not None:
        _bridge.rebuild(PLUGIN, state()['enabled'], state()['bilingual'], supplemental_terms())
        _bridge.collect(state()['capture_untranslated'])
        _bridge.tick()
    from .auto_translate import Translator
    from .bridge import dictionary
    _translator = Translator(catalogue(), dictionary(PLUGIN))
    _codex_resources_pending = False
    unreal.log(f"[XHNodeChinese] {report['translated_entries']} translations; {report['categories']}")
    return report


def enable():
    if not state()['enabled']:
        old=unreal.InternationalizationLibrary.get_current_language()
        if old != core.CULTURE:
            state()['previous_language']=old
    state()['enabled'] = True
    rebuild()
    save_state()


def disable():
    state()['enabled'] = False
    save_state()
    previous = state().get('previous_language', 'zh-Hans')
    if previous == core.CULTURE:
        previous = 'zh-Hans'
    unreal.InternationalizationLibrary.set_current_language(previous, False)
    if _bridge is not None:
        _bridge.enable(False, False)
    unreal.log('[XHNodeChinese] Disabled; previous language restored.')


def toggle_enabled():
    if state()['enabled']:disable()
    else:enable()


def toggle_language():
    # Compatibility for toolbar UObjects already registered by 0.1.5.
    toggle_enabled()


def toggle_bilingual():
    state()['bilingual'] = not state()['bilingual']
    rebuild()
    save_state()


def edit_dictionary():
    # Explicit menu action opens the user's CSV in Notepad, preserving UTF-8.
    import subprocess
    subprocess.Popen(['notepad.exe', str(PLUGIN / 'Dictionaries/User.csv')])


def import_stamp():
    return tuple((p.stat().st_mtime_ns,p.stat().st_size) if p.exists() else None
                 for p in (SAVE/'Live.csv',SAVE/'Pending.csv',SAVE/'LongText.csv'))


def toggle_capture():
    state()['capture_untranslated']=not state()['capture_untranslated']
    if state()['capture_untranslated']:state()['live_export']=True
    save_state()
    if _bridge is not None:_bridge.collect(state()['capture_untranslated'])
    # Flush already captured text once when pausing; never discard a short hover.
    live_sync(automatic=False)
    unreal.log('[XHNodeChinese] 未译文本采集：'+('开启' if state()['capture_untranslated'] else '关闭'))


def live_sync(capture=True,automatic=None):
    global _live, _pending, _auto_total, _last_live_report, _last_import_stamp, _indexed
    from .live import LiveSession
    if _live is None:
        _live = LiveSession(PLUGIN, SAVE)
    current = _bridge.current() if capture and _bridge is not None else []
    captured_count=len(current)
    sync_long_text(current)
    # Partially translated descriptions remain available for a full translation.
    exact = _bridge.known_terms if _bridge is not None else {}
    translator = _translator if (state()['auto_translate'] if automatic is None else automatic) else None
    report = _live.sync(current, exact, translator=translator, separate_long=True)
    if (SAVE/'Pending.csv').exists():
        if _pending is None:_pending=LiveSession(PLUGIN,SAVE,'Pending.csv')
        # A legacy full-engine export may contain thousands of unseen labels.
        # Import its manual edits, but auto-translate only the live/current queue.
        pending_report=_pending.sync([],exact)
        report['imported']+=pending_report['imported']
        report['automatic']+=pending_report['automatic']
    if (SAVE/'Indexed.csv').exists():
        if _indexed is None:_indexed=LiveSession(PLUGIN,SAVE,'Indexed.csv')
        index_report=_indexed.sync([],exact,separate_long=True)
        report['imported']+=index_report['imported']
    _auto_total += report['automatic']
    _export_status.update(total=report['total'],pending=report['pending'],imported=_live.imported+(_pending.imported if _pending else 0))
    if report['new'] or report['imported'] or report['removed']:
        _export_status['last_time']=time.strftime('%H:%M:%S')
    if report['imported']:
        rebuild()
        if _bridge is not None:
            _bridge.tick()
        # Pending.csv imports may resolve Live.csv entries in the same click.
        cleaned=_live.sync([], _bridge.known_terms if _bridge else {}, separate_long=True)
        report.update(total=cleaned['total'],pending=cleaned['pending'])
        _export_status.update(total=report['total'],pending=report['pending'])
    _last_live_report=report
    if capture and _bridge is not None:_bridge.ack_capture(captured_count)
    _last_import_stamp=import_stamp()
    write_diagnostics(report)
    return _live.path


def write_diagnostics(live_report=None, detailed=False):
    rows = core.load_dictionary(PLUGIN / 'Dictionaries/User.csv')
    current = _bridge.current() if _bridge is not None and detailed else []
    pairs = _bridge.bindings() if _bridge is not None and detailed else []
    personal = _bridge.personal if _bridge is not None else {}
    data = {'version':RUNTIME_VERSION, 'time':time.strftime('%Y-%m-%d %H:%M:%S'),
            'codex_poll_interval_ms':250,
            'capture_untranslated':state()['capture_untranslated'],
            'native_scan_ms':_bridge.dll.XH_ScanMs() if _bridge else None,
            'graph_search':_bridge.graph_index(detailed) if _bridge else None,
            'niagara_search':_bridge.search_index(detailed) if _bridge else None,
            'parameter_search':_bridge.parameter_index() if _bridge else None,
            'enabled':state()['enabled'], 'language':unreal.InternationalizationLibrary.get_current_language(),
            'dictionary_path':str(PLUGIN / 'Dictionaries/User.csv'),
            'dictionary_rows':len(rows), 'personal_display_terms':len(personal),
            'bridge_loaded':_bridge is not None, 'bridge_error':_bridge_error,
            'live_export':state()['live_export'], 'live_error':_live_error,
            'current_text_count':_bridge.dll.XH_CurrentCount() if _bridge else 0, 'bound_widgets':_bridge.count if _bridge else 0,
            'personal_exact_hits':[p for p in pairs if p['source'] in personal],
            'bindings':pairs, 'unmatched_current':[s for s in current if _bridge.preview(s)==s] if _bridge else [],
            'overview_bindings':[p for p in pairs if p['area']=='NiagaraOverview'],
            'preloaded_terms':_preloaded, 'scan_interval_ms':100 if state()['capture_untranslated'] else 250,
            'auto_translate':state()['auto_translate'], 'auto_written':_auto_total,
            'long_text':_long_text.status() if _long_text else None,
            'toolbar_status':{kind:status_display(kind) for kind in ('language','capture','auto','codex','export')},
            'codex_translation':codex_session().state,
            'translation_provider':state()['translation_provider'],
            'external_translation':external_session().state,
            'last_auto_result':_last_auto_result,
            'live':live_report if live_report is not None else _last_live_report}
    core.write_json(SAVE / 'LiveStatus.json', data)
    return SAVE / 'LiveStatus.json'


def open_live():
    state()['live_export'] = True
    state()['capture_untranslated'] = True
    if _bridge is not None:_bridge.collect(True)
    save_state()
    path = live_sync()
    import subprocess
    subprocess.Popen(['notepad.exe', str(path)])


def toggle_live():
    state()['live_export'] = not state()['live_export']
    if not state()['live_export']:
        state()['capture_untranslated']=False
        if _bridge is not None:_bridge.collect(False)
    save_state()
    unreal.log('[XHNodeChinese] 实时导出：' + ('已开启' if state()['live_export'] else '已暂停'))


def toggle_auto():
    state()['auto_translate']=not state()['auto_translate']
    save_state()
    write_diagnostics()
    unreal.log('[XHNodeChinese] 本地自动翻译：'+('已开启' if state()['auto_translate'] else '已关闭'))


def sync_long_text(current=(),include_known=False,apply_bridge=True):
    global _long_text
    from .long_text import LongTextSession
    from .bridge import dictionary
    if _long_text is None:_long_text=LongTextSession(SAVE)
    sources=set(current)
    if (SAVE/'Live.csv').exists():
        sources.update(r['Source'] for r in core.load_dictionary(SAVE/'Live.csv',True) if not r['Translation'])
    if _long_text.sync(sources,dictionary(PLUGIN,_indexed_terms),include_known=include_known) and _bridge is not None and apply_bridge:
        _bridge.rebuild(PLUGIN,state()['enabled'],state()['bilingual'],supplemental_terms())
        _bridge.tick()


def edit_long_text():
    sources=_bridge.observed() if _bridge else []
    sync_long_text(sources,include_known=True)
    import subprocess
    subprocess.Popen(['notepad.exe',str(_long_text.path)])


def translate_current(show_dialog=True):
    global _last_auto_result
    rebuild()
    live_sync(automatic=False)
    before=_live.pending;written_before=_auto_total
    live_sync(automatic=True)
    result={'before':before,'after':_live.pending,'written':_auto_total-written_before,
            'resolved':max(0,before-_live.pending)}
    _last_auto_result=result
    write_diagnostics()
    message=(f"本次新增个人译文：{result['written']} 条\n实时待译：{before} → {result['after']} 条\n"
             f"已减少待译：{result['resolved']} 条\n\n"
             '未减少的词条在本地词库中没有完整译文，请手动填写；不会调用大模型。\n'
             '相同基础名称的数字编号已合并计数。实时文件已更新，已打开的记事本请重新打开查看。')
    unreal.log('[XHNodeChinese] '+message)
    if show_dialog:unreal.EditorDialog.show_message('本次自动翻译结果',message,unreal.AppMsgType.OK)
    return result


def codex_session():
    global _codex
    if _codex is None:
        from .codex_translate import Session
        _codex=Session(PLUGIN,SAVE)
    return _codex


def external_session():
    global _external
    if _external is None:
        from .multi_translate import Session
        _external=Session(PLUGIN,SAVE)
    return _external


def choose_translation(provider):
    from .multi_translate import PROVIDERS
    if provider not in PROVIDERS:raise ValueError('未知翻译方式')
    for session in (codex_session(),external_session()):
        if session.state['phase'] in ('sending','waiting','error') and session.state.get('folder'):
            active='codex' if session is codex_session() else session.state.get('provider')
            if provider!=active:
                unreal.EditorDialog.show_message('翻译任务尚未结束','请先完成当前翻译，或选择“停止当前翻译接收”，再切换方式。',unreal.AppMsgType.OK)
                return
    state()['translation_provider']=provider;save_state();write_diagnostics()


def translate_selected(include_export=False,show_dialog=True):
    provider=state()['translation_provider']
    if provider=='codex':return translate_with_codex(include_export,show_dialog)
    from . import multi_translate,clipboard
    try:
        session=external_session()
        config=multi_translate.api_config(SAVE) if provider=='api' else None
        live_sync()
        from .bridge import dictionary
        known=_bridge.known_terms if _bridge else dictionary(PLUGIN,supplemental_terms())
        if not session.prepare(known,provider,include_export):
            if show_dialog:unreal.EditorDialog.show_message('翻译','当前没有新的待译词条或长文本。',unreal.AppMsgType.OK)
            return False
        if provider=='api':return session.start_api(config)
        register_menus()
        text,path=session.web_prompt()
        try:clipboard.copy(text)
        except RuntimeError:
            import subprocess
            subprocess.Popen(['notepad.exe',str(path)])
            if show_dialog:unreal.EditorDialog.show_message('请从文件复制','剪贴板暂不可用，已打开任务文本。复制全部内容到翻译工具，得到回答后复制 JSON，并点击“粘贴并导入网页译文”。',unreal.AppMsgType.OK)
            return True
        url=multi_translate.PROVIDERS[provider][1]
        if url:unreal.SystemLibrary.launch_url(url)
        if show_dialog:unreal.EditorDialog.show_message('翻译任务已复制','在网页对话框粘贴并发送。回答完成后复制回答（JSON 或表格），再选择“节点汉化 → 粘贴译文”。\n每次复制一批，导入后再点击翻译按钮复制下一批。网页免费额度与登录要求以服务商为准。',unreal.AppMsgType.OK)
        return True
    except Exception as error:
        if show_dialog:unreal.EditorDialog.show_message('翻译未开始',str(error),unreal.AppMsgType.OK)
        else:raise
        return False


def import_web_translation():
    from . import clipboard
    try:
        count=external_session().accept_text(clipboard.paste())
        unreal.EditorDialog.show_message('已接收译文',f'已接收 {count} 条。缺失或校验失败的词条保留待译。\n点击“开始／继续翻译”即可补齐剩余项；详情见“任务进度”。',unreal.AppMsgType.OK)
    except Exception as error:unreal.EditorDialog.show_message('译文未导入',str(error),unreal.AppMsgType.OK)


def open_translation_files():
    session=codex_session() if state()['translation_provider']=='codex' else external_session()
    folder=Path(session.state['folder']) if session.state.get('folder') else SAVE/'TranslationRequests'
    folder.mkdir(parents=True,exist_ok=True)
    os.startfile(str(folder))


def show_translation_progress():
    session=codex_session() if state()['translation_provider']=='codex' else external_session()
    info=session.state
    phase={'waiting':'等待译文','sending':'提交中','cancelled':'已暂停，可继续','error':'需要处理','done':'已完成','idle':'尚未开始','empty':'没有待译词条'}.get(info['phase'],info['phase'])
    current=external_session().current_batch() if session is external_session() else None
    message=f"{phase} · 已处理 {info.get('completed',0)}/{info.get('total',0)} 条"
    if current: message+=f"\n当前第 {current[0]} 批，剩余 {len(current[1]['items'])} 条"
    if info.get('error'):message+='\n'+str(info['error'])
    folder=Path(info['folder']) if info.get('folder') else None
    if folder and (folder/'ImportReport.json').exists():
        report=json.loads((folder/'ImportReport.json').read_text(encoding='utf-8'))
        message+='\n最近导入：'+str(report.get('error') or f"接收 {report.get('accepted',0)} 条，剩余 {report.get('remaining',0)} 条")
        for row in report.get('rejected',[])[:3]:message+='\n'+row['source'][:40]+'：'+row['reason']
    message+='\n\n关闭编辑器也会保存进度。点击“开始／继续翻译”接着翻，不必找旧回答。\n任务文件夹保留每次复制的回答、请求和导入报告。'
    unreal.EditorDialog.show_message('翻译任务进度',message,unreal.AppMsgType.OK)


def scan_unopened():
    global _indexer
    from .asset_index import Indexer
    if _indexer and _indexer.phase=='paused':
        _indexer.resume();return
    if _indexer and _indexer.phase in ('waiting','scanning','deep'):
        unreal.EditorDialog.show_message('模块索引',_indexer.label(),unreal.AppMsgType.OK);return
    _indexer=Indexer(PLUGIN,SAVE,catalogue())
    unreal.log('[XHNodeChinese] 已开始索引未打开模块；完成后点击翻译按钮处理剩余英文。')


def pause_module_index():
    if _indexer:_indexer.pause()


def show_index_status():
    path=SAVE/'ModuleIndexStatus.json'
    data=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    message=_indexer.label() if _indexer else '尚未扫描；选择“扫描未打开模块”开始。'
    if data:message+='\n已匹配本地译文：'+str(data.get('matched',0))+'\n待翻译：'+str(data.get('pending',0))+'\n内部模块进度：'+str(data.get('deep_position',0))+'/'+str(data.get('deep_total',0))+'\n新增内部文本：'+str(data.get('deep_sources',0))+'\n读取失败：'+str(len(data.get('failed_assets',{})))
    unreal.EditorDialog.show_message('模块覆盖情况',message,unreal.AppMsgType.OK)


def configure_translation_api(preset='deepseek'):
    from .multi_translate import configure_api
    import subprocess
    path=configure_api(SAVE,preset)
    subprocess.Popen(['notepad.exe',str(path)])
    unreal.EditorDialog.show_message('配置翻译 API','填写 endpoint（完整接口地址）、model（模型或接入点 ID）、api_key 后保存。也可用 api_key_env 指定环境变量名称。\n已有配置会保留。选择“自配 API”后点击工具栏翻译按钮开始；API 可能收费。\n豆包网页账号不等于火山方舟 API 密钥。配置只存当前工程 Saved 目录，不包含在插件分发包中。',unreal.AppMsgType.OK)


def stop_translation():
    external_session().cancel();codex_session().cancel();write_diagnostics();register_menus()


def translate_with_codex(include_export=False,show_dialog=True):
    try:
        session=codex_session()
        if session.state['phase'] in ('sending','waiting'):
            from . import codex_translate
            config=codex_translate.connection(SAVE)
            if not config.get('thread_id'):
                copy_codex_request(); return False
            if show_dialog:unreal.EditorDialog.show_message('Codex 翻译',session.display()['tooltip'],unreal.AppMsgType.OK)
            return False
        started=time.perf_counter()
        live_sync()
        from .bridge import dictionary
        known=_bridge.known_terms if _bridge else dictionary(PLUGIN,supplemental_terms())
        submitted=session.start(known,include_export)
        if submitted:
            from . import codex_translate, clipboard
            config = codex_translate.connection(SAVE)
            if not config.get('thread_id'):
                folder = Path(session.state['folder'])
                core.atomic_write(folder/'TRANSLATE.md',codex_translate.instructions(folder/'request.json',folder/'response.json').encode('utf-8'))
                text = codex_translate.handoff_text(folder)
                core.atomic_write(folder/'发送给Codex.txt', text.encode('utf-8'))
                try: clipboard.copy(text)
                except RuntimeError:
                    import subprocess
                    subprocess.Popen(['notepad.exe',str(folder/'发送给Codex.txt')])
                opened = codex_translate.open_app(config)
                if show_dialog: unreal.EditorDialog.show_message('请求已准备',
                    '请求路径已复制。在 Codex 对话中粘贴并发送即可，译文将自动导入。\n'+
                    ('已尝试打开本机 Codex。' if opened else '未找到本机 Codex；请手动打开，或在设置中填写程序路径。'), unreal.AppMsgType.OK)
            session.state['button_prepare_ms']=round((time.perf_counter()-started)*1000,2)
            session.persist()
            register_menus()
        write_diagnostics()
        if not submitted and show_dialog:
            unreal.EditorDialog.show_message('Codex 翻译',session.display()['tooltip'] if session.state['phase'] in ('sending','waiting') else '当前没有新的待译词条或长文本。',unreal.AppMsgType.OK)
        return submitted
    except Exception as error:
        codex_session().state.update(phase='error',error=str(error))
        codex_session().persist()
        if show_dialog:unreal.EditorDialog.show_message('Codex 翻译未提交',str(error),unreal.AppMsgType.OK)
        else:raise
        return False


def translate_export_with_codex():
    return translate_with_codex(include_export=True)


def copy_codex_request():
    from . import codex_translate,clipboard
    session=codex_session()
    if not session.state.get('folder'):return translate_with_codex()
    folder=Path(session.state['folder'])
    core.atomic_write(folder/'TRANSLATE.md',codex_translate.instructions(folder/'request.json',folder/'response.json').encode('utf-8'))
    text=codex_translate.handoff_text(folder)
    core.atomic_write(folder/'发送给Codex.txt',text.encode('utf-8'))
    try:clipboard.copy(text)
    except RuntimeError:
        import subprocess
        subprocess.Popen(['notepad.exe',str(folder/'发送给Codex.txt')])
    codex_translate.open_app(codex_translate.connection(SAVE))
    unreal.EditorDialog.show_message('请求路径已复制','在 Codex 对话中粘贴并发送即可。当前请求保留，已导入结果不会丢失。',unreal.AppMsgType.OK)


def translation_history():
    roots={SAVE/'TranslationRequests'}
    from . import codex_translate
    try:roots.add(Path(codex_translate.connection(SAVE)['exchange_dir']))
    except (ValueError,OSError,RuntimeError,KeyError):pass
    paths=set()
    for root in roots:
        if root.is_dir():paths.update(root.glob('*/status.json'));paths.update(root.glob('Codex/*/status.json'))
    result=[]
    for path in sorted(paths,key=lambda p:p.stat().st_mtime,reverse=True)[:12]:
        try:
            info=json.loads(path.read_text(encoding='utf-8'))
            if info.get('folder') and (path.parent/'request.json').is_file():result.append((path,info))
        except (ValueError,OSError):pass
    return result


def restore_translation_task(status_path):
    choices={str(p.resolve()):(p,info) for p,info in translation_history()}
    selected=choices.get(str(Path(status_path).resolve()))
    if not selected:raise ValueError('任务已不在历史列表，请重新打开菜单')
    path,info=selected
    for session in (codex_session(),external_session()):
        if session.state.get('folder')!=info.get('folder') and session.state['phase'] in ('sending','waiting'):
            unreal.EditorDialog.show_message('请先暂停当前任务','从翻译工具中选择“暂停接收译文”，再恢复历史任务。',unreal.AppMsgType.OK);return
    provider=info.get('provider','codex')
    session=codex_session() if provider=='codex' else external_session()
    if session.worker and session.worker.is_alive():
        unreal.EditorDialog.show_message('稍后重试','当前请求正在结束，请稍后恢复任务。',unreal.AppMsgType.OK);return
    session.state=info
    if info['phase'] not in ('done','empty','idle'):session.state.update(phase='cancelled',error=None)
    session._file_stamps.clear();session.persist()
    state()['translation_provider']=provider;save_state()
    show_translation_progress()


def configure_codex():
    from . import codex_translate
    path=SAVE/'CodexConnection.json'
    if not path.exists():
        config=codex_translate.connection(SAVE)
        core.write_json(path, {'cli_path': config['cli_path'], 'thread_id': ''})
    import subprocess
    subprocess.Popen(['notepad.exe',str(path)])
    unreal.EditorDialog.show_message('Codex 设置（可选）',
        '通常无需填写：插件会查找本机 Codex、复制请求路径并打开应用。\n'
        '找不到程序时仅填 cli_path（安装目录或 codex.exe）。thread_id 可留空。\n'
        '高级：填写指定聊天 ID 后，点击翻译会直接发送到该聊天。原有连接配置继续有效。',unreal.AppMsgType.OK)


def cancel_codex():
    codex_session().cancel()
    write_diagnostics()
    unreal.log('[XHNodeChinese] 已停止接收本次译文；Codex 聊天中的翻译任务可能仍在运行。')


def optimize_dictionary():
    from . import personal
    report=personal.update(PLUGIN,SAVE)
    core.write_json(SAVE/'DictionaryOptimization.json',report)
    rebuild()
    unreal.log(f"[XHNodeChinese] 词典整理：{report['before']} → {report['after']} 条，删除 {report['removed']} 条冗余；原文件已备份。")
    return report


def diagnose():
    if _bridge is not None:
        _bridge.tick()
    path = write_diagnostics(detailed=True)
    import subprocess
    subprocess.Popen(['notepad.exe', str(path)])
    return path


def export_untranslated(all_entries=False):
    path = SAVE / 'Pending.csv'
    observed = _bridge.observed() if _bridge is not None else []
    _export_status['phase']='writing'
    try:
        live_sync()
        count = core.export_pending(PLUGIN, catalogue(), path, observed=observed, current_only=not all_entries)
    except Exception as error:
        _export_status.update(phase='error',error=str(error))
        raise
    _export_status.update(phase='idle',last_time=time.strftime('%H:%M:%S'),last_manual_count=count,notice_until=time.monotonic()+8)
    import subprocess
    try:
        subprocess.Popen(['notepad.exe', str(path)])
    except OSError as error:
        unreal.EditorDialog.show_message('待翻译词条已导出', f'{count} 条\n{path}\n\n记事本未能打开，请手动打开以上文件。\n{error}', unreal.AppMsgType.OK)
    else:
        unreal.log(f'[XHNodeChinese] 已导出 {count} 条并用记事本打开：{path}')
    return path


def show_status():
    report = json.loads((SAVE / 'report.json').read_text(encoding='utf-8')) if (SAVE / 'report.json').exists() else rebuild()
    status = '已启用' if state()['enabled'] else '已停用'
    mode = '中英双语' if state()['bilingual'] else '中文'
    message = (f"状态：{status}｜{mode}\n自定义汉化：{report['translated_entries']} 条\n"
               f"已索引：{report['catalogue_entries']} 条\n"
               f"Niagara / 材质 / 蓝图：{report['categories']}\n\n"
               f"用户词典：{PLUGIN / 'Dictionaries/User.csv'}\n\n"
               f"动态显示：{str(_bridge.count) + ' 个控件' if _bridge is not None else (_bridge_error or '未加载')}\n"
               'Ctrl+Alt+L 启用／停用汉化。支持整条匹配及个人词典短语匹配，仅修改显示。'
               '未匹配文本可导出后补译；资产原名、数值、脚本和可编辑注释不会被写入或改名。'
               '\n如节点仍显示英文，请在编辑器偏好设置中启用“使用本地化的节点和引脚名称”，并重新打开节点编辑器。')
    unreal.EditorDialog.show_message('星河节点汉化', message, unreal.AppMsgType.OK)


MENU_NAMES = ('LevelEditor.MainMenu', 'AssetEditor.Niagara.MainMenu',
              'AssetEditor.NiagaraScriptEditor.MainMenu',
              'AssetEditor.MaterialEditor.MainMenu', 'AssetEditor.BlueprintEditor.MainMenu')


def register_menus():
    from .multi_translate import PROVIDERS
    menus=unreal.ToolMenus.get()
    # Rebuild our owned submenu so old versions cannot leave duplicate entries.
    def add(menu,section,name,label,call,tip=''):
        entry=unreal.ToolMenuEntry(name='XHNodeChinese.'+name,type=unreal.MultiBlockType.MENU_ENTRY)
        entry.set_label(label);entry.set_tool_tip(tip or label)
        entry.set_string_command(unreal.ToolMenuStringCommandType.PYTHON,'','import xh_node_chinese.runtime as xh; xh.'+call)
        menu.add_menu_entry(section,entry)
    for menu_name in MENU_NAMES:
        menus.remove_menu(menu_name+'.XHNodeChinese')
        main=menus.extend_menu(menu_name)
        menu=main.add_sub_menu('XHNodeChinese','Tools','XHNodeChinese','节点汉化','汉化与翻译')
        add(menu,'Quick','ImportWeb','粘贴译文','import_web_translation()','复制网页回答后点这里；支持 JSON、表格、两列 CSV，可分次导入')
        add(menu,'Quick','Progress','任务进度／中断后继续','show_translation_progress()')
        providers=menu.add_sub_menu('XHNodeChinese','Settings','TranslationProviders','翻译工具','选择豆包、DeepSeek、Codex 或 API')
        for provider,(label,url) in PROVIDERS.items():add(providers,'Provider','Provider_'+provider,label,f"choose_translation('{provider}')")
        for name,label,call in [('Files','打开当前任务文件夹','open_translation_files()'),('Stop','暂停接收译文','stop_translation()'),
            ('CodexCopy','复制 Codex 请求路径','copy_codex_request()'),('CodexConfig','Codex 设置（可选）','configure_codex()'),('ApiDeepSeek','API 设置：DeepSeek',"configure_translation_api('deepseek')"),
            ('ApiDoubao','API 设置：豆包',"configure_translation_api('doubao')"),('ApiCustom','API 设置：其他',"configure_translation_api('custom')")]:
            add(providers,'Settings',name,label,call)
        history=providers.add_sub_menu('XHNodeChinese','Tasks','History','找回历史翻译任务','任务日期、进度与工具')
        for index,(path,info) in enumerate(translation_history()):
            stamp=time.strftime('%m-%d %H:%M',time.localtime(info.get('started_at',path.stat().st_mtime)))
            label=f"{stamp} · {info.get('provider','codex')} · {info.get('completed',0)}/{info.get('total',0)}"
            add(history,'History','History'+str(index),label,'restore_translation_task('+repr(str(path))+')')
        dictionaries=menu.add_sub_menu('XHNodeChinese','Settings','Dictionaries','词典与覆盖','编辑词典、补齐未打开模块')
        for name,label,call in [('Edit','编辑个人词典','edit_dictionary()'),('Long','编辑长文本翻译','edit_long_text()'),
            ('Scan','扫描未打开模块','scan_unopened()'),('Coverage','查看模块覆盖情况','show_index_status()'),
            ('PauseScan','暂停模块扫描','pause_module_index()'),
            ('Optimize','整理重复词条','optimize_dictionary()')]:add(dictionaries,'Dictionary',name,label,call)
        advanced=menu.add_sub_menu('XHNodeChinese','Settings','Advanced','高级选项','导出、双语和诊断')
        for name,label,call in [('Bilingual','中文／中英双语','toggle_bilingual()'),('Auto','开关本地译文复用','toggle_auto()'),
            ('Translate','立即复用本地译文','translate_current()'),('Live','打开实时待译词条','open_live()'),
            ('Export','导出当前待译词条','export_untranslated()'),('ExportAll','导出全部语言资源','export_all()'),
            ('TranslateAll','翻译全部历史导出','translate_selected(include_export=True)'),('Rebuild','重建语言资源索引','rescan()'),
            ('Diagnose','查看命中诊断','diagnose()'),('Status','使用说明与文件位置','show_status()')]:add(advanced,'Advanced',name,label,call)
    from . import status_ui_029 as status_ui
    status_ui.register()
    menus.refresh_all_widgets()


def rescan():
    rebuild(force=True)


def export_all():
    return export_untranslated(all_entries=True)


def tick(delta):
    global _last_check, _last_codex_check, _dictionary_stamp, _last_error, _last_slate, _live_error
    global _codex_resources_pending, _codex_last_batch, _indexed_terms
    if _hotkey.pressed():
        toggle_enabled()
    now = time.monotonic()
    if _indexer and _indexer.phase in ('waiting','scanning','deep'):
        try:
            if _indexer.step():
                _indexed_terms={r['Source']:r['Translation'] for r in core.load_dictionary(SAVE/'IndexedTranslations.csv')}
                sync_long_text(apply_bridge=False)
                rebuild()
                write_diagnostics()
                unreal.log('[XHNodeChinese] '+_indexer.label())
        except Exception as error:
            _indexer.phase='error'; _indexer.error=str(error); _indexer.persist()
            unreal.log_warning('[XHNodeChinese] 模块索引失败：'+str(error))
    # Response detection is cheap and independent of the slower capture cycle.
    # Heavy dictionary work only runs when a new, validated batch was imported.
    if now-_last_codex_check>=0.25:
        _last_codex_check=now
        try:
            changes=[]
            for session in (codex_session(),external_session()):
                try:changes.append(session.poll())
                except Exception as error:
                    session.state.update(phase='error',error=str(error));session.persist();changes.append(False)
            codex_changed,external_changed=changes
            if codex_changed or external_changed:
                sync_long_text(apply_bridge=False)
                if _bridge is not None:
                    # Publish complete translations now; compiling every locres
                    # after every small batch delays even the visible Slate text.
                    _bridge.rebuild(PLUGIN,state()['enabled'],state()['bilingual'],supplemental_terms())
                    _bridge.tick()
                    _dictionary_stamp=dictionary_stamp()
                    _codex_resources_pending=True
                    _codex_last_batch=time.monotonic()
                else:rebuild()
                live_sync(capture=False,automatic=False)
                unreal.log('[XHNodeChinese] '+(external_session() if external_changed else codex_session()).display()['tooltip'])
        except Exception as error:
            codex_session().state.update(phase='error',error=str(error))
            codex_session().persist()
    # Native pre-tick scanning updates controls before paint at up to 20 Hz.
    if now - _last_check < 3:
        return
    _last_check = now
    try:
        stamp = dictionary_stamp()
        if stamp != _dictionary_stamp:
            # Remember failed versions too; do not spam logs or repeatedly reload.
            _dictionary_stamp = stamp
            rebuild()
        elif _codex_resources_pending:
            # Merge resource refreshes while streaming, allow a painted frame
            # first, and flush after completion or a quiet interval.
            quiet=time.monotonic()-_codex_last_batch
            if quiet>=1 and (all(s.state['phase'] not in ('sending','waiting') for s in (codex_session(),external_session())) or quiet>=5):
                rebuild()
        _last_error = None
    except Exception:
        message = traceback.format_exc()
        if message != _last_error:
            unreal.log_error('[XHNodeChinese] Dictionary not applied; previous resource retained.\n' + message)
            _last_error = message
    try:
        if state()['capture_untranslated'] and state()['live_export'] or import_stamp()!=_last_import_stamp:
            live_sync(capture=state()['live_export'],automatic=None if state()['capture_untranslated'] else False)
        _live_error = None
    except Exception as error:
        message = str(error)
        if message != _live_error:
            unreal.log_error('[XHNodeChinese] 实时词条未导入：' + message)
        _live_error = message


def startup():
    global _tick_handle, _bridge, _bridge_error, _preloaded, _indexed_terms
    if _tick_handle is not None:
        return
    SAVE.mkdir(parents=True, exist_ok=True)
    register_menus()
    _indexed_terms={r['Source']:r['Translation'] for r in core.load_dictionary(SAVE/'IndexedTranslations.csv')}
    try:
        from .bridge import Bridge
        _bridge = Bridge(PLUGIN, unreal.Paths.convert_relative_path_to_full(unreal.Paths.engine_dir()))
    except Exception as error:
        _bridge_error = str(error)
        unreal.log_warning('[XHNodeChinese] Dynamic display unavailable: ' + _bridge_error)
    rebuild()
    if _bridge is not None:
        sync_long_text()
        warm=set(_bridge.terms)
        try:
            previous=json.loads((SAVE/'LiveStatus.json').read_text(encoding='utf-8'))
            warm.update(previous.get('unmatched_current',[]))
            warm.update(p['source'] for p in previous.get('bindings',[]))
        except (OSError,ValueError,KeyError):pass
        _bridge.preload(warm)
        _preloaded=len(warm)
        _bridge.start()
    save_state()
    _tick_handle = unreal.register_slate_post_tick_callback(tick)
    from .asset_index import Indexer
    global _indexer
    _indexer=Indexer(PLUGIN,SAVE,catalogue(),cached_only=True)
    import atexit
    atexit.register(shutdown)
    unreal.log(f'[XHNodeChinese] Ready {RUNTIME_VERSION}: {_preloaded} preloaded; progressive Codex translation.')


def shutdown():
    global _tick_handle
    if _tick_handle is not None:
        unreal.unregister_slate_post_tick_callback(_tick_handle)
        _tick_handle = None
    if _bridge is not None:
        _bridge.shutdown()
    if _external is not None:_external.shutdown()
    from . import status_ui_029 as status_ui
    status_ui.unregister()
