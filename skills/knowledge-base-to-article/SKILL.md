---
name: knowledge-base-to-article
description: Transform knowledge base discussions into polished publishable articles with proper architecture compliance
license: MIT
metadata:
  version: "1.0.0"
  author: lynch5mo
  category: writing
---

# From Knowledge Base to Publishable Article

## Context
When the user asks to turn a knowledge base discussion or research into a polished article.

## Architecture Rules (2026-04-13)
- **Publishable articles go to `write/articles/`**, NOT `wiki/summaries/`
- `wiki/` is for compiled knowledge summaries
- `write/` is the dedicated writing layer (articles, drafts, publish, templates)

## Writing Iteration Pattern

### Critical Rule: Write for Humans, Not Machines
**用户明确纠正（2026-06-04）**："你的问题是现在的文章写得太机械了。你这是在给机器看，而不是在给人看。"

这是最常见的失败模式。具体表现：
- 把数据表格堆在一起，用"结论：XXX"做结尾
- 用"第一/第二/第三"的编号结构
- 用代码块展示分析过程（读者不需要看你的代码）
- 每段都是"数据+解读"的机械格式

**正确的做法：**
- 先讲一个反常识的现象或悬念（钩子）
- 用类比和故事串联逻辑，不是用编号
- 数据是论据，不是主角——先说结论，再用数据证明
- 用比喻：水龙头、引擎、飞机、迷宫、弃船、影子
- 结尾留一个开放性问题或金句，不要写"结论：..."

### Common User Feedback Patterns
1. "什么都说了又好像什么都没说" → Need deeper analysis on specific angles, not breadth
2. "逻辑上没有必然的推进关系" → Each section must build on the previous
3. "趣味性不够" → Use concrete examples, dialogue, vivid language
4. "去掉章节编号" → Flowing prose, not academic structure
5. **"太机械了" / "给机器看的"** → 这是最严重的失败，必须重写
6. **"太过于新闻媒体的味道" / "过于正式化"** → 用户要的是个人随笔/博客风格，不是新闻通稿。用"我"、用反问、用"你往下看就会发现"这类对话感强的表达
7. **"过渡太生硬 / 割裂感太强"** → 章节之间必须有过渡句，不能硬切。用"说完了X，我们把镜头拉远一点""但如果你以为这只是关于Y的故事，那你就只看到了冰山一角"这类桥接
8. **"共识部分太冗长，分歧才是重点"** → 涉及谈判/协议类话题时，共识一笔带过，把篇幅和分析力度集中在分歧上——分歧才是故事
9. **"引用太多、太学术"** → 用户不希望大段引用原文（尤其是引号块和"原话：'……'"格式），更喜欢用自己的话转述观点。引用降级为"他当时说……""他的原话大意是……"这类口语化转述。直接引用只保留最关键的一句，且不使用blockquote格式
10. **新闻引用简化** → 去掉"Al Jazeera在3月19日报道"这类格式化引用，改为"有人评论说""多家智库都在用同一个词"这类自然叙述。参考来源可以在文末合并分组，不在正文中逐条列出
11. **深层逻辑优先于事件报道** → 分析地缘政治/宏观经济类话题时，不要只罗列事件，要提炼底层结构性逻辑（如"五根支柱同时动摇"）。用框架性语言组织分析，而不是新闻流水账
12. **副标题要有主题感** → 副标题不应该是描述性的（"分析XXX的走向"），而应该是主题性的、有吸引力的（"索尔坦四年前的预言，正在一一兑现"）
13. **不要写预测章节** → "接下来会发生什么"之类的预测部分"过于淡而无味"，削弱文章张力。用户明确要求删除。文章应该在分析高潮处或一个有力的金句结尾，而不是用不确定的预测来收尾。如果必须提及未来，融入正文分析中（如"五根支柱同时动摇"已经暗示了未来方向），而不是单独开一个预测章节
14. **用户提供的分析文本不要改写** → 如果用户把自己的分析文本贴进来，那是他们想要的最终深度和逻辑。不要用"简化版"覆盖它。任务是润色过渡和语序，不是重新组织论证结构。用户的文本就是标准，Agent的工作是让它衔接更自然
15. **过渡润色需要逐段打磨** → 章节之间的过渡不能只加一句就完事。每个过渡点都要检查：前后两段的逻辑关系是什么？用什么桥接最自然？常见的过渡模式：因果递进（"钱的问题还没解决，核的问题又浮出水面了"）、视角切换（"说完了今天的局面，我们把镜头拉远一点"）、对比转折（"堡垒美国在收缩，而在地球的另一端"）、悬念引出（"这让我想起一个人"）
16. **副标题要有主题感** → 副标题不应该是描述性的（"分析XXX的走向"），而应该是主题性的、有吸引力的（"索尔坦四年前的预言，正在一一兑现"）

### Recommended Approach
1. **Start with a hook** — 反常识现象、悬念、或一个让人"等等，这不对"的观察
2. **Build narrative, not lists** — 用"引擎熄火""三重绞杀""流动性退潮"这样的比喻串联
3. **数据是论据，不是主角** — 先说洞察，再用数据证明。"TGA飙升$374B后BTC见顶"比表格更有冲击力
4. **Go deep on 2-3 key angles** rather than shallow on 10
5. **End with a strong metaphor or question** — "当你把所有支撑它的逻辑一层层剥开之后，底下什么都没有"
6. **章节之间必须有过渡句** — 不能硬切到下一个话题。用桥接句把前后逻辑串起来："说完了今天的局面，我们把镜头拉远一点""但如果你以为这只是一个关于X的故事，那你就只看到了冰山一角""说到Y，这里有一个关键人物"
7. **谈判/协议类话题：共识一笔带过，分歧重点展开** — 读者不关心双方同意了什么（新闻已经报过了），读者关心他们在吵什么、为什么吵不拢

### Web Research Technique: Google News RSS
大多数现代新闻网站（Reuters、AP、NYT等）都是JS重度渲染，curl无法直接抓取正文。最可靠的方法是用Google News RSS：
```bash
curl -sL "https://news.google.com/rss/search?q=关键词&hl=en-US&gl=US&ceid=US:en" -H "User-Agent: Mozilla/5.0" | grep -oE '<(title|pubDate|source)>[^<]+</(title|pubDate|source)>'
```
这能获取标题、日期、来源，足以拼出事件全貌。需要具体文章内容时，再尝试抓取AMP版本或非JS站点（如DW、Al Jazeera的部分页面）。

### Structure (公众号长文)
```
反常识钩子 → 第一个逻辑层（叙事）→ 第二个逻辑层（数据）→ 第三个逻辑层（宏观）→
三层叠加的结论 → 一个让人记住的金句收尾
```

### Example Pattern (from 2026-06-04 BTC文章)
开头："2026年6月2日，纳斯达克100涨了0.5%，黄金基本持平，比特币却暴跌了6.5%。"
→ 用一个具体事件做钩子，而不是"本文分析了BTC的三重风险"

收尾："当你把所有支撑它的逻辑一层层剥开之后，底下什么都没有。"
→ 金句，不是"综上所述"

## File Location
- Final articles: `write/articles/`
- Source conversations: `raw/conversations/`
- Compiled knowledge (source material): `wiki/summaries/<domain>/`

## Git Workflow
After writing:
```bash
cd /Users/lynch5mo/Documents/LLM/agent-kb
git add -A && git commit -m "descriptive message"
git push origin main
```
