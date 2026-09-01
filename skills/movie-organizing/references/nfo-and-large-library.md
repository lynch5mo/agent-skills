## v1.3.6：NFO 身份门禁与大库批次卡

这张卡只补充流程细节；命名仍以 [naming-contract.md](naming-contract.md) 为唯一权威。
Agent 不手写 NFO、不猜 TMDb/IMDb ID，也不把主观 confidence 当作匹配结果。

### NFO_GATE

1. `movie_organizing_nfo.py plan` 只从已经通过命名预处理的 active 单片读取最终视频 stem、年份、导演夹和可选 `ffprobe` 时长。
2. 脚本通过 TMDb v3 `search/movie`，再对候选逐一调用 `movie/{id}`、`alternative_titles`、`credits` 和 `external_ids`。标题比较只做 Unicode/重音/标点归一；年份、导演必须严格相符，时长存在时误差不超过 5 分钟。
3. 只有过滤后恰好一个候选才允许 `AUTO_CREATE`；0 个、多个、API/ffprobe/解析失败均为 `PENDING_*`。已有 NFO 不覆盖：即使有 TMDb ID 也必须重新查询并核验标题、年份、导演及 IMDb 关联，失败进入待确认。
4. `AUTO_CREATE` 先把同视频 stem 的 XML 写入 `_work-record_/nfo-staging/`，验证 XML、TMDb ID 和 staging hash 后才可原子落盘。正式 `verify` 通过后才写 `nfo-identity-lock-*.json`；后续 fresh audit 必须同时验证视频指纹、NFO hash、TMDb ID 与 identity-lock。
5. 选中批次的 `PENDING_*` 会生成同一 NFO 事务中的 `pending_isolation`：只把完整电影夹移到当前 `TASK_ROOT/_待确认_/原导演路径/原电影夹`，保留目录上下文；计划记录 source/target/tree hash/evidence/rollback。目标冲突、symlink、树漂移或隔离验证失败即 STOP，不得猜名或原地反复规划。
6. 固定链不可跳步：

   ```text
   nfo plan → nfo apply --dry-run → nfo apply → nfo verify →（deferred=0 时）fresh audit
   ```

   仍有未隔离的 pending 才能 `STOP_PENDING_CONFIRMATION`；隔离完整后继续下一批。大库
   `deferred_count>0` 时跳过已锁定条目直接生成下一批，不能先做全树 audit；全部批次结束后
   才做 fresh full-tree audit。没有 identity-lock 的旧 NFO 不是 PASS。

### large_library_mode

当 active 视频 >20、导演数 >3 或预估动作 >50 时，脚本强制 `large_library_mode`。清单写入
`TASK_ROOT/_work-record_/inventory.jsonl`，进度写入 `progress.json`；Agent 不把全量清单或长日志装进上下文。

- 每个批次只选一个导演、最多 10 个视频单元；异常 slowpath 模板最多 5 项。
- 命名批次必须 `plan → apply --dry-run → apply → verify → seal`；`seal` 只有正式命名 verify PASS 才能写入 `sealed=true`，之后 fresh audit 决定下一批。
- 任何计划 hash、旧/新路径、数量、scope、NFO ID 或验证结果漂移均为 circuit breaker：`next_allowed=null`，不得继续。
- 恢复或上下文压缩后只运行 `movie_organizing_task.py status`，以 JSON 的 `next_allowed` 为准；`progress.json` 不能自证完成。

API key 仅从 `TMDB_API_KEY` 环境读取，不写入计划、日志、recovery 或包文件。所有 rollback 都是
`_work-record_/recovery/` 内可追溯的移动，不使用删除媒体或控制目录的原语。
