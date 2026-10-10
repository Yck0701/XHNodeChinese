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


def dictionary_stamp():
    return tuple((PLUGIN / 'Dictionaries' / name).stat().st_mtime_ns if (PLUGIN / 'Dictionaries' / name).exists() else 0 for name in ('Base.csv','Graph.csv','UI.csv','Descriptions.csv','User.csv'))


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
        _bridge.rebuild(PLUGIN, state()['enabled'], state()['bilingual'], _long_text.terms if _long_text else {})
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
    global _live, _pending, _auto_total, _last_live_report, _last_import_stamp
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
    data = {'version':'0.2.8', 'time':time.strftime('%Y-%m-%d %H:%M:%S'),
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
    if _long_text.sync(sources,dictionary(PLUGIN),include_known=include_known) and _bridge is not None and apply_bridge:
        _bridge.rebuild(PLUGIN,state()['enabled'],state()['bilingual'],_long_text.terms)
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
        known=_bridge.known_terms if _bridge else dictionary(PLUGIN,_long_text.terms if _long_text else {})
        if not session.prepare(known,provider,include_export):
            if show_dialog:unreal.EditorDialog.show_message('翻译','当前没有新的待译词条或长文本。',unreal.AppMsgType.OK)
            return False
        if provider=='api':return session.start_api(config)
        text,path=session.web_prompt()
        try:clipboard.copy(text)
        except RuntimeError:
            import subprocess
            subprocess.Popen(['notepad.exe',str(path)])
            if show_dialog:unreal.EditorDialog.show_message('请从文件复制','剪贴板暂不可用，已打开任务文本。复制全部内容到翻译工具，得到回答后复制 JSON，并点击“粘贴并导入网页译文”。',unreal.AppMsgType.OK)
            return True
        url=multi_translate.PROVIDERS[provider][1]
        if url:unreal.SystemLibrary.launch_url(url)
        if show_dialog:unreal.EditorDialog.show_message('翻译任务已复制','在网页对话框粘贴并发送。回答完成后复制完整 JSON，再选择“节点汉化 → 翻译方式 → 粘贴并导入网页译文”。\n每次复制一批，导入后再点击翻译按钮复制下一批。网页免费额度与登录要求以服务商为准。',unreal.AppMsgType.OK)
        return True
    except Exception as error:
        if show_dialog:unreal.EditorDialog.show_message('翻译未开始',str(error),unreal.AppMsgType.OK)
        else:raise
        return False


def import_web_translation():
    from . import clipboard
    try:
        count=external_session().accept_text(clipboard.paste())
        unreal.EditorDialog.show_message('已接收译文',f'本批 {count} 条校验通过，正在导入。点击翻译按钮可复制下一批。',unreal.AppMsgType.OK)
    except Exception as error:unreal.EditorDialog.show_message('译文未导入',str(error),unreal.AppMsgType.OK)


def open_translation_files():
    session=external_session()
    if session.state.get('folder'):os.startfile(session.state['folder'])


def configure_translation_api(preset='deepseek'):
    from .multi_translate import configure_api
    import subprocess
    path=configure_api(SAVE,preset)
    subprocess.Popen(['notepad.exe',str(path)])
    unreal.EditorDialog.show_message('配置翻译 API','填写 endpoint（完整接口地址）、model（模型或接入点 ID）、api_key 后保存。也可用 api_key_env 指定环境变量名称。\n已有配置会保留。选择“自配 API”后点击工具栏翻译按钮开始；API 可能收费。\n豆包网页账号不等于火山方舟 API 密钥。配置只存当前工程 Saved 目录，不包含在插件分发包中。',unreal.AppMsgType.OK)


def stop_translation():
    external_session().cancel();codex_session().cancel();write_diagnostics()


def translate_with_codex(include_export=False,show_dialog=True):
    try:
        session=codex_session()
        if session.state['phase'] in ('sending','waiting'):
            if show_dialog:unreal.EditorDialog.show_message('Codex 翻译',session.display()['tooltip'],unreal.AppMsgType.OK)
            return False
        started=time.perf_counter()
        live_sync()
        from .bridge import dictionary
        known=_bridge.known_terms if _bridge else dictionary(PLUGIN,_long_text.terms if _long_text else {})
        submitted=session.start(known,include_export)
        if submitted:
            session.state['button_prepare_ms']=round((time.perf_counter()-started)*1000,2)
            session.persist()
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


def configure_codex():
    path=SAVE/'CodexConnection.json'
    if not path.exists():
        core.write_json(path,{'thread_id':'','cli_path':'','workspace':'','exchange_dir':''})
    import subprocess
    subprocess.Popen(['notepad.exe',str(path)])


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
    menus = unreal.ToolMenus.get()
    for menu_name in MENU_NAMES:
        main = menus.extend_menu(menu_name)
        menu = main.add_sub_menu('XHNodeChinese', 'Tools', 'XHNodeChinese', '节点汉化', 'Niagara、材质、蓝图节点词典')
        for name, label, method, tooltip in [
            ('Language', '启用 / 停用汉化    Ctrl+Alt+L', 'toggle_enabled', '控制本插件汉化，停用时恢复启用前语言'),
            ('Enable', '启用节点汉化', 'enable', '应用独立词典，并保留官方中文'),
            ('Disable', '停用节点汉化', 'disable', '恢复启用前的编辑器语言'),
            ('Bilingual', '切换：中文 / 中英双语', 'toggle_bilingual', '双语仅影响本插件覆盖的词条'),
            ('Edit', '编辑自定义词典', 'edit_dictionary', '保存 UTF-8 CSV 后约三秒自动应用'),
            ('LongText', '编辑长文本翻译', 'edit_long_text', '长说明单独保存；在右列填写完整中文，保存后自动应用，不写入个人词典'),
            ('Optimize', '整理个人词典（去除冗余）', 'optimize_dictionary', '保留最后生效译文和作用域，修改前自动备份'),
            ('Translate', '自动翻译当前词条并写入个人词典', 'translate_current', '复用 UE 官方中文和本地词库整条译文；未知英文保留待译'),
            ('CodexExport', '交给 Codex：全部导出词条和长文本', 'translate_export_with_codex', '包括历史 Pending.csv；可能包含大量引擎词条，耗时更长'),
            ('CodexConfig', '配置 Codex 翻译连接', 'configure_codex', '设置已有聊天 ID、Codex CLI 和请求文件目录；不需要另填 API 密钥'),
            ('CodexCancel', '停止接收本次 Codex 译文', 'cancel_codex', '保留请求和已有译文，停止自动导入；不会终止聊天中的任务'),
            ('Rebuild', '重新扫描并应用', 'rescan', '引擎更新后重新索引文本'),
            ('Export', '导出当前会话待译词条', 'export_untranslated', '两列去重导出；过滤已译词条和资源路径，填写中文保存后自动导入'),
            ('ExportAll', '导出全部语言资源待译词条', 'export_all', '全部资源去重导出；可能包含大量未打开界面的词条'),
            ('Live', '实时导出并打开待翻译词条', 'open_live', '持续追加当前界面英文；填写右列保存后自动导入个人词典'),
            ('LiveToggle', '暂停 / 继续实时写出', 'toggle_live', '暂停时也关闭底层采集；已采集记录保留'),
            ('Diagnose', '检查个人词典实际命中', 'diagnose', '查看已读取数量与实际控件原文、显示译文'),
            ('Status', '状态与使用说明', 'show_status', '查看覆盖数量、文件位置与限制'),
        ]:
            entry = unreal.ToolMenuEntry(name='XHNodeChinese.' + name, type=unreal.MultiBlockType.MENU_ENTRY)
            entry.set_label(label)
            entry.set_tool_tip(tooltip)
            entry.set_string_command(unreal.ToolMenuStringCommandType.PYTHON, '', f'import xh_node_chinese.runtime as xh; xh.{method}()')
            menu.add_menu_entry('Dictionary', entry)
    from .multi_translate import PROVIDERS
    for menu_name in MENU_NAMES:
        parent=menus.extend_menu(menu_name+'.XHNodeChinese')
        providers=parent.add_sub_menu('XHNodeChinese','Dictionary','TranslationProviders','翻译方式','选择网页工具、API 或 Codex')
        entries=[('Provider_'+p,'选择：'+label,f"choose_translation('{p}')",'选择后点击工具栏翻译按钮开始') for p,(label,url) in PROVIDERS.items()]
        entries += [('Start','翻译当前采集词条和长文本','translate_selected()','按当前选择的方式开始或继续'),
                    ('ImportWeb','粘贴并导入网页译文','import_web_translation()','先复制翻译工具返回的完整 JSON；校验通过后才导入'),
                    ('Files','打开本次翻译任务文件夹','open_translation_files()','保留提示词、请求和已接收译文'),
                    ('ApiDeepSeek','配置翻译 API（DeepSeek 模板）',"configure_translation_api('deepseek')",'打开本机配置；已有配置不覆盖'),
                    ('ApiDoubao','配置翻译 API（豆包／火山方舟模板）',"configure_translation_api('doubao')",'首次配置预填服务地址，模型填写自己开通的模型 ID'),
                    ('ApiCustom','配置翻译 API（通用兼容接口）',"configure_translation_api('custom')",'支持 Chat Completions 格式，密钥仅存本机'),
                    ('TranslateAll','按所选方式翻译全部历史导出','translate_selected(include_export=True)','可能有大量词条，API 可能产生费用'),
                    ('Stop','停止当前翻译接收','stop_translation()','保留已导入结果；API 停止后续批次，正在处理的单次请求可能已计费')]
        for name,label,call,tip in entries:
            entry=unreal.ToolMenuEntry(name='XHNodeChinese.'+name,type=unreal.MultiBlockType.MENU_ENTRY)
            entry.set_label(label);entry.set_tool_tip(tip)
            entry.set_string_command(unreal.ToolMenuStringCommandType.PYTHON,'','import xh_node_chinese.runtime as xh; xh.'+call)
            providers.add_menu_entry('Translation',entry)
    from . import status_ui_028 as status_ui
    status_ui.register()
    menus.refresh_all_widgets()


def rescan():
    rebuild(force=True)


def export_all():
    return export_untranslated(all_entries=True)


def tick(delta):
    global _last_check, _last_codex_check, _dictionary_stamp, _last_error, _last_slate, _live_error
    global _codex_resources_pending, _codex_last_batch
    if _hotkey.pressed():
        toggle_enabled()
    now = time.monotonic()
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
                    _bridge.rebuild(PLUGIN,state()['enabled'],state()['bilingual'],_long_text.terms if _long_text else {})
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
    global _tick_handle, _bridge, _bridge_error, _preloaded
    if _tick_handle is not None:
        return
    SAVE.mkdir(parents=True, exist_ok=True)
    register_menus()
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
    import atexit
    atexit.register(shutdown)
    unreal.log(f'[XHNodeChinese] Ready 0.2.8: {_preloaded} preloaded; progressive Codex translation.')


def shutdown():
    global _tick_handle
    if _tick_handle is not None:
        unreal.unregister_slate_post_tick_callback(_tick_handle)
        _tick_handle = None
    if _bridge is not None:
        _bridge.shutdown()
    if _external is not None:_external.shutdown()
    from . import status_ui_028 as status_ui
    status_ui.unregister()
