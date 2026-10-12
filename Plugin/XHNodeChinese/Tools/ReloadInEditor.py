"""Run with UE's Execute Python Script command after installing an update."""
import importlib
import unreal
import xh_node_chinese.runtime as runtime

runtime.shutdown()
from xh_node_chinese import core, bridge, personal, auto_translate, live, long_text, term_keys, codex_translate, multi_translate, web_import, asset_index
for module in (term_keys,core, bridge, personal, auto_translate, live, long_text, codex_translate, multi_translate, web_import, asset_index, runtime):
    importlib.reload(module)
runtime.startup()
runtime._bridge.tick() if runtime._bridge is not None else None
runtime.live_sync(capture=runtime.state()['live_export'])
unreal.log('[XHNodeChinese] 更新已加载；诊断：' + str(runtime.SAVE / 'LiveStatus.json'))
