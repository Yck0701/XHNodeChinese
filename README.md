# 虚幻翻译插件 · 源码仓库

此仓库用于维护插件与管理器源码，应保持私密。

- `Plugin/XHNodeChinese`：可构建的插件源码及已验证定制引擎二进制参考。
- `Manager`：更新器、共享词典及发布脚本源码。
- 说明、维护与下载入口：https://365.kdocs.cn/l/cpi4ASG5Izsi?source=wiki
- 自动更新文件仓库：https://github.com/Yck0701/XHNodeChinese-new

普通用户无需访问此仓库。安装包由 `Manager/publish.py` 去除 C++ 源码和维护工具后生成。运行时 Python 脚本仍需随插件分发。

## 为另一引擎编译

将 `Plugin/XHNodeChinese` 整个文件夹压缩为 ZIP（包内根目录为 XHNodeChinese），在管理器“引擎编译”页选为本地源码包。构建需要目标引擎、匹配 SDK 和相应 MSVC 工具链。验证通过后才能通过发布脚本加入公开清单。

不要提交个人词典、原始长文本采集、API 密钥、Codex 连接配置或工作工程。这里的 User.csv 为空，共享译文单独维护在 Manager/shared。

安装与发布步骤见 Manager/README.md 和 Manager/PUBLISHING.md。

## 当前版本

管理器 1.0.15、插件 0.2.16；共享词库 2026.10.12.3。选择工程后自动识别 UE，启动检测适配；已安装就直接使用，有包就复用或下载，没有才询问是否编译。修复安装时误提示“先选择引擎”的问题，并同步界面图标、插件流畅性与路径保护改进。

安装说明与金山云下载：https://365.kdocs.cn/l/cpi4ASG5Izsi?source=wiki
版本附件与自动更新：https://github.com/Yck0701/XHNodeChinese-new/releases/tag/manager-v1.0.15
