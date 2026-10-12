# 星河插件管理器 1.0.3 · 修复安装时拒绝访问

## 怎么安装

解压 XHPluginManager-1.0.3-win64.zip，双击 XHPluginManager.exe。选择工程和引擎，检查更新，然后安装匹配插件。安装前保存并关闭 UE。

已使用 1.0.2 的用户，也可以在管理器中检查更新，点击“下载并打开新版工具”。

## 本版修复

- 修复整个插件文件夹无法移动时安装失败的问题：短暂占用自动重试，持续无法移动时先完整备份并校验，再逐文件更新。
- 文件本身被占用时先停止；更新失败自动恢复。恢复受阻或安装中断时，完整旧插件和恢复记录会保留，防止误清理。
- 检查 UE 编辑器及命令行编辑器进程，错误原因写入日志，成功安装后刷新版本状态。
- 继续提供插件 0.2.10、32,578 条基础词条和 4,205 段长说明，安装包和共享词库内容沿用已验证版本。

## 文件影响和备份

安装只更新 Plugins/XHNodeChinese，并在 Saved/XHNodeChinese/UpdaterBackups 保存备份。个人 User.csv 和 LongText.csv 保持原样；不写入项目资产、.uproject 或项目 Config。

UpdaterBackups 中 dictionary- 开头的 ZIP 是个人词典备份，plugin-dictionary- 开头的目录是完整旧插件。出现恢复受阻提示时，先按 install-recovery.json 中记录的路径恢复旧插件，再打开 UE。

共享译文由星河维护，并非 Epic 官方语言包。
