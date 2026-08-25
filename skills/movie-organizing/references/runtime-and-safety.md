# Runtime and Safety Details

仅在遇到远程卷、容器工具、特殊路径、sidecar 配对或回收站问题时读取本文件。

## 工具通道

- 宿主机/Mac 可能没有 ffprobe。优先使用 jellyfin 容器内 `/usr/lib/jellyfin-ffmpeg/ffprobe`；镜像直跑时以 readonly bind mount 暴露媒体，不复制数据。
- SSH/FUSE 场景先核对主机、挂载点和 uid。脚本化写操作经 `sudo -n python3 -` 传整段脚本，每次调用拆小块，防止 stream timeout。
- 审计 JSON 先在远端生成，再拉回本地分析；不要把全库枚举结果塞进对话。
- 含单引号、空格、Unicode 变体的路径不走 shell 字符串拼接；用 Python `os.scandir` 枚举和 `os.rename` 逐字处理。

## FUSE 与 Unicode

- 大卷禁用全树 `find`/`du`/`os.walk`；按国、导演或电影夹浅层分块扫。
- 操作前用 `unicodedata.normalize('NFC', name)` 比对同名 NFC/NFD 变体；一律走数据所在实体路径。
- FUSE 可能显示同 inode 双条目或幻影空壳。rename 后 stat 新路径确认实体存在；幻影清 `_trash_` 留证。
- NFD 条目可能 scandir 可见但 join/stat/move 报 ENOENT；跳过记录，不重试轰炸。

## Sidecar 与字幕

- 改视频 basename 前 listdir 获取逐字真名，禁止手打猜测。
- 视频改英文名后同步对齐同名 `.nfo` 和字幕；idx/sub 必须成对提级。
- 子夹先提级内容再处理子夹，避免 Directory not empty。
- 孤儿 `movie.nfo` 不动出报告；一夹多视频不自动配；zip 内可能是唯一字幕来源时先安全提取评估，再决定保留或回收。
- 异版字幕不硬配，时间轴错位风险高，直接进回收站清单。

## 回收站与清场

- 路径：`<媒体根>/_trash_<区域>_<YYYYMMDD>/<任务说明>/<导演>/<电影夹>/`，保留原层级便于回滚。
- 白名单外项目整批 `mv` 进对应回收站；禁止 `rm`、`rm -rf`、`rmdir`、`rm -d`。
- CD2/FUSE 对非空目录的 rmdir 可能递归转发云端删除，因此即使目录看似空也只用 `mv`。
- 清完垃圾变空的夹留壳不删，报告中待裁决。
- 不刷新 CD2 缓存、不重启 clouddrive 容器、不改其 sqlite。

## 执行前检查

每项 rename/move 前核对：old exists、new absent、target parent exists、target name 与计划逐字一致、source/target 都不是幻影路径。幂等设计允许重复运行时零改动或安全跳过，但不允许覆盖。
