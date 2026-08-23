# SMB 回滚参考：匹配、批处理与报告

## 1. 推荐计划字段

每个恢复动作至少记录：

```json
{
  "src": "/卷/_rollback_staging_区域/国家/新导演/影片/文件",
  "dst": "/卷/亚洲/国家/原导演/影片/文件",
  "level": "exact_context | relaxed_movie_context | explicit_trash_map",
  "source_kind": "current_extra | staging | trash | quarantine",
  "evidence": "影片目录名+相对路径；或 UUID 前缀+历史目录上下文"
}
```

执行前验证 `src` 存在、`dst` 不存在，并检查整个计划的源路径唯一性。执行后立即验证目标出现、源消失；失败项不自动改用另一个候选。

## 2. 影片根目录推断

从文件路径的父目录向上查找包含视频的最深目录，但排除 `BDMV`、`STREAM`、`CLIPINF`、`Sample`、`Subs`、`CD1`、`CD2` 等结构目录。计算祖先路径时必须包含完整的直接父目录：

```python
def ancestors(parent):
    if not parent:
        return []
    parts = parent.split(os.sep)
    return [os.path.join(*parts[:i])
            for i in range(1, len(parts) + 1)]  # +1 很重要
```

漏掉 `+1` 会把 `影片/文件.mkv` 误判成导演目录，进而让合集→导演、国家合并和同影片附件匹配失败。这是一次实际调试中发现的边界错误。

建立键时优先使用：

```text
(filename, normalized_movie_root, relative_path_inside_movie_root,
 normalized_director_context)
```

导演名只做 NFC、去空格/点号的比较；影片目录名和影片内相对路径仍必须一致。导演格式变化（点格式/空格格式、中文英文之间空格差异）不能成为跨影片匹配的理由。

## 3. 安全放宽顺序

对每个目标按顺序尝试，且全局锁定已使用源：

1. 原始路径或回收站保留的原始子树路径。
2. 文件名 + 影片根目录名 + 影片内相对路径 + 导演规范化。
3. 文件名 + 影片根目录名 + 影片内相对路径（合集和导演目录变化时）。
4. 只有 release 文件名、UUID 前缀等真正独特的 basename 才允许全局唯一匹配。

第 4 层禁止用于 `movie.nfo`、`poster.jpg`、`landscape.jpg`、`fanart.jpg`、`backdrop.jpg`、`logo.png`、`folder.jpg`、`clearlogo.png`。这些文件即使在当前候选池“只出现一次”，也可能只是因为其他源暂时不可见，不能跨影片猜测。

## 4. 整目录优化

先生成逐文件计划，再按源影片目录分组。只有以下集合相等时才转换成整目录移动：

```text
all_actual_files(source_root) == snapshot_files(target_root)
```

同时检查：

- 目标目录不存在；
- 源目录计划没有父子嵌套；
- 目录内没有额外未确认文件；
- 目标和源不是同一路径。

如果计划有父子嵌套，按源路径长度排序，只保留最上层已经完成集合比较的计划。否则父目录成功后，子目录会产生“源不存在”的假错误。

## 5. SMB 批次检查表

每一批执行前：

- [ ] 扫描范围只有一个国家/导演批次
- [ ] 计划源路径全局唯一
- [ ] 通用附件没有 basename-only 映射
- [ ] 目标不会覆盖现存文件
- [ ] 回收站和暂存区仍保留

每一批执行后：

- [ ] `moved == expected`
- [ ] `failed == 0`
- [ ] 每个目标存在
- [ ] 每个源已消失或已被父目录移动
- [ ] 重新生成下一批实际清单，而不是沿用旧索引
- [ ] 记录本批的 skipped、ambiguous、missing

SMB 延迟高时每批约 40–100 个文件；整目录集合验证通过时可按目录批量。不要在一次命令中扫描、判断、移动整卷，超时后无法判断副作用边界。

## 6. 旧索引和幽灵条目

一次 `scandir` 的 JSON 只是当时观察结果。后续移动后，旧路径可能已经不存在；任何旧计划都要用当前实际路径再次过滤。

若条目能被 `scandir` 列出，但 `stat`、`isdir`、`rename` 通过完整路径返回 `ENOENT`：

- 记为 `unreachable_nfd_ghost`；
- 不重试、不删除、不据此创建“已恢复”结论；
- 报告原始 Unicode 路径；
- 需要替代目录时使用 NFC 名称，并明确是规避缓存的替代物。

## 7. 报告模板

```text
区域：亚洲/韩国
快照文件总数：...
原位或已恢复：...
仍在 staging/trash：...
缺失视频：...
缺失字幕/nfo/图片：...
歧义未自动移动：...
SMB 不可访问幽灵：...
本批失败：...
```

“恢复完成”只在逐国复核完成后使用；如果仍有任何未核实国家，使用“部分恢复完成”。回收站和暂存区保留到用户确认后再处理。
