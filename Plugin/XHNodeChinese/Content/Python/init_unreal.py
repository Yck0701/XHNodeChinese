try:
    from xh_node_chinese import runtime
    runtime.startup()
except Exception:
    import traceback
    import unreal
    unreal.log_error('[XHNodeChinese] ' + traceback.format_exc())
