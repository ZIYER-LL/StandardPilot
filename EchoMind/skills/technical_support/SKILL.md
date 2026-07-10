---
name: TDoc Summary Skill
description: 适用于 StandardPilot TDocAnalystAgent 的单篇或一组 TDoc 结构化摘要、字段抽取和争议点识别规范
keywords: TDoc,T-Doc,文稿,摘要,总结,Background,Problem,Proposed Solution,Impact,Agenda,Meeting,Source,Company,Open Issues
---

# TDoc Summary Skill

负责单篇或一组 TDoc 的结构化摘要，重点是读懂文稿本身，而不是判断整个标准方向是否值得立项。

## 必须提取的字段

- Background
- Problem
- Proposed Solution
- Impacted Entities / Procedures
- Company / Source
- Agenda / Meeting / TDoc ID
- Open Issues
- Potential Controversies

## 约束

- 如果文本中没有明确出现公司、会议、Agenda 或 TDoc ID，必须标记“未知”或“待确认”。
- 不要补写不存在的信息。
- 不要把单篇 TDoc 摘要扩展成跨标准机制的 Gap 结论；如用户需要 Gap 判断，应建议交给 StandardAnalystAgent。
