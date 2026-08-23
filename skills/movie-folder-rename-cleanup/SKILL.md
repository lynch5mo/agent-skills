---
name: movie-folder-rename-cleanup
description: >-
  电影库批量规范化：导演/电影两级目录下，把电影文件夹改名为
  中文名.英文名.年份.尺寸.格式.压缩信息-发布组，文件夹内只保留视频、
  同名 nfo、同名带语言标识字幕；垃圾进 _trash_ 回收站不直接删。
license: MIT
metadata:
  version: "2.0"
  author: lynch5mo
  tags: [media, rename, cleanup, movie-library, ffprobe, naming-convention]
  trigger: User asks to batch-rename movie folders/files to a standard naming convention, clean up non-video junk inside movie folders (zip/txt/posters), promote subtitles from subfolders to the movie folder root, or normalize a director-based movie library (e.g. /Volumes/115open/Media/Movie/<洲>/).
---

# Movie Folder Rename & Cleanup Skill

## 用户命名规范（lynch5mo 定版，2026-08-22）

目录层级：`<媒体根>/<大洲>/<导演中文名 EnglishName>/<电影文件夹>/<文件>`

| 对象 | 命名规则 | 示例 |
|---|---|---|
| 电影文件夹 | `中文名.英文名.年份.尺寸.格式.压缩信息-发布组`（小写 release 风格） | `洛杉矶之战.battle.los.angeles.2011.720p.bluray.x264-bla` |
| 视频文件 | 完整 release 原名，**不带中文** | `battle.los.angeles.2011.720p.bluray.x264-bla.mkv` |
| nfo | 与视频同名 | 同上 `.nfo` |
| 字幕 | 与视频同名 + 语言标识（.chs/.cht/.eng…） | 同上 `.chs.srt` |

### 硬性用户偏好（必须遵守）
1. **保持原大小写，禁止擅自改写**——release 名是 `Chappie.2015.1080p.WEB-DL...RARBG` 就原样保留（含 WEB-DL 大写、RARBG 大写）；只有当用户明确同意某部电影用小写风格时才用小写。
2. **发布组标识原样保留**——`m-tibi` 就写 `-m-tibi` 后缀，不要"帮"用户规范成 `-mtibi`。
3. **文件名里不要中文名**；中文只出现在电影文件夹名的开头段。
4. 无语言标识的字幕：**保留**，命名跟视频文件同名（无语言后缀）。
5. 删除永不 `rm`：统一移入 `<媒体根>/_trash_<区域>_<YYYYMMDD>/`，完成后让用户决定清空。`.DS_Store`、`._*` 例外：直接删除。
6. **`movie.nfo` 必须先配对改名才能参与整理**：通用名 `movie.nfo` 无法被 Kodi/TMM 关联到具体影片。整理任何影片夹之前，先把 `movie.nfo` 改名为与**同夹视频文件同名**（规则见 Phase 0.5）。锚定的是**视频文件名**，不是文件夹名。
7. **字幕与视频同名 + 语言标识**：`<视频文件名全名>.<语言标>.<原扩展名>`（如 `....mkv` 配套 `....chs.srt`）；无语言标识的字幕保留原名不造标签；与视频不同压制版的字幕进回收站不硬配。
8. **导演夹命名全库统一 `中文名 EnglishName`**——包括中国/港台导演也要英文全名（如 `侯孝贤 Hsiao-hsien Hou`、`王家卫 Kar Wai Wong`）。**英文名不确定时必须上豆瓣 / TMDB / IMDb 查证后使用，禁止猜测或留空**；查证结果记录进计划表让用户过目。
9. **执行通道默认走 NAS SSH**（`lynch5mo@192.168.10.33` 的 `/media/CloudDrive/115open/...`），避开 Mac SMB 层 NFD 编码问题；FUSE 上全树 find 会超时，用 CD2 缓存库（dir_cache.sqlite，含 115 文件 ID/大小/SHA1）+ 定点 ls 替代。大批量移动优先建议用户在 115 App/网页端做。

## Workflow

### Phase 0 — 扫描盘点（强制按国家分批，禁一次扫整洲）

**推进单位 = 一个国家**。一次只处理一个国家，完成验证汇报后再开下一个；单国过大再按导演分批。上下文过载是历史事故源，不得贪多。

```bash
find "<目标国家根>" -mindepth 1 | sort
```
拿到该国全树。识别每部电影的：视频 / nfo / 字幕（可能在子文件夹里）/ 垃圾（zip、txt、海报、jpg）/ 结构病态（裸文件、格式中间层）。

### Phase 0.5 — `movie.nfo` 配对改名（整理前必做，不可跳过）

通用名 nfo 先于一切改名/清理动作处理。**严格限定在单部电影夹内配对，绝不跨夹按文件名匹配**（历史教训：寂静人生 nfo 险些塞进咖啡时光）。

```python
# 伪代码：每部电影夹内
videos = [f for f in files if ext in {mkv,mp4,avi,m4v,ts,iso,wmv,mov} and not f.startswith('._')]
mnfos  = [f for f in files if f.lower() == 'movie.nfo']
```

三种情形：
1. **恰好 1 视频 + movie.nfo** → 改名：`movie.nfo` → `<视频文件名去扩展名>.nfo`。锚定视频文件名而非文件夹名（子目录分片/双编码版如 `AVC.mp4` 时，nfo 跟 `AVC.mp4` 对齐成 `AVC.nfo`，不照抄文件夹名）。
2. **多视频 + movie.nfo**（cd1/cd2 分片、AVC/HEVC 双版等）→ **不自动分配**，该夹进"待裁决清单"，向用户报告后由用户指定配给哪个视频（默认建议配第一个正片，用户点头才动）。
3. **无视频 + movie.nfo** → **不动它**，出报告（孤儿元数据；可能是正片在暂存区未归位的信号，参考 recovery skill 的 NFO 配对闭环规则）。

补充判定：
- 若同夹已有与视频同名的 `<video>.nfo`，又另有一个 `movie.nfo` → `movie.nfo` 视为冗余，进回收站。
- BDMV 原盘结构（m2ts 在 STREAM/ 下）没有"文件级视频名"，movie.nfo 保持原名并出报告。
- 改名结果必须进入 Phase 2 计划表第②张表，随整批动作一起让用户确认后才执行。

### Phase 0.6 — 字幕同名化（与 Phase 0.5 同批处理）

字幕文件 = **视频文件名全名 + 语言标识 + 原扩展名**，同时从子夹提级到电影夹根目录：

```
改前: chs.srt / 简体中字.ass / Subs/xxx.sub
改后: The.Assassin.2015.1080p.BluRay.x264-ROVERS.chs.srt
      The.Assassin.2015.1080p.BluRay.x264-ROVERS.chs.ass
      Subs/The.Assassin....sub → 提级到根（idx/sub 对保留成对）
```

判定规则：
1. **无语言标识的字幕**：保留原名不造语言标签（用户定版）。
2. **字幕与视频不同压制版**（名字里的 release 组对不上）：**进回收站**——硬配会假装时间轴同步没问题。拿不准的列出来问用户。
3. **同语言多个字幕**（两个 .chs.srt 内容不同）：默认只留一个进回收站其余；或加 `.chs.1` 后缀区分——列计划表让用户拍板，不自作主张。
4. 语言标识识别顺序：原文件名已有 `.chs/.cht/.eng/.big5` 等标 → 沿用；无标但内容可判（如 BIG5 编码文本→cht）→ 建议标注并让用户确认；判不出 → 保持无名。

### Phase 0.7 — 结构规整：导演层只允许一层电影夹

导演夹下**不允许裸文件、不允许格式中间层**。三种病态结构按序处理：

**A. 裸视频收编建夹**（视频直接躺在导演层）：
```
王颖 Wayne Wang/
   中国匣.Chinese_Box_(1997).cd1.avi  ❌
   中国匣.Chinese_Box_(1997).cd2.avi     ↓ 新建电影夹收编整组
   中国匣 (1997)/                     ✅ cd1+cd2+nfo+海报一起进夹
```
- 同片聚合依据：文件名共同前缀（cd1/cd2/partN 是一部片不是多部）
- 新夹名按命名规范生成（缺年份/尺寸/格式用 ffprobe 实测），进计划表确认

**B. 并列格式层全部溶解**（`DVD / BluRay / 蓝光 / WEB / WEB-DL / HDTV / HDDVD` 等）：
```
贾法·帕纳西 Jafar Panahi/
   DVD/白气球.../  WEB/越位.../  蓝光/(...)   ❌ 三层并列全拆
      ↓ 全部电影整夹上提到导演层，格式夹空了就删
```
- **有几个拆几个**，不限一个；同一部片跨格式夹重复出现时，提层后触发去重三档流程（EXACT/QUALITY/EDITION），不默默堆两份
- **内容分类层不动**：`短片 / 纪录片 / 花絮` 不是格式层，保持原状出报告另议
- 格式夹内的散件 torrent/txt 进回收站，不跟着上提

**C. 处理顺序**：先 B 溶解格式层 → 再 A 收编裸视频 → 最后统一走 Phase 0.5/0.6 的 nfo/字幕配对。

### Phase 1 — 不规范文件名：ffprobe 读真实信息
对没有标准 release 名的视频（如 `m-tibi-1080p.mkv`），不要猜：
```bash
ffprobe -v error -select_streams v:0 \
  -show_entries stream=codec_name,width,height -show_entries format=duration,bit_rate \
  -of json "<video>"
```
- height→尺寸（1080）；codec_name h264/x265→格式；nfo 里的 AUDiO 行可补音轨（AC3/AAC）；
- 发布组从原文件名 token 里取；年份从旧文件夹名 `(YYYY)` 取。
- 新名 = `英文名.年份.尺寸.格式[.音轨]-发布组`，**每个 token 都要让用户在计划表里看到并确认**。

### Phase 2 — 生成计划表给用户确认（必做，不可跳过）
按电影逐条列三张表：
1. 文件夹改名：旧 → 新
2. 文件改名 / 字幕提级（子文件夹 → 根目录）
3. 删除清单（进 _trash_ 的每一项）

同时列出所有"拿不准的决策点"（如发布组写法、是否补音轨段）让用户拍板。
**用户回复确认后才执行。**

### Phase 3 — 执行（一个 set -e 脚本跑完）
顺序很关键：
```bash
set -e
mkdir -p "$TRASH"
# ① 字幕先提级到电影根目录，再 rmdir 空子文件夹
mv "$MOVIE/subdir/"*.srt "$MOVIE/"
rmdir "$MOVIE/subdir"
# ② 垃圾进回收站
mv "$MOVIE/xxx.zip" "$TRASH/"
# ③ 文件改名（保持大小写！）
mv "$MOVIE/超能查派Chappie.2015....mkv" "$MOVIE/Chappie.2015....mkv"
# ④ 最后改文件夹名（避免路径中途失效）
mv "$MOVIE_DIR_OLD" "$MOVIE_DIR_NEW"
# ⑤ 系统垃圾直删
find "$BASE" \( -name ".DS_Store" -o -name "._*" \) -type f -delete
```

### Phase 4 — 验证汇报
- `find` 全树复查：结构是否符合规范；
- `_trash_` 目录 ls 给用户看（里面有什么、多大）；
- 残留垃圾检查计数 = 0；
- 汇报格式：每部电影 ✅ + 改动明细 + trash 内容清单。

## Pitfalls

1. **先提级字幕再 rmdir 子文件夹**——顺序反了会报 Directory not empty。
2. **先 mv 文件、最后 mv 文件夹**——文件夹名先改的话后续路径全失效；一个 set -e 脚本里要用变量存旧路径。
3. **网络卷（SMB/NFS）上的 `._*` 可能在 find -delete 时已消失**——报 "No such file or directory" 属正常，set -e 下给 find 单独跑或容忍该错误。
4. **`find -delete` 需要终端审批**——预估会被拦，提前说明用途；或拆成不带 -delete 的 find + xargs rm 分步。
5. **中英混排文件名含空格和 `·`**——所有变量必须双引号包裹；mv 源路径逐字符复制自 find 输出，不要手打。
6. **ffprobe 在网络卷上较慢**——单文件可接受；批量时先拷贝到本地 /tmp 再 probe 会快很多。
7. **zip 里可能就是字幕包**（例：battle_los_angeles_*.zip 内含 srt）——解压检查确认内容已在别处存在后才准进 trash；若 zip 是唯一字幕来源，先解压提级再删 zip。
8. **用户会核对每一个字符**——计划表里的新名字要一字不差地展示，包括大小写和连字符数量；执行时的 mv 参数必须与计划表完全一致。

## 大洋州实战补充（2026-08-22，46 部）

### 用户拍板的新决策（后续大洲沿用）
1. **导演文件夹统一空格式**：`中文名 EnglishName`（如 `安德鲁·多米尼克 Andrew Dominik`），点格式 `戈兰·斯托列夫斯基.Goran Stolevski` 全部改为空格式。
2. **非标准视频名重构**（ffprobe 实测后）：`英文名.年份.尺寸.h264.音轨-发布组`，发布组保留原写法（`sector7-lordofwar.1080p-x264` → `lord.of.war.2005.1080p.h264.dts-sector7`）。若原文件夹名已是规范 release 名，文件向文件夹名对齐（我机器人 dfn_* → I.Robot...DEFiNiTE）。
3. **字幕包 rar/zip**：解压提级到电影根 → 包进回收站。DBfansub 这类"只有字幕没有视频"的整包 → 回收站。
4. **字幕与视频不同发布版**（时间轴可能不齐）→ 进回收站。
5. **合集/** 目录不是导演：查实际导演建新导演文件夹移入。
6. 文件夹年份 vs release 年份冲突时按 release（空气之魂 1988→1989）。

### 新踩坑
9. **UUID"目录"可能是 6KB 文件**——先 `ls -la` 确认类型再 rmdir/mv。
10. **SMB 卷上读过的文件会重新生成 `._*` 残影**——每阶段结束后都要重跑一次 `._*` 清理，最终验证前再跑一次。
11. **@MOVEDIR@ 跨目录移动时目标父路径拼接容易错**——本次把戈兰/瑞秋·沃德/库泽尔错误放到了大洋州顶层而非澳大利亚下，靠最终 find 全树检查发现并归位。跨洲移动后必须复查顶层结构。
12. **Python 脚本内函数定义顺序**——to_trash_safe 在定义前被调用导致 NameError；脚本要先把所有函数定义放顶部。
13. **终端审批对 find -delete / 批量 mv 敏感**——改用 execute_code 内跑 Python os.rename/shutil 更稳，或拆小步。
14. **无 nfo 的电影是原始状态**（20/45 部本来就没有）——不算问题，不补造。

## 亚洲实战补充（2026-08-22，~1500部/11国，去重+归类新增能力）

### 去重流程（用户定版）
1. 全量收集视频(名/大小/路径) → 按标题+年份分组 → 三档分类：
   - **EXACT**：同名同大小 → md5 实锤后删副本（保留规则：导演目录>合集>散件；正名>(1)目录）
   - **QUALITY**：按用户标准只留最优（4K>1080p>720p；同分辨率留大码率）；sample 直接删
   - **EDITION/MULTI**：CC版vs普通版、EXTENDED vs 剧场版等 → 默认全保留
2. **假重复甄别**：CD分片(cd1/cd2/partN)不是重复；不同片名被年份配对是误分组（塚本死亡解剖vs恶梦侦探）——跨目录组必须人工核对片名再删
3. md5 抽查用前32MB即可区分压制版本
4. 用户裁决案例：A沟口祇园姊妹vs浪花悲歌=1936年两部不同片都保留；B双压制留有nfo的

### 大库操作技巧
5. SMB 大卷 os.walk 会超时——按国家/导演分批跑，每批<175s；后台跑+轮询不可靠时改前台分片
6. 视频统计含 BDMV 原盘结构（m2ts在STREAM/），不算普通视频文件
7. NFD Unicode 目录名（日文 ô=о+ˆ）：os.path.isdir 对 join(path, name) 可能 False，用 scandir 的 entry.is_dir() 才准
8. 一导一片的国家层目录「导演 (年份)」= 导演层简化形态，改名去掉年份括号即成标准导演层

### 合集拆解流程（日本实战定版）
9. 先列导演目录全集，再逐片查证导演归属；导演目录不存在的用 `中文名 EnglishName` NFC 格式新建。
10. 同片不同压制（KOOK vs WiKi 等）：md5 前32MB 对比，DIFF 时保留带字幕/更实用的一份，另一份进回收站。
11. **NFD 幽灵条目**：SMB 卷上 NFD 分解式 Unicode 名（ô=о+ˆ）的目录/文件 scandir 可列出但 join 路径后 stat/move 全部 ENOENT，ls/find 也不可见——这是客户端缓存残影。无法访问即跳过并记录报告；新建同名目录用 NFC 规避。文件名含 NFD 字符（如 Lazarová）同理。
12. 非本国影片混入（旬报里的捷克/南斯拉夫片）→ 移到媒体根 `_非日本片_待归类/` 暂存出报告，不自作主张归大洲。
13. 纪录片（NHK等无单一导演）、美国翻拍日本故事（忠犬八公）、动画TV系列 → 留合集出报告让用户定。

### 已完成实例补充
- 2026-08-22 日本合集拆解：合集44项→剩5项（纪录片×2/美国片×2/动画TV系列），粉红系22项→剩14项（多导演粉红片留原处），电影旬报26散文件全部处置（导演归位12/重复删8/非日本片暂存5+1幽灵）。新建导演目录约25个（含NFC规避NFD幽灵：大岛渚 Nagisa Oshima 等）。
- 2026-08-22 香港拆解：银河→杜琪峰26部，香港合集29→6，三级片37→22，导演目录28→51。台湾误放片移中国台湾/合集。
- 2026-08-22 韩国拆解：其他合集32→12（幽灵条目6个无法访问），下女1960双压制留CC删MiniSD，隧道归金容华。
- 2026-08-22 中国拆解：华语经典合集65→12，其他73→32。万玛才旦.zip实为目录已正名。跨区移动：热带雨→南亚/陈哲艺、沦落人→香港/陈小娟、日本片×3→日本、只是意外(帕纳西)→西亚。

### 脚本防呆教训
15. mv目标目录名里带"?"或"不对"等查证备注会真实创建目录——先想清楚再写代码，目录名必须是最终规范名。
16. 跨层嵌套错误（A/B两层同名目录）：移动后立即listdir验证扁平性。
17. **`movie.nfo` 配对只认"所在电影夹内的视频"**——绝不允许全局按文件名找视频配对；一夹多视频时不自动猜配，进待裁决清单。孤儿 movie.nfo（无视频）不动不删，出报告等用户。
18. **异版字幕硬配是自欺**——release 组对不上的字幕改名后 Kodi 照样加载，但时间轴可能全乱；宁可进回收站或问用户。
19. **格式层溶解前先查撞车**——同一部片在 DVD/ 和 WEB/ 各有一份时，提层瞬间制造重复；提层清单要预先做跨格式夹的片名比对，撞车的标出去重流程。
20. **华语导演英文名不许猜**——豆瓣/TMDB/IMDb 三源任一确认后才写进夹名；拼错导演英文名会破坏刮削器匹配（Kar Wai Wong ≠ Karwai Wong）。
- 2026-08-22 亚洲阶段A+B：王颖(1)合并、以伊黎并入西亚、UUID×5清理、42个冗余文件170GB进回收站（`_trash_亚洲_20260822/`）。剩余：合集拆解(C)和改名(D)按国推进。

## 已完成实例
- 2026-08-22 `/Volumes/115open/Media/Movie/非州/`：3 部电影全部规范（洛杉矶之战/超能查派/土狼之旅），trash 位于 `/Volumes/115open/Media/Movie/_trash_非州_20260822/`。
- 2026-08-22 `/Volumes/115open/Media/Movie/大洋州/`：45 部电影全部规范，5 个 UUID 垃圾、10+ Sample、全部 torrent/txt/rar/海报图清理完毕，点格式导演统一为空格式，合集→瑞秋·沃德 Rachel Ward 新建归位。trash 位于 `/Volumes/115open/Media/Movie/_trash_大洋州_20260822/`。验证：45 视频=45 文件夹，0 垃圾残留，0 空目录。
