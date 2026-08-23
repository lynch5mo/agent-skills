# CloudDrive2 × 115 隐身文件救援手册（2026-08-23 实战验证）

用户媒体库的真实挂载链路（此前被误认为"Mac 直连 115"）：

```text
Mac (SMB 挂载 /Volumes/115open)
  └─ Ubuntu NAS 192.168.10.33（SSH 用户 lynch5mo，密钥认证，sudo 免密）
       └─ Docker 容器 clouddrive（cloudnas/clouddrive2）
            ├─ FUSE 挂载点 /media/CloudDrive
            └─ 配置目录 /DATA/AppData/clouddrive/Config/*.sqlite   ← 勿动原件
```

CD2 Web UI：http://192.168.10.33:19798

## 事故机制（已实锤，取代"降级上传"猜想）

容器日志出现 N 次 `rename uploadfile failed：文件名不能为空` ⇒ CloudDrive 向 115 发改名请求时名字字段变空被拒 ⇒ 文件在 115 的**目录索引**里变成空名隐身：

- 115 App / 网页 / 官方回收站全部看不到（从未发生删除，所以回收站也没有）
- 文件本体和文件 ID 在 115 服务器上完好
- CloudDrive 能照常播放（按文件 ID 向 115 开放平台换直链，绕过坏目录树）
- 三层各见各的真相：115 服务器（本体活着）/ CD2 缓存库（有 ID 有名字有大小）/ FUSE-SMB 层（目录壳读不了）

## 取证步骤

1. 只读拷贝配置库到本机再分析（**不要**在远端用 `>` 重定向写回远端路径）：
   ```bash
   ssh nas 'sudo cp /DATA/AppData/clouddrive/Config/dir_cache.sqlite /tmp/ && sudo chmod 644 /tmp/dir_cache.sqlite'
   scp nas:/tmp/dir_cache.sqlite /tmp/cd2_db/
   ```
2. 关键库：
   - `dir_cache.sqlite`：~9 万条文件记录（115 文件 ID、SHA1、原始名、大小）。文件挂在 cached_item 目录条目下，**必须 JOIN 不能嵌套枚举**：
     ```sql
     SELECT f.id,f.name,f.size,c.path FROM files f
     JOIN cached_item c ON f.parent_id=c.id WHERE c.path LIKE '/115open%';
     ```
     注意库内路径前缀是 `/115open/...` 不是 `/media/CloudDrive/115open/...`，LIKE 模式要写对。
   - `clouddrive_data.sqlite`：admin_tokens（值永不回显）、transfer_tasks。
   - `fileproperties.sqlite`：disk_cache_folders 空 ⇒ NAS 本地无内容缓存。
3. 对照实扫：NAS 上 `find /media/CloudDrive/115open/Media/Movie -type f -printf '%s\t%P\n'` 可跑通但 ~30 分钟；**FUSE 上对大树跑 `du` 或全树 `find` 极易超时（>240s 实测）**，能用缓存库 SQL 回答的问题不要碰 FUSE。
4. 判定"隐身"：缓存库有记录 + 字节数已知 + 实扫/FUSE 读不到 ⇒ 服务器端索引问题，不是数据丢失。

## 救援手段（按实战优先级）

1. **首选：用户在 CD2 Web UI 手工"移动到云下载"**。按 ID 的服务器端操作，完全绕开坏目录列表。实测滨口 7 部 78.7GB 一次成功，随后逐部核对字节数与缓存记录精确一致即算救回。整夹移动同样可行（回收站归档也用这一招：一条 `mv` 秒完成，可逆）。
2. 备选（未走通不必先试）：115 开放平台 `/open/ufile/downurl` 按 ID 换直链；CD2 本地 gRPC `FileDownloadUrl`。admin token 在 clouddrive_data.sqlite 里可读但对话中绝不回显值。

## 纪律（救援完成前）

- 不刷新 CD2 目录缓存、不重新扫描、不重启 clouddrive 容器
- 不删 Config 下任何 sqlite
- 大批量移动以后改在 115 App/网页端做；经挂载点的批量操作每小批双向刷新验证（App 看一眼 + 挂载 rescandir）

## 2026-08-23 战果速查

- 事故指纹：当日 6×「rename uploadfile failed」
- 受害者：亚洲库滨口龙介 7 部（快照里该目录为 0 条＝快照抓自失真视图的证据）
- 救援：Web UI 移云下载 → 7/7 字节精确一致
- 全库复查：亚洲 0 隐身残留；欧洲 18 个"隐身"实为用户确认正常的目录，不救
- 教训：快照若来自失真视图本身就是错的——落盘后必须抽查已知存在的知名目录，发现"某导演整目录为空"当场提出
