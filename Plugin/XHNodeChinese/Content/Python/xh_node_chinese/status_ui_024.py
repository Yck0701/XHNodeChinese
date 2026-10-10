"""Distinct function icons and checked backgrounds for toolbar toggles."""
import unreal
from .status_ui import TOOLBARS
_entries=[]

@unreal.uclass()
class XHNodeChineseStatusEntry024(unreal.ToolMenuEntryScript):
    def kind(self):
        name=str(self.data.name)
        if 'Capture' in name:return 'capture'
        if 'Codex' in name:return 'codex'
        if 'Auto' in name:return 'auto'
        return 'export' if 'ExportStatus' in name else 'language'

    @unreal.ufunction(override=True)
    def get_label(self,context):
        from . import runtime
        return runtime.status_display(self.kind())['label']

    @unreal.ufunction(override=True)
    def get_tool_tip(self,context):
        from . import runtime
        status=runtime.status_display(self.kind())
        return status['label']+'\n'+status['tooltip']

    @unreal.ufunction(override=True)
    def get_check_state(self,context):
        from . import runtime
        key={'capture':'capture_untranslated','language':'enabled','auto':'auto_translate'}.get(self.kind())
        return unreal.CheckBoxState.CHECKED if key and runtime.state()[key] else unreal.CheckBoxState.UNCHECKED

    @unreal.ufunction(override=True)
    def get_icon(self,context):
        from . import runtime
        return unreal.ScriptSlateIcon(style_set_name='EditorStyle',style_name=runtime.status_display(self.kind())['icon'])

    @unreal.ufunction(override=True)
    def execute(self,context):
        from . import runtime
        method={'capture':runtime.toggle_capture,'language':runtime.toggle_enabled,
                'auto':runtime.toggle_auto,'codex':runtime.translate_with_codex,'export':runtime.open_live}[self.kind()]
        method()

def add(menu,section,name,toolbar):
    entry=XHNodeChineseStatusEntry024()
    entry.init_entry('XHNodeChinese',menu,section,'XHNodeChinese.'+name,'状态','状态')
    data=entry.data;advanced=data.advanced
    advanced.entry_type=unreal.MultiBlockType.TOOL_BAR_BUTTON if toolbar else unreal.MultiBlockType.MENU_ENTRY
    advanced.user_interface_action_type=(unreal.UserInterfaceActionType.TOGGLE_BUTTON
        if entry.kind() in ('capture','language','auto') else unreal.UserInterfaceActionType.BUTTON)
    data.advanced=advanced;entry.data=data
    entry.register_menu_entry();_entries.append(entry)

def register():
    from .runtime import MENU_NAMES
    from . import status_ui_023
    status_ui_023.unregister()
    unregister();menus=unreal.ToolMenus.get()
    for menu in TOOLBARS:
        menus.extend_menu(menu)
        for name in ('CaptureStatus','LanguageStatus','AutoStatus','CodexStatus','ExportStatus'):
            add(menu,'XHNodeChineseStatus',name,True)
    for menu in MENU_NAMES:
        name=menu+'.XHNodeChinese'
        for entry in ('AutoToggle','CodexTranslate','CaptureToggle'):
            menus.remove_entry(name,'Dictionary','XHNodeChinese.'+entry)
            add(name,'Dictionary',entry,False)

def unregister():
    for entry in _entries:entry.unregister_menu_entry()
    _entries.clear()
