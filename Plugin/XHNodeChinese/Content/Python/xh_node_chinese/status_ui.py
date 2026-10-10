"""Live toolbar labels/icons; callbacks resolve the currently loaded runtime."""
import unreal

TOOLBARS = ('LevelEditor.LevelEditorToolBar.User', 'AssetEditor.Niagara.ToolBar',
            'AssetEditor.NiagaraScriptEditor.ToolBar', 'AssetEditor.MaterialEditor.ToolBar',
            'AssetEditor.BlueprintEditor.ToolBar')
_entries = []

@unreal.uclass()
class XHNodeChineseStatusEntry015(unreal.ToolMenuEntryScript):
    def kind(self):
        return 'export' if 'ExportStatus' in str(self.data.name) else 'language'

    @unreal.ufunction(override=True)
    def get_label(self, context):
        from . import runtime
        return runtime.status_display(self.kind())['label']

    @unreal.ufunction(override=True)
    def get_tool_tip(self, context):
        from . import runtime
        return runtime.status_display(self.kind())['tooltip']

    @unreal.ufunction(override=True)
    def get_icon(self, context):
        from . import runtime
        return unreal.ScriptSlateIcon(style_set_name='EditorStyle', style_name=runtime.status_display(self.kind())['icon'])

    @unreal.ufunction(override=True)
    def execute(self, context):
        from . import runtime
        if self.kind() == 'language':runtime.toggle_enabled()
        else:runtime.open_live()

def register():
    unregister()
    menus=unreal.ToolMenus.get()
    for menu in TOOLBARS:
        menus.extend_menu(menu)
        for name in ('LanguageStatus','ExportStatus'):
            entry=XHNodeChineseStatusEntry015()
            entry.init_entry('XHNodeChinese',menu,'XHNodeChineseStatus','XHNodeChinese.'+name,'状态','状态')
            data=entry.data
            advanced=data.advanced
            advanced.entry_type=unreal.MultiBlockType.TOOL_BAR_BUTTON
            data.advanced=advanced
            entry.data=data
            entry.register_menu_entry()
            _entries.append(entry)

def unregister():
    for entry in _entries:
        entry.unregister_menu_entry()
    _entries.clear()
