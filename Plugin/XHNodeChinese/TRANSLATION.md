# 翻译工具设置

先看[安装和常用操作](README.md)。网页和 Codex 都无需 API 密钥。

网页导入支持带说明的 JSON、Markdown 表格和两列 CSV；只返回一部分也可以导入有效条目。中断后点击“开始／继续翻译”。

Codex 会自动查找本机程序并复制请求路径，用户粘贴到对话发送即可。高级自动发送仍可指定聊天 ID。

## 二、API 翻译：配置一次，之后后台处理

API 密钥需要在对应服务商平台申请，与网页聊天账号的免费使用额度不一定相同。

### 第一步：打开配置

选择 **虚幻翻译插件 → 翻译工具 → API 设置**，选择 DeepSeek、豆包／火山方舟或通用兼容接口模板。

插件会打开工程中的 `Saved/XHNodeChinese/TranslationAPI.json`。模板只在首次创建时写入，已有配置不会被覆盖。

### 第二步：填写并保存

通常只需填写这三项：

| 配置项 | 填什么 |
| --- | --- |
| `endpoint` | 服务商提供的完整接口地址 |
| `model` | 你已开通的模型名称或推理接入点 ID |
| `api_key` | 你自己的 API 密钥，不要发到聊天或分享给别人 |

DeepSeek 模板示例（模型名称以服务商当前提供的为准）：

```json
{
  "endpoint": "https://api.deepseek.com/chat/completions",
  "model": "deepseek-flash",
  "api_key": "在这里填写自己的密钥",
  "api_key_env": "",
  "timeout_seconds": 90,
  "extra_body": {"thinking": {"type": "disabled"}}
}
```

豆包／火山方舟的接口地址为 `https://ark.cn-beijing.volces.com/api/v3/chat/completions`，`model` 填写你已开通的模型或推理接入点 ID。

### 第三步：开始翻译

保存配置，选择 **自配 API**，然后点击工具栏翻译按钮。插件会在后台逐批翻译并导入，工具栏显示进度。

发生错误时会停止后续请求，已完成的批次会保留。修正配置或网络问题后手动继续；重启编辑器后也需要手动继续未完成任务。


## 进度和历史任务

主菜单“任务进度／中断后继续”可查看剩余数量和失败原因。“翻译工具 → 找回历史翻译任务”可按日期恢复任务。切换未完成任务前先暂停当前接收。

每次粘贴的原回答保存在任务文件夹 answer-*.txt，ImportReport.json 记录失败原因。含无关编号或其他 request_id 的回答不会导入。损坏的 JSON 和没有编号或原文对应关系的散文需让网页工具重新整理。
