## 任务：审阅论文中的一个完整段落

### 当前位置
- 章节：{chapter_title}
- 段落编号：第 {para_index} 段

### 上下文（前后段摘要）
{context}

### 待审阅段落
{paragraph}

### 审阅规则
{rules}

### 可参考的范文
{sample_summary}

### 要求

从段落整体角度审阅：
1. 段内逻辑是否清晰，论点是否展开充分
2. 句间过渡是否自然
3. 段落主题是否明确
4. 与前后段是否衔接得当
5. 是否存在冗余或遗漏

如果你认为学生应该参考某篇范文的某个部分来改进，请在 references 中指明。

请以如下 JSON 格式回复：

{{
  "pass": true或false,
  "feedback": "整体评价和改进建议",
  "flagged_sentences": [
    {{"sentence": "有问题的原句", "feedback": "这句的具体问题"}}
  ],
  "references": [
    {{"paper": "范文名称", "chapter": "章节标题或编号", "keyword": "关键词(可选)", "reason": "为什么要参考这部分"}}
  ]
}}

如果通过，flagged_sentences 和 references 为空数组。
references 只在你觉得需要参考范文时才填写，不需要每次都引用。
