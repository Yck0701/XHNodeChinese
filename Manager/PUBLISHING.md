# 发布与构建

## 第一次发布到 GitHub

公开源码仓库：<https://github.com/Yck0701/XHNodeChinese>。

公开发布仓库：<https://github.com/Yck0701/XHNodeChinese-new>。以下 Release 操作均在公开发布仓库进行。

1. 在仓库的 **Releases → Draft a new release** 新建版本。
2. 上传本工具 `release` 文件夹内的 **manifest.json 和所有 ZIP**。它们必须是同一个 Release 的附件，不要只提交到源码分支。
3. 上传同版本便携管理器包（例如 `XHPluginManager-1.0.4-win64.zip`）。编译用源码 ZIP 单独发布，并在 manifest.json 的 source 项填写文件名、版本和 SHA-256。
4. 确认附件完整后发布，并将其设为 **Latest**（不选 Pre-release）。

管理器使用 `https://github.com/Yck0701/XHNodeChinese-new/releases/latest/download/manifest.json`。版本清单引用相邻附件的文件名，在线和离线共用一套文件。公开清单包含已审查的 source 下载项，便于管理器自动编译。

**只发布本次生成的公开发布目录。**源码公开前须检查个人配置、密钥与项目文件；不要直接上传未经审查的工作目录。公开插件 ZIP 会去掉 `Source` 和维护用 `Tools`（保留运行所需的 ReloadInEditor.py）。插件运行所需的 Python 脚本仍随包分发，仓库私密不等于这些运行脚本不可见。

工作区的 `shared-review` 保存了待审查的原词条，不属于发布内容。GitHub 凭据不进入管理器、插件或任何发布包。

## 生成首版清单

以下命令在管理器源码目录运行，路径按实际位置替换：

```text
python publish.py prepare --plugin ../XHNodeChinese-0.2.8.zip --shared shared --output release --verification ../XHNodeChinese/Verification/integration-028.json
```

`prepare` 用于本项目已有验证记录的定制 UE 5.8.3 包。它不会上传文件，也不会从已安装插件中读取个人配置。

## 增加另一个引擎构建

1. 在管理器中选择对应引擎、完整 SDK 和工具链，编译测试包。
2. 在该引擎的隔离工程中检查加载、启用/停用、采集、参数/模块/蓝图搜索、网页译文导入以及原生自检。不得直接将编译完成当成兼容通过。
3. 保留编译器生成的同名 `.json` 报告；建立验证记录，至少包含 `passed: true` 和该 ZIP 的 `package_sha256`，并记录实际验证结果。
4. 执行：

```text
python publish.py add --manifest release/manifest.json --package path/to/UNVERIFIED.zip --report path/to/UNVERIFIED.json --verification path/to/verified.json --label "UE 目标版本 / 已验证构建"
```

命令核对包、编译报告和验证记录，并在清单中加入新包。同一引擎指纹的新条目替换旧条目，其他构建继续保留。将更新后的清单、共享包、全部仍被引用的引擎 ZIP 一起上传到新的 Latest Release。

## 处理云端编译投稿

公开仓库的 `community-official-*` 与 `community-custom-*` 是相互独立的投稿预发布存档，不能加入自动安装。收录机器人只检查格式和哈希，不执行上传的 DLL。详细投稿流程见公开仓库的 CONTRIBUTING.md。

维护者先审查来源，在隔离环境准备对应目标引擎。可以用下面命令将投稿组件与同插件版本的可信基础包组合为验证包：

```text
python review_contribution.py --bundle components.zip --catalog official-engines.json --base trusted-plugin.zip --expected-base-sha256 <可信基础包SHA256> --output candidate-UNVERIFIED.zip
```

该命令只组合文件，不安装或加载组件。验证通过后，沿用上文 `publish.py add` 的报告与验证记录流程发布正式包。云端正式清单优先于待审核目录，所以正式发布后管理器会直接匹配安装包。

官方目录 `catalog/official-engines.json` 仅由维护者依据独立取得并验证的官方引擎更新，不能根据用户自报的版本或指纹自动授信。定制包保留独立指纹及分类。用户关闭分享时不应要求其上传指纹。

## 更新共享译文

编辑 `shared/User.csv` 和 `shared/LongText.csv`，使用 UTF-8，保留两列表头 `Key,Value`。不要包含空译文、私有路径或工程名称。带作用域的词典可以使用五列格式。

本次筛选摘要在 `shared/curation-report.json`。入选规则为：引擎语言资源匹配、引擎源码/资源包含原文，或长文本引用的资源确实位于引擎插件内容中；无法确认来源的条目暂不公开。引擎中的通用短词可能与用户自定义命名重合，需要后续人工维护。

更新共享文件后，使用以下命令生成新包并更新校验值，同时保留清单中的各引擎安装包：

```text
python publish.py shared --manifest release/manifest.json --shared shared --version 2026.10.11
```

日期可换成你自己的版本号。同步更新共享文件的说明和筛选摘要，再上传新 Release。管理器对所有下载的 ZIP 校验清单中的 SHA-256；校验失败不安装。清单来源应保持为你信任的 HTTPS 仓库。

## 从源码打包管理器

源码运行需要 Python + tkinter。便携 EXE 用户不需要 Python。安装 PyInstaller 后运行：

```text
python -m PyInstaller --noconfirm --clean --onedir --windowed --name XHPluginManager --icon assets/translate.ico --add-data "assets;assets" app.py
```

把 `README.md`、`PUBLISHING.md` 和 `release` 文件夹复制到 EXE 同级，再压缩整个 `dist/XHPluginManager` 文件夹。不能只分发 EXE，`_internal` 文件夹也是运行必需的。

## 更新保护

- 复用已验证的引擎二进制时，必须重新打入当前运行脚本及所有基础词典。使用 `default_dictionary_payloads` 生成词典内容，并以 `verify_packaged_defaults` 逐份校验最终 ZIP；禁止只覆盖 Shared.csv、SharedLongText.csv 而遗漏 UI.csv 等基础词典。
- 发布包中的 User.csv 必须是空白模板；基础词典中不放个人覆盖项。实际发布 ZIP 仍需在每个目标引擎的隔离工程中验证。
- 下载先写临时文件，校验后才使用；拒绝路径越界、符号链接、重复压缩条目与超大压缩包。
- 插件安装使用暂存目录，保留个人词典，工程 Saved 数据不替换，旧插件目录另行备份。
- 词典替换/恢复先备份两份文件；执行出错时尝试恢复原内容。意外断电后可用 ZIP 备份恢复。
- 工具不会安装不匹配引擎的二进制文件，不会自动下载整套引擎或静默安装编译环境。
- 共享包可直接在本地预览；任何发布操作均由发布者在 GitHub 中完成。
