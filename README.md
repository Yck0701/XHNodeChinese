# 虚幻翻译插件 · 源码仓库

此仓库已公开，用于维护插件与管理器源码。

- `Plugin/XHNodeChinese`：可构建的插件源码及已验证定制引擎二进制参考。
- `Manager`：更新器、共享词典及发布脚本源码。
- 说明、维护与下载入口：https://365.kdocs.cn/l/cpi4ASG5Izsi?source=wiki
- 自动更新文件仓库：https://github.com/Yck0701/XHNodeChinese-new

管理器 1.0.17 会自动取得经校验的编译源码，普通用户无需手动操作仓库。安装包由 `Manager/publish.py` 去除 C++ 源码和维护工具后生成。运行时 Python 脚本仍需随插件分发。

## 为另一引擎编译

推荐打开管理器 1.0.17，选择目标工程和 UE，点“自动适配并安装”。有匹配包直接使用；没有时自动获取源码、安装编译依赖、编译并安装。Windows 授权、重启和缺失的定制 SDK 仍需本人处理。手动源码包应以 XHNodeChinese 为包内根目录。新构建通过目标引擎验证后才能加入正式清单。

不要提交个人词典、原始长文本采集、API 密钥、Codex 连接配置或工作工程。这里的 User.csv 为空，共享译文单独维护在 Manager/shared。

安装与发布步骤见 Manager/README.md 和 Manager/PUBLISHING.md。

## 当前版本

管理器 1.0.18、插件 0.2.16；共享词库 2026.10.12.3。选择工程和 UE，点「自动适配并安装」即可复用已有包，或自动获取源码、安装 C++ 环境、编译并安装。管理器在原目录更新，原快捷方式继续有效。源码已公开。

安装说明与金山云下载：https://365.kdocs.cn/l/cpi4ASG5Izsi?source=wiki
版本附件与自动更新：https://github.com/Yck0701/XHNodeChinese-new/releases/tag/manager-v1.0.18
