# 高级说明

第一次使用请先看[安装与日常使用](README.md)。选择在线翻译工具请看[翻译工具设置](TRANSLATION.md)。

## 个人词典与长文本

个人词典位于插件的 `Dictionaries/User.csv`。使用 UTF-8 编码，一行一条，两列分别为原文、译文：

```csv
"MyCustomTerm","我的自定义词条"
"DynamicMaterialParameter","动态材质参数"
```

不需要表头；也兼容 `Key,Value` 表头和以 `#` 开头的注释。保存后通常约 3 秒自动加载。

`DynamicMaterialParameter1`、`DynamicMaterialParameter2` 等同一名称的末尾编号变体，可复用基础词条的译文并保留编号；如果词典中有指定编号的独立译文，则优先使用独立译文。`Vector3`、`float4`、`DX12` 等固有名称不按普通编号变体处理。

CSV 单元格中的英文双引号需要写成两个双引号；多行内容需要整体放在双引号内。译文须保留 `{0}`、`{EnumName}`、`%s` 等占位符，以及属性路径、代码标识符和数字。

长说明使用 **编辑长文本翻译**，保存在工程的 `Saved/XHNodeChinese/LongText.csv`，不必全部塞进个人术语词典。请按整段语义翻译，避免逐词拼接成中英混排。

### 兼容旧词典

也支持带命名空间等信息的五列格式：

```csv
Source,Translation,Namespace,Key,Category
Branch,条件分支,K2Node,Branch,Blueprint
```

这类条目按指定范围匹配，不一定全局生效。不要在同一个文件中混用两列表头与五列表头。

同一原文、同一匹配范围的重复条目以最后一条为准。执行词典优化时会创建备份。想修改已有译文，应直接编辑个人词典；清空待翻译导出文件中的译文并不等于删除已有翻译，未改动的旧导出内容也不会覆盖后来手动修改的个人词典。

## 采集、导出与自动翻译的区别

| 功能 | 作用 |
| --- | --- |
| 采集未翻译文本 | 收集界面中尚未匹配的内容；日常使用可关闭以减少开销。 |
| 导出当前会话待译词条 | 将本次会话采集的待翻译内容写入文件并打开，方便手动处理。 |
| 导出全部语言资源待译词条 | 导出语言资源中的待翻译内容，可能包含大量尚未打开界面的词条。 |
| 实时导出 | 随已采集内容更新导出文件，关闭采集后不会继续扫描新内容。 |
| 本地自动翻译 | 复用本地已有译文，补全能匹配的词条；不会自动调用在线服务。 |
| 翻译工具按钮 | 按所选方式发起网页、API 或 Codex 翻译任务。 |

采集开关与汉化显示开关相互独立。新用户默认关闭采集，需要补译时再开启。快捷键提示、加载统计、Python 命令、纯路径及已是中文等不适合作为待翻译词条的内容会被过滤。

## 支持范围与搜索

插件优先处理 Niagara、材质、蓝图的常用界面，包括部分富文本、标签和悬停说明。自定义绘制控件或可编辑输入框可能无法统一处理，不保证所有界面文本都能采集或替换。

汉化针对显示内容，不会重命名资源，也不会更改参数值、脚本逻辑或写回用户保存的可编辑注释。

已支持的新增模块、参数、蓝图和材质搜索可使用英文原名、中文译名或混合词语。“大小／尺寸”“颜色／色彩”等同义词由有限规则支持，不代表任意语义搜索。新译文加载后会更新相关索引。

节点或属性名称仍为英文时，检查 **编辑器偏好设置 → 区域和语言** 中的本地化属性名称、节点及引脚名称设置，并重新打开对应编辑器。

## 文件位置与备份

以下路径均相对于你的工程目录：

| 路径 | 内容 |
| --- | --- |
| `Plugins/XHNodeChinese/Dictionaries/User.csv` | 个人词典 |
| `Saved/XHNodeChinese/LongText.csv` | 长文本翻译 |
| `Saved/XHNodeChinese/Live.csv` | 实时导出内容 |
| `Saved/XHNodeChinese/Pending.csv` | 待翻译词条 |
| `Saved/XHNodeChinese/settings.json` | 插件设置 |
| `Saved/XHNodeChinese/TranslationAPI.json` | 在线 API 配置 |
| `Saved/XHNodeChinese/CodexConnection.json` | Codex 连接配置 |
| `Saved/XHNodeChinese/TranslationRequests/` | 网页和 API 翻译任务记录 |
| `Saved/XHNodeChinese/DictionaryBackups/` | 词典操作备份 |
| `Saved/XHNodeChinese/LongTextBackups/` | 长文本操作备份 |
| `Saved/XHNodeChinese/ExportBackups/` | 导出文件操作备份 |
| `Saved/XHNodeChinese/LiveStatus.json` | 当前运行状态，供排查问题 |

**覆盖安装前仍需手动备份。**直接解压安装包不会自动保留原目录中的个人词典。建议关闭 UE 后备份整个插件目录和 `Saved/XHNodeChinese`，更新后恢复自己的 `User.csv`。

分享时使用发布 ZIP，不要附带个人词典、API 密钥、连接配置或个人任务历史。

## 引擎兼容与重新编译

本包的动态显示组件针对当前定制 **UE 5.8.3** 构建。即使版本号相同，不同引擎构建也可能不兼容。插件会检查引擎指纹；不要修改版本声明或指纹来强行加载不匹配的二进制文件。

普通用户应向提供者索取匹配的安装包。以下内容仅供需要自行编译的人参考。

源码在 `Source/SlateBridge/Bridge.cpp` 及相关 `.inl` 文件中，构建入口为 `Tools/build_bridge.py`。需要目标引擎及与之匹配的 SDK；当前构建使用 MSVC 14.50、Windows SDK 10.0.26100 和 .NET Framework 4.8 SDK。

在插件目录运行，路径替换为本机实际位置：

```text
python Tools/build_bridge.py --engine "D:/TargetUE/Engine" --sdk "D:/MatchingUESDK/Engine" --vcvars "C:/Path/To/VC/Auxiliary/Build/vcvars64.bat"
python -m unittest discover -s Tools -p "test_*.py"
```

构建成功后，还需在匹配的引擎和独立测试工程中验证加载、菜单、采集与翻译，再分发给其他人。

### 当前版本验证范围

0.2.8 已完成 60 项 Python 测试、6 项原生自检，以及 UE 隔离工程中的菜单、网页结果导入、模拟 API 导入和热加载验证。**尚未使用真实服务商密钥验证在线 API。**记录见 [integration-028.json](Verification/integration-028.json)。
