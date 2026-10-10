"""Dynamic toolbar controls, including explicit Codex translation requests."""
import unreal
from .status_ui import TOOLBARS
_entries=[]

@unreal.uclass()
class XHNodeChineseStatusEntry019(unreal.ToolMenuEntryScript):
    def kind(self):
        name=str(self.data.name)
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
        return runtime.status_display(self.kind())['tooltip']

    @unreal.ufunction(override=True)
    def get_icon(self,context):
        from . import runtime
        return unreal.ScriptSlateIcon(style_set_name='EditorStyle',style_name=runtime.status_display(self.kind())['icon'])

    @unreal.ufunction(override=True)
    def execute(self,context):
        from . import runtime
        if self.kind()=='language':runtime.toggle_enabled()
        elif self.kind()=='auto':runtime.toggle_auto()
        elif self.kind()=='codex':runtime.translate_with_codex()
        else:runtime.open_live()


def add(menu,section,name,toolbar):
    entry=XHNodeChineseStatusEntry019()
    entry.init_entry('XHNodeChinese',menu,section,'XHNodeChinese.'+name,'状态','状态')
    data=entry.data;advanced=data.advanced
    advanced.entry_type=unreal.MultiBlockType.TOOL_BAR_BUTTON if toolbar else unreal.MultiBlockType.MENU_ENTRY
    data.advanced=advanced;entry.data=data
    entry.register_menu_entry();_entries.append(entry)


def register():
    from .runtime import MENU_NAMES
    from . import status_ui_018
    status_ui_018.unregister()
    unregister();menus=unreal.ToolMenus.get()
    for menu in TOOLBARS:
        menus.extend_menu(menu)
        for name in ('LanguageStatus','AutoStatus','CodexStatus','ExportStatus'):
            add(menu,'XHNodeChineseStatus',name,True)
    for menu in MENU_NAMES:
        name=menu+'.XHNodeChinese'
        menus.remove_entry(name,'Dictionary','XHNodeChinese.AutoToggle')
        add(name,'Dictionary','AutoToggle',False)
        add(name,'Dictionary','CodexTranslate',False)


def unregister():
    for entry in _entries:entry.unregister_menu_entry()
    _entries.clear()
