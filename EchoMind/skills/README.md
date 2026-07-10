# StandardPilot Skills 文档

StandardPilot 启动时会优先从 `STANDARDPILOT_SKILLS_DIR` 读取 Skills；为兼容旧部署，也会回退读取 `ECHOMIND_SKILLS_DIR`。Skills 会在匹配用户请求时注入到对应 Agent 的 system prompt，适合维护标准文稿处理规范、TDoc 摘要字段、提案写作边界、会议 challenge 准备和禁止事项。

当前示例文件沿用原目录名以保持加载逻辑兼容：

```text
skills/general_customer_service/SKILL.md  # Standard Analysis Skill：标准问答、Gap 分析、任务澄清
skills/technical_support/SKILL.md         # TDoc Summary Skill：TDoc 摘要与字段抽取
skills/billing_support/SKILL.md           # Proposal Writing and Review Defense Skill：提案草稿与会议攻防
```

## 编写原则

- 一类 Skill 只描述一类职责，不要把 TDoc 摘要、标准化价值判断和提案写作边界混在同一段规则里。
- 所有标准结论必须区分已有证据、合理推断和待确认内容。
- 不要编造标准条款、TDoc ID、公司立场或会议结论。
- 如果材料不足，应提示补充 WG、Release、Agenda、TDoc ID、目标公司或目标任务。
