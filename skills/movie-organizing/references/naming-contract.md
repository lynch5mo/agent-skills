## ⭐ 第一部分：命名规范（一切操作的基础，2026-08-24 定版）

目录层级：`<媒体根>/<大洲>/<导演中文名 EnglishName>/<电影文件夹>/<文件>`

### 1.1 标准命名表

| 对象 | 规则 | 示例 |
|---|---|---|
| 导演夹 | `中文名 EnglishName`；中文段与英文段之间恰好一个 ASCII 空格；外国导演中文译名内部姓名段使用 U+00B7 `·`，不得使用 ASCII 空格或 ASCII `.` | `刁亦男 Yi'nan Diao`、`爱德嘉·莱兹 Edgar Reitz` |
| 电影夹 | `中文名.英文 Name.年份.尺寸.格式[.音轨]-发布组` | `太阳照常升起.The Sun Also Rises.2007.CHINESE.1080p.Blu.dts-fgt` |
| 视频文件 | `English Name.年份.尺寸.格式-发布组.ext`（不带中文） | `The Sun Also Rises.2007.CHINESE.1080p.Blu.dts-fgt.mkv` |
| NFO | 与视频 basename 完全一致 | 同上 `.nfo` |
| 字幕 | 视频 basename + 语言标识 + 原扩展名 | 同上 `.chs.srt` / `.chs.ass` / `.eng.srt` |

### 1.2 空格规则（2026-08-24 用户定为绝对规则）

- **英文名内部单词之间用空格，不用点连接**。点只作段落分隔符。
- 电影夹：`混在北京.The Strangers in Beijing.1995.720p.H264.AC3` ✅　`混在北京.The.Strangers.in.Beijing...` ❌
- 视频：`The Strangers in Beijing.1995.720p.H264.AC3.mkv` ✅
- 年份及之后的 token 保持点分隔：`英文名（空格）.年份.分辨率.编码.音轨-发布组`
- 语言标识标准化：`.zh/.chn/.chn0→.chs`、`.cht`、`.eng` 保持小写。

### 1.3 导演中文译名规则（2026-08-28 修订）

- 导演夹始终是 `中文段 EnglishName`，中文段与英文段之间恰好一个 ASCII 空格；英文姓名内部按原文保留空格、撇号、连字符和重音。
- 外国导演的中文译名若由多个姓名段组成，中文段内部统一使用 U+00B7 `·`：`爱德嘉·莱兹 Edgar Reitz`。已有正确 `·` 必须保留；ASCII `.` 或姓名段之间的 ASCII 空格均须改为 `·`。
- 多导演中文名使用 `、` 分隔，且每位导演中文姓名内部仍使用 `·`：`奥利弗·纳卡什、艾力克·托莱达诺 Olivier Nakache、Éric Toledano`。
- 原生中文姓名不新增 `·`：`刁亦男 Yi'nan Diao`、`张艺谋 Zhang Yimou`。
- 不得把导演中文段的 U+00B7 `·` 与电影/视频文件名中的 ASCII `.` 混同；导演夹规范化只改中文译名分隔符和中英段之间空格，不改英文姓名内容。

### 1.4 冲突与缺失处理（禁止造名）

1. **保持原大小写、发布组原样**——release 是 `WEB-DL`/`RARBG` 就原样保留；发布组 `m-tibi` 不许写成 `-mtibi`。
2. **年份冲突**：目录用查证后的影片年份；视频文件保留 release 原始 token（如《无名狂》目录 2019、文件保留 `Wild.Swords.2020`）。
3. **发布组不可考**：标 `Unk` 或省略该段，禁止编造（《苹果》B 版 → `AAC-Unk`）。
4. **夹名与实际内容不符**：一律以视频实片为准重新查证改名（《寻枪》原夹误标 The Missing Sun；《地球最后的夜晚》错标 2014→2018）。
5. **文件名里不要中文**；中文只出现在电影夹名的开头段。
6. **不确定的 token 进报告单议，不能猜**。

### 1.5 电影夹内容白名单（净化标准）

夹内只允许存在：

- 视频文件（mkv/mp4/avi/rmvb/ts/m2ts/iso/wmv/mov/m4v…）
- 与视频同名的 `.nfo`
- 与视频 basename 一致 + 语言标识的字幕（srt/ass/ssa/sub/idx/sup/vtt）

其余一切（海报/fanart/clearlogo/backdrop/torrent/RARBG.txt/exe/论坛htm/lnk/url/sample/播放器截图/广告视频/.dat VOB 老副本/Sample 子夹）= 垃圾，**当批移入 `_trash_`**，禁止标"暂留项"拖后。`.DS_Store`/`._*` 直接删。

### 1.6 查证渠道（三源闭环）

1. 夹内 NFO 的 title/originaltitle/year/director；
2. ffprobe 实测时长+分辨率（验证 runtime 是否吻合）；
3. IMDb suggestion API：`https://v2.sg.media-imdb.com/suggestion/x/<关键词>.json`（豆瓣已限流，仅作参考）；tt 号可反查 `/suggestion/t/<tt号>.json`。

三源互相印证后再写名；任何单源存疑即出报告。
