---
name: teaching-video-explainer
description: >-
  把一个经济学/科学概念做成 100–120 秒的中文教学动画视频（单文件 HTML + GSAP + 微软 Neural TTS）。
  当用户说「讲一下 XX 概念」「做个视频讲解」「把这张图讲活」「教学视频」，
  或者要求复刻/迭代某个已有教学视频时使用。
license: MIT
metadata:
  version: 1.0.0
  author: Hermes Agent
  hermes:
    tags: [video, teaching, explainer, gsap, hyperframes, tts, edge-tts]
    related_skills: [course-series-translation, agent-kb-workflow]
    triggers:
      - "做个视频讲解"
      - "讲一下*概念*视频"
      - "教学视频"
      - "把这张图讲活"
      - "explain * with a video"
---

# Teaching Video Explainer — 单文件教学动画

把一个概念做成 100–120 秒的中文讲解视频。产出是一个自包含的 HTML 工程加一个 MP4。

这套流程故意绕开了 OpenMontage 的多阶段流水线。实测下来，那条路会让一半的力气花在满足 schema 和 checkpoint 契约上，对画面零贡献。这里只留三样东西：旁白 JSON、一个构建脚本、HyperFrames 的检查与渲染。

## 什么时候用

- 用户要「讲解一个概念」的视频，两分钟以内
- 有一张图、一组数据、或一条因果链需要讲清楚
- 用户做自学材料，需要一批同风格的短视频
- 需要迭代已有的教学视频（换旁白、换数据、换配色）

## 什么时候不要用

- 需要真人出镜、口播、采访剪辑
- 需要实拍素材或复杂转场特效
- 时长超过 5 分钟（分集，每集仍用本技能）

## 四步流程

### 第一步：写旁白

先写旁白，再想画面。旁白定节奏，画面跟着念。

`narration.json`：

```json
{
  "voice": "zh-CN-YunjianNeural",
  "rate": "-4%",
  "sections": [
    {"id": "s1", "text": "一千辆汽车，或者三千台电脑。……"},
    {"id": "s2", "text": "……"}
  ]
}
```

写法要点：

- 9 到 10 段，每段 10–15 秒，总长控制在 100–120 秒
- 每段只讲一件事，段首直接给结论，不要铺垫
- 第一段必须是钩子：先立住一个反差或一个具体数字，禁止「今天我们来学习」
- 最后一段收口，把概念压缩成几个词
- 中文口语，短句为主。念出来能懂，不要书面语堆叠

### 第二步：生成配音和时间轴

```bash
python scripts/make_tts.py narration.json --out ./audio --timeline timeline.json
```

脚本做三件事：调 `edge-tts` 生成每段 mp3、转 44.1k 单声道 wav、用 ffprobe 量出真实时长算绝对时间轴。

时间轴是后续所有动画的唯一基准。段间隔默认 0.5 秒。

配音选择：

- 男声 `zh-CN-YunjianNeural`，沉稳，讲原理合适
- 女声 `zh-CN-XiaoxiaoNeural`，清晰，讲步骤合适
- `rate=-4%` 到 `-8%`，教学场景宁可慢一点

`edge-tts` 走的是微软 Neural TTS 引擎，和 Azure 同源，免费、不需要 key、不会到期。如果用户有 Azure Speech 配额，把 `voice` 换成 Azure 音色名并在脚本里切到 Azure 分支即可，音质同级。

### 第三步：搭画面

跑一次 `build.py` 生成 `index.html`，然后改三处：

一是几何映射。骨架里有一段：

```js
const P = (x, y) => [OX + x * KX, OY - y * KY];
```

把它换成你的坐标系。曲线用 `scripts/curve.py` 的 PCHIP 函数生成，不要手写贝塞尔控制点。

二是 SVG 元素。骨架提供了网格、坐标轴、刻度、曲线、切线、标记点、说明卡这七种。按概念增删。

三是每段的动画。骨架里的 `hl()`、`bd()`、`dl()`、`odo()`、`cursorTo()` 就是给这个用的：

```js
hl("#hl4", S.s4[0] - 0.1);          // 换标题
bd("#bd4", S.s4[0] + 0.9);          // 换说明文字
odo("#odoCar", 0, 10, at, dur);     // 读数跳档
cursorTo(x, y, at);                 // 游标定位
```

### 第四步：检查并渲染

先把字体提出来（一次性）：

```bash
python scripts/extract_fonts.py --out assets/fonts
```

然后：

```bash
export HYPERFRAMES_BROWSER_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
cd <工程目录>
npx -y hyperframes check            # 必须通过，不许跳过
npx -y hyperframes render --output ../renders/out.mp4 --fps 30 --quality high
```

渲完跑一遍自检：

```bash
python scripts/verify.py ../renders/out.mp4 --expect-duration 116
```

它检查时长、分辨率、音轨、响度、解码错误，并抽出若干关键帧供肉眼核对。

## 设计规范（固定骨架，只换内容）

这套规范是踩过「看起来像会动的教材插图」之后定下来的。不要每次重新设计。

画布 1920×1080，边距 96。

版面用不对称：左侧 96–560 放信息栏（小标、大标题、一句说明、大号读数），右侧 620–1824 放图形。不要居中对称摆，那是插图的排法。

字号四档：52（标题）、46（关键数字或端点标注）、26（说明）、19（刻度与注释）。不要再加档位，层级一多就糊。

线宽三档：8（主曲线）、3（辅助线、切线）、1（网格）。

颜色六个，各司其职：

| 用途 | 值 |
|---|---|
| 纸面 | `#F4EFE4` |
| 墨色（主线条与文字） | `#16202A` |
| 可达 / 增益 | `#0E6B5E` |
| 代价 / 损失 | `#A8341A` |
| 辅助与注释 | `#485866` |
| 高亮 | `#C8901E` |

字体两套：宋体做标题与正文（`Songti SC`），黑体做数字与小标（`Hiragino Sans GB`）。都能从系统 ttc 提成 woff2。

动效分三层，同一时刻只允许一个主运动：

- 主运动：曲线描出、游标滑动、边界外推。一次一个
- 次要：读数跳档、标签淡入。跟着旁白走
- 背景：颗粒与暗角的极慢呼吸，全程不停

转场用位置变化或分段推进，不要满屏淡入淡出。所有元素一起匀速淡入是最典型的「差一口气」原因。

钩子单独设计。前五秒必须是全片信息密度最高的一刻，用大字数字或强对比，不要等元素慢慢出现。

## 环境与坑（每条都踩过）

### 渲染前必做

```bash
export HYPERFRAMES_BROWSER_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
```

不设这个，CLI 会去下载 chrome-headless-shell，网络一断就报 `Chrome not found`，看起来像本机没装浏览器，其实是它没用系统那个。

### 字体必须自备

HyperFrames 的 lint 只认三种：`@font-face` 声明、Google Fonts 引入、内置别名表。直接写系统字体名（`PingFang SC`、`Hiragino Sans GB`、`Songti SC`）一律报 `font_family_without_font_face`，因为云端渲染没有那些字形。

做法是从系统 ttc 提 woff2 放进工程，用 `url()` 引用。`scripts/extract_fonts.py` 已经封装好。

### GSAP 的 immediateRender 会让元素提前可见

多个 tween 碰同一元素的 `opacity` 时，最后构建的那个 `fromTo` 会在构建阶段立即应用它的 `from` 值，覆盖掉 CSS 里的初始值。

症状：切线、说明卡在本该隐藏的时间点出现在画面上。

修法两条一起用：

```js
// 1. 所有 fromTo 加 immediateRender:false
tl.fromTo("#tan", {opacity:0}, {opacity:1, duration:.5, immediateRender:false}, at);
// 2. 在 t=0 显式锁死初始状态兜底
tl.set(["#tan","#cardV","#words"], {opacity:0}, 0);
```

### 不要用 tl.call 改文本

HyperFrames 是逐帧 seek 渲染，不保证按顺序经过每个时间点，`tl.call` 的回调可能不执行或重复执行。

所有文本在 HTML 里预先写好，每段一个节点，用 `opacity` 切换。骨架里的 `hl()` / `bd()` 就是这个模式。

### 长链条 tween 会丢帧

对同一属性连写二十几个微 tween（比如数字每帧加一），逐帧 seek 下容易只执行一部分，表现为数字卡在中间值。

读数改成逐档瞬时跳（`tl.set`），或者用固定的几个离散档位切换。要滚动效果就单独做一个纵向数字带，用一次 transform 位移完成。

### 不要用 motionPath

`MotionPathPlugin` 在 atelier 工程里不稳。改成预计算关键帧再 `tl.set`：

```js
path.forEach((p, i) => cursorTo(p[0], p[1], t0 + (t1 - t0) * i / (path.length - 1)));
```

### PCHIP 转贝塞尔的公式

想画出过点、单调、不过冲的曲线（比如生产可能性边界），用单调三次插值。转换到贝塞尔时：

```python
c1 = (x0 + h/3, y0 + m0 * h/3)
c2 = (x1 - h/3, y1 - m1 * h/3)
```

x 方向的偏移固定是 `h/3`，只有 y 方向乘斜率。写成 `m*h/3` 两边都乘，会把整条曲线的参数压扁，形状和切线方向全错。这个 bug 排查起来很费时间，因为曲线看起来「只是有点怪」。

### 骨架不要复制到工程根目录

`assets/skeleton.html.tpl` 只由 `build.py` 读取。如果把它复制成工程里的 `skeleton.html`，check 会报 `multiple_root_compositions`，因为两个带 `data-composition-id` 的 HTML 都在根目录，运行期可能重复播放音频。需要改模板时改技能里的那一份，不要落到工程里。

### check 的 content_overlap 不看透明度

两个元素的位置重叠就报，哪怕 `opacity:0`。所以隐藏不用的层要用 `opacity:0` 真正隐掉，或者移出画布（`attr.x` 设到画外），不要指望半透明能绕过。

### 逐帧 set 的属性优先用 attr

SVG 元素 `cx` / `cy` / `x1` 这类要改属性，用 `{attr:{cx:...}}`。直接写 `{cx:...}` 会被当成 CSS 属性忽略。

HTML 元素（读数、卡片）用 transform 和 opacity，比 SVG 里的同操作可靠。

## 交付前自检

- [ ] `hyperframes check` 零 error
- [ ] 时长与旁白总长误差在 1 秒内
- [ ] 有音轨，响度峰值不高于 −1dB
- [ ] 抽帧看过钩子、中段、收口三处
- [ ] 关键数字与来源教材一致（对着原文核一遍，不要凭记忆）
- [ ] 曲线形状符合概念本身（外凸还是内凹，斜率在往哪个方向变）

## 常见返工原因

画面「差一口气」通常是这四个，按出现频率排：

一是所有元素匀速淡入淡出，没有主次。改成位置推进加分层节奏。

二是信息挤在画面中间，四周留白没有安排。改成左右分栏。

三是字号只有两档，标题和正文拉不开。套四档阶梯。

四是钩子太弱，前五秒画面是空的。第一帧就要给出最强的数字或最强的对比。

## 复用成本

写过一次之后，做第二条同类视频的增量工作是：写旁白（10 分钟）、改几何映射和 SVG（15 分钟）、调动画时间点（10 分钟）、渲染（2 分钟）。合计约 40 分钟。如果几何形状能复用（同类图表），可压到 20 分钟。

## 脚本

| 脚本 | 作用 |
|---|---|
| `scripts/make_tts.py` | 旁白 JSON → wav + 绝对时间轴 |
| `scripts/curve.py` | PCHIP 插值、贝塞尔转换、沿曲线取点与切线 |
| `scripts/extract_fonts.py` | 从系统 ttc 提 woff2 到工程 |
| `scripts/verify.py` | 成片探测、响度、抽帧 |

`assets/skeleton.html.tpl` 是可直接跑的骨架（含完整 CSS 与时间轴辅助函数），由 `build.py` 填充占位符后生成 `index.html`。`assets/config.example.json` 是配套的配置示例，跑通后再按自己的主题改。

一次完整的最小流程：

```bash
mkdir my-video && cd my-video
python <skill>/scripts/make_tts.py narration.json --out audio --timeline timeline.json
cp <skill>/assets/config.example.json config.json
python <skill>/scripts/extract_fonts.py --out assets/fonts
# 把 gsap.min.js 放进 assets/vendor/（HyperFrames 的 npx 缓存里有）
python <skill>/scripts/build.py --config config.json --timeline timeline.json --out index.html
export HYPERFRAMES_BROWSER_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
npx -y hyperframes check && npx -y hyperframes render --output out.mp4 --fps 30 --quality high
python <skill>/scripts/verify.py out.mp4 --frames 3,20,35
```
