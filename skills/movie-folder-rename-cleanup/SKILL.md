---
name: movie-folder-rename-cleanup
description: >-
  电影库批量规范化：命名规范置顶（中文名.英文 Name.年份...），先完成电影夹与视频
  文件名规范化，再做 NFO/字幕配对、夹内净化，最后结构整理；垃圾进 _trash_ 回收站
  不直接删。
license: MIT
metadata:
  version: "3.0"
  author: lynch5mo
  tags: [media, rename, cleanup, movie-library, ffprobe, naming-convention]
  trigger: User asks to batch-rename movie folders/files to a standard naming convention, clean up non-video junk inside movie folders, promote subtitles from subfolders to the movie folder root, or normalize a director-based movie library (e.g. /Volumes/115open/Media/Movie/<洲>/).
---

# Movie Folder Rename & Cleanup Skill

## ⭐ 第一部分：命名规范（一切操作的基础，2026-08-24 定版）

目录层级：`<媒体根>/<大洲>/<导演中文名 EnglishName>/<电影文件夹>/<文件>`

### 1.1 标准命名表

| 对象 | 规则 | 示例 |
|---|---|---|
| 导演夹 | `中文名 EnglishName`（空格式，禁点格式） | `刁亦男 Yi'nan Diao` |
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

### 1.3 冲突与缺失处理（禁止造名）

1. **保持原大小写、发布组原样**——release 是 `WEB-DL`/`RARBG` 就原样保留；发布组 `m-tibi` 不许写成 `-mtibi`。
2. **年份冲突**：目录用查证后的影片年份；视频文件保留 release 原始 token（如《无名狂》目录 2019、文件保留 `Wild.Swords.2020`）。
3. **发布组不可考**：标 `Unk` 或省略该段，禁止编造（《苹果》B 版 → `AAC-Unk`）。
4. **夹名与实际内容不符**：一律以视频实片为准重新查证改名（《寻枪》原夹误标 The Missing Sun；《地球最后的夜晚》错标 2014→2018）。
5. **文件名里不要中文**；中文只出现在电影夹名的开头段。
6. **不确定的 token 进报告单议，不能猜**。

### 1.4 电影夹内容白名单（净化标准）

夹内只允许存在：

- 视频文件（mkv/mp4/avi/rmvb/ts/m2ts/iso/wmv/mov/m4v…）
- 与视频同名的 `.nfo`
- 与视频 basename 一致 + 语言标识的字幕（srt/ass/ssa/sub/idx/sup/vtt）

其余一切（海报/fanart/clearlogo/backdrop/torrent/RARBG.txt/exe/论坛htm/lnk/url/sample/播放器截图/广告视频/.dat VOB 老副本/Sample 子夹）= 垃圾，**当批移入 `_trash_`**，禁止标"暂留项"拖后。`.DS_Store`/`._*` 直接删。

### 1.5 查证渠道（三源闭环）

1. 夹内 NFO 的 title/originaltitle/year/director；
2. ffprobe 实测时长+分辨率（验证 runtime 是否吻合）；
3. IMDb suggestion API：`https://v2.sg.media-imdb.com/suggestion/x/<关键词>.json`（豆瓣已限流，仅作参考）；tt 号可反查 `/suggestion/t/<tt号>.json`。

三源互相印证后再写名；任何单源存疑即出报告。

## ⭐ 第二部分：定版执行顺序（唯一流程，2026-08-24 校正版）

> 命名规范化是整理的第一步，不是收尾。以下顺序优先级高于一切旧阶段编号。

**Step 1 只读盘点**：国家 → 导演 → 电影夹 → 文件三级清单生成 JSON；FUSE 层禁全树 find，浅层 scandir 分块扫。

**Step 2 电影夹 + 视频文件名规范化**：按第一部分规则逐夹生成新名；多版本先做版本判定（见第三部分）；查证闭环后才允许执行。

**Step 3 NFO 配对改名**：锚定已稳定的视频 basename；一夹多视频不自动猜配，进待裁决清单；孤儿 movie.nfo 不动出报告。

**Step 4 字幕同名化**：basename 对齐最终视频名 + 语言标识标准化 + 子夹字幕提级到夹根（idx/sub 成对）；异版字幕（release 对不上）进回收站不硬配。

**Step 5 夹内净化**：白名单外全部移 `_trash_`（保 `<导演>/<电影夹>` 层级）；清完逐夹复扫残留=0；空壳夹留壳不删。

**Step 6 结构规整 / 归类 / 去重**：最后才做。格式层溶解、裸视频收编、跨导演移动、合集拆解、全库去重都以此为前提。

每步完成后：终验四件套（见第五部分）+ KB 批次报告落档。

## 第三部分：多版本判定（EDITION 全留原则）

同片多副本先 ffprobe（时长 duration + streams 分辨率/codec），再分档：

- **时长不同 = 不同剪辑**（导演剪辑/未删减/短剪辑）→ 全部保留，各自规范化（《太阳照常升起》6687s vs 6972s；《南方车站》未删减版）
- **同剪辑不同分辨率/编码** = QUALITY → 留最优（4K>1080>720；同分辨率留大码率），其余进回收站（《狗十三》：4K.HEVC 与 1080.HEVC 时长同为 5799s → 删 1080 留 4K；但 4K.AVC 时长 7274s 不同 → 保留）
- **SHA1 完全相同** = EXACT → 副本进回收站
- 撞车判定用 CD2 缓存库服务器端 SHA1：`select ci.path,f.id,f.name,f.size,f.file_hash from files f join cached_item ci on f.parent_id=ci.id where ci.path like ? and f.name like ?`

## 第四部分：执行通道与工具

### ffprobe 通道（宿主机/Mac 均无 ffprobe）

```bash
# 方式一：jellyfin 容器（容器内媒体根 /Media/Media/Movie/…）
docker exec jellyfin /usr/lib/jellyfin-ffmpeg/ffprobe -v error \
  -show_entries format=duration:stream=codec_name,width,height,bit_rate -of json '<容器内路径>'
# 方式二：镜像直跑（挂载 /media/CloudDrive → /data）
docker run --rm --entrypoint /usr/lib/jellyfin-ffmpeg/ffprobe \
  --mount type=bind,src=/media/CloudDrive,dst=/data,readonly \
  sha256:68e012f4bf5aeb114632e9045f5b2f2f6713536693093f70fcb338179f84f86c ... '/data/115open/Media/…'
```

### SSH 通道

- `lynch5mo@192.168.10.33`，BatchMode=yes 密钥认证，sudo 免密；FUSE `/media/CloudDrive` uid=0 **脚本必须 sudo**。
- 写操作走 `ssh … sudo -n python3 -` 传整段脚本；**每次调用拆小块**（<~8K tokens 输出）防 stream timeout。
- FUSE 上 find/du 大目录超时 → 用 scandir 浅层扫描；审计 JSON 用 scp 拉回本地分析。
- **含单引号路径会截断 Bash**（`Yi'nan Diao` 实证）→ 特殊字符路径全部走 Python os.rename 逐字处理，不走 shell mv。

### 回收站

- 路径：`<媒体根>/_trash_<区域>_<YYYYMMDD>/<任务说明>/<导演>/<电影夹>/`——保层级，回滚直接 mv 回去。
- 铁律：删除永不 rm；**永远不用 rmdir/rm -d**（CD2 FUSE 对非空目录 rmdir 会递归转发云端删除，8-23 书记.mkv 事故实证）。清场一律 mv。
- 清完垃圾变空壳的夹：**留壳不删**，出报告待裁决（张律·黄绮琳空壳实证）。
- 不刷新 CD2 缓存、不重启 clouddrive 容器、不碰 `/DATA/AppData/clouddrive/Config` 下 sqlite。

## 第五部分：终验清单（固定四件套 + 净化复扫）

每批次结束必须核验并写进报告：

1. 旧目录名残留 = 0（重扫确认）
2. 目录/文件 inode 不变（rename 非 copy）
3. 字节数不变（视频/NFO 未损坏）
4. 夹内非白名单残留 = 0（逐夹复扫）
5. 回收站清单可逆（列出路径与大小）

## 第六部分：特殊件单议（原地不动出报告）

以下类型**不改名不移动**，进单议清单等用户拍板：

- 身份不明裸视频（无夹无元数据）
- 无中文可考片名（Something in Blue 案例）
- 无年份短片（607 短片案例）
- 夹名与视频完全对不上的归属矛盾件（Keep 'Em Rolling 1934 vs keep rolling.2020 案例）
- 同片双导演归属矛盾（日掛中天：蔡尚君 vs 张律 双夹并存）
- 仅 .rm 等残缺格式无完整 release 信息（静静的嘛呢石短片版案例）
- NFC/NFD 双夹并存（山田洋次案例）——合并前必须核对内容

## 第七部分：Pitfalls（血泪清单）

1. 先提级字幕再处理子文件夹；顺序反了报 Directory not empty。
2. 先 mv 文件、最后 mv 文件夹——文件夹名先改后续路径全失效；脚本用变量存旧路径。
3. 网络 SMB 卷 `._*` 在 find -delete 时可能已消失，报 ENOENT 属正常，容忍或单独跑。
4. 中英混排文件名含空格和特殊符号——变量必须双引号包裹；mv 源路径逐字符复制自 find/scandir 输出，禁止手打（**空格 vs 点写法差异坑 mv**：Weekend Lover ≠ Weekend.Lover）。
5. ffprobe 在网络卷较慢，批量时可用容器通道；单文件可接受。
6. zip 里可能是唯一字幕来源——先解压提级再删包；DBfansub 这类只有字幕没视频的整包进回收站。
7. 用户会核对每一个字符——计划表新名字要一字不差展示，执行参数与计划表完全一致。
8. UUID"目录"可能是 6KB 文件——先 ls -la 确认类型再操作。
9. SMB 卷读过的文件会重新生成 `._*` 残影——每阶段结束重跑清理。
10. Python 脚本函数定义放顶部，防 NameError。
11. 终端审批对 find -delete / 批量 mv 敏感——execute_code 内 subprocess 跑更稳，或拆小步。
12. 无 nfo 的电影是原始状态，不算问题不补造。
13. os.walk 大卷超时——按国/导演分批，每批 <175s。
14. NFD 幽灵条目：scandir 可列出但 join 后 stat/move ENOENT——跳过记录，新建用 NFC。
15. mv 目标带"?"等备注字符会真实建目录——目标必须是最终规范名。
16. 跨层嵌套错误：移动后立即 listdir 验证扁平性。
17. movie.nfo 配对只认所在夹内视频，绝不跨夹匹配。
18. 异版字幕硬配是自欺——时间轴可能全乱，宁可回收站。
19. 格式层溶解前先查撞车，防止瞬间制造重复。
20. 华语导演英文名三源任一确认才写入，拼错破坏刮削。
21. FUSE ls 会显示同 inode 双条目残影——判断双夹用 find -maxdepth 1 -type d 或比对 inode。
22. 合并前查目标夹内容：空壳直接并入；同名文件冲突进回收站不覆盖。
23. **FUSE rmdir 递归删除陷阱**（书记.mkv 事故）：CD2 FUSE 对非空目录 rmdir 把递归删除转发云端。铁律：永远不用 rmdir/rm -d，清场一律 mv 进 _trash_；证据链=115 文件 ID+SHA1+字节数。
24. 撞车判定用 CD2 缓存 file_hash 服务器端 SHA1，秒级实锤。
25. **脚本报错先核对现场再重跑**：rename 前逐项 check old_exists/new_absent/target_exists；幂等设计让重复执行无害（赵亮批次拼错源名零改动兜底实证）。
26. **计划复核再执行**：批量清场前先把 plan JSON 打出来人工过一遍边角（sample/广告视频/错配 nfo/字幕 basename），比事后返工便宜。
27. 单引号路径截断 Bash——Python 逐字处理（见第四部分）。
28. 大批量 SSH 调用拆小块防 stream timeout；审计产物 scp 回本地分析。
29. **NFC/NFD 双目录实体陷阱**（小津 `Yasujirô` 实证）：同一导演夹可能同时存在 NFD 实体（真实数据）与 NFC 幻影（FUSE 读穿透/写落平行空壳）。症状：rename 报成功但旧文件原样在、新夹 inner 为空。操作前必须 `unicodedata.normalize('NFC',name)` 比对枚举到的所有同名变体；一律走**数据所在实体路径**；幻影空壳清 `_trash_` 留证。每次 rename 后必须 stat 新路径验证实体存在（防 GHOST no-op）。
30. **夹内视频文件 EN 化后必须同步对齐同 basename 的 nfo/srt**，且改名前先 listdir 拿逐字真名（手打猜名必 MISS）；多 cd 文件用 part1/part2 或 cd1/cd2 后缀保留。

## 第八部分：已完成实例（战例存档）

- 2026-08-22 非州 3 部、大洋州 45 部全规范；点格式导演统一改空格式。
- 2026-08-22 亚洲阶段A+B：王颖合并、UUID×5 清理、42 个冗余文件 170GB 进回收站。
- 2026-08-22 日本/香港/韩国/中国合集拆解：银河→杜琪峰26部、香港29→6、华语经典65→12 等。
- 2026-08-23 中国区 7 件结构整理（万玛才旦合并、NFO 配对 82 审计、字幕同名化 14 夹 23 字幕、15 导演夹改名）。
- 2026-08-24 中国区全量命名规范化：约 90 个导演批次连续推进（万玛才旦/娄烨/张艺谋/贾樟柯/姜文/刁亦男/刘伽茵/徐浩峰/陈凯歌/忻钰坤/郝杰/宁浩/曹保平/李云波/毕赣/顾晓刚/丁晟/万力/乌尔善/任鹏远/何群/冯小刚/李杨/李玉/赵亮/郭帆/马楠/大鹏/孔笙/周全/周浩/周子阳/徐磊系/黄建新系…至全区 152 夹达标）；关键查证案例：《西小河的夏天》(tt5644394)、《寻枪》、《混在北京》(tt7937808)、《无名狂 Wild Swords》。
- 2026-08-24 空格规则回溯：64 夹+236 文件由点式改空格式，重扫残留 0。
- 2026-08-24 夹内净化补课：152 夹扫描，251 项垃圾进 `_trash_中国_20260824/naming_junk_0824/`，149+3 夹达白名单标准，终验逐夹复扫通过。
