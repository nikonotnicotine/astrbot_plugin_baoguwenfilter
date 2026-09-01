# 八股文过滤器 (astrbot_plugin_baoguwenfilter)

对 LLM 返回的文字内容进行正则过滤/替换，消除常见"八股文"套话，同时在下次请求前清理对话历史，防止 LLM 重复学习原始内容。

## 功能

- 13 项可独立开启的过滤/替换规则，默认全部关闭
- 支持自定义过滤词（纯文本）和自定义替换规则（`原文||替换文`）
- 双钩子策略：`on_llm_response` 过滤输出，`on_llm_request` 清理历史

## 配置说明

在管理面板中找到本插件的配置，按需开启各项规则。

| 配置项 | 说明 |
|--------|------|
| `filter_jiqi_yisi` | 删除"极其"和"一丝" |
| `replace_laozi` | "老子" → "我" |
| `replace_jidu` | "嫉妒" → "忮忌" |
| `replace_tama` | "他妈" → "他爹" |
| `filter_jinhuzhe` | 删除"一种近乎"和"带着一种" |
| `filter_weibukeча` | 删除"微不可察"和"不易察觉" |
| `replace_dash` | "——" → "，" |
| `filter_violent` | 删除"低吼/幼兽/凶残的/肉刃/四肢百骸" |
| `filter_burongzhiyi` | 删除"不容置疑的"和"不容置喙的" |
| `filter_wodexiao` | 删除"我的小" |
| `filter_xiongqiang` | 删除"胸腔震动"和"胸腔振动" |
| `custom_filters` | 自定义过滤词（每条一个，纯文本匹配） |
| `custom_replacements` | 自定义替换规则（每条格式：`原文\|\|替换文`） |

## 自定义示例

**custom_filters（自定义过滤）：**
```
简直
不禁
```

**custom_replacements（自定义替换）：**
```
简直||真的
不禁||
```

空替换文等同于删除该词。
