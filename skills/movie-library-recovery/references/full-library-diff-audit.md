# 全库差异审计脚本（一次遍历 + 内存比对）

用途：电影库回滚后，回答"快照中还有哪些条目没恢复、为什么没对上、还能不能对上"。
原理：把 SMB 卷上每棵树（主库/暂存区/回收站/待归类）只 `os.walk` 一遍收集 NFC 归一文件集合，
之后所有缺失判定和候选来源查找都在内存完成，避免逐条 `os.path.exists()` 的网络往返超时。

2026-08-23 实测：亚洲库 4 棵树共 ~11,700 文件，扫描约 550s，随后 503 条快照判定瞬间完成。

## 使用前修改的参数

```python
BASE = '/Volumes/115open/Media/Movie/亚洲'   # 主库根
STG  = '.../_rollback_staging_亚洲'          # 暂存区
TR   = '.../_trash_<洲>_<日期>'              # 回收站
WAIT = '.../_非日本片_待归类'                # 待归类
SN   = '/tmp/az_rollback_snapshot.json'      # 冻结快照 {'files': [绝对路径,...]}
```

## 输出

- `/tmp/diff_audit_<日期>.json` — 每国 {snap, missing, cand_stg_trash, cand_in_base_other, cand_none, buckets, samples}
- 控制台 — 每国一行汇总 + recovery2 计划现状复核（目标已存在/可执行/源丢失）

## 归因分桶逻辑（对应 SKILL.md §5.5）

| 桶 | 判定 | 含义 |
|---|---|---|
| 候选:暂存/回收站有 | basename 在 STG/TR/WF 集合中命中且非通用名 | 可执行恢复 |
| 候选:库内他处同名 | basename 在主库其他位置命中 | 需人工确认是否同一文件 |
| 候选:无处可寻 | 以上全无 | 真丢失，交用户定夺 |
| （隐式）通用元数据名 | movie.nfo/poster.jpg 等黑名单名不参与候选匹配 | 需目录上下文匹配，非数据丢失 |
| 视频\|整链缺 / 父目录在 | 父祖先目录是否存在于主库 | 区分"仅文件丢"与"整个影片目录丢" |

## 关键实现要点（踩过的坑）

1. **onerror 必须存字符串**：`os.walk(onerror=lambda e: errors.append(str(e)))`。
   直接 append 异常对象会让 json.dump 抛
   `TypeError: Object of type FileNotFoundError is not JSON serializable`。
2. **NFC 归一**：所有收集到的路径先 `unicodedata.normalize('NFC', s)`，
   快照路径 join 后同样归一再比对，SMB NFD 差异不会误报为缺失。
3. **分阶段落盘**：每棵树扫完立即 dump 到 `/tmp/scan23_<name>.json`，被杀不丢已完成部分。
4. **前台运行**：Hermes 后台进程 stdout 重定向可能静默丢日志；长扫描用前台 + timeout≥600。
5. **计划复核纯内存**：recovery 计划的 src/dst 存在性用集合成员判断
   （dst in BF → 无需动；src in SF|TF|WF|BF → 可执行；都不在 → 源也没了）。

## 二次复核层：指纹级"无处可寻"验证（2026-08-23 增补）

审计报告的 `候选:无处可寻` 桶**不能直接当真丢失上报**。实测 34 条经内容指纹复核后只剩 ~3 条疑点（误报率约 90%）。

### 复核流程

对每条"无处可寻"项提取多个内容指纹 token，在全部四个位置（主库/暂存/回收站/待归类）全库搜：

```python
# token 取片名的多语言变体，避开易变 Unicode 字符（如 ô、全角假名）
tokens = [('蛇草莓','蛇イチゴ'), ('驾驶我的车','Drive.My.Car'),
          ('撩乱的裸舞曲','Gymnopedies'), ('下女1960','Hanyo.1960')]
for label, tok in tokens:
    hits = {loc: [x for x in S if tok.lower() in x.lower()]
            for loc, S in [('主库',BF),('暂存',SF),('回收站',TF),('待归类',WF)]}
```

### 判定规则

| 指纹命中位置 | 结论 |
|---|---|
| 暂存区其他目录 | 目录重排导致 basename 匹配失效 → **可恢复**，补精确映射 |
| 主库其他位置 | 已归位/版本互替 → 非丢失，属结构决策 |
| 仅 `._` 开头条目 | AppleDouble 元数据残骸，**不算本体存在**；过滤规则：`basename.startswith('._')` |
| 四位置全空 | 才进入"真疑点"清单，交用户定夺并询问是否有网盘 App 端副本 |

### 快照合理性校验（防失真基准）

115 等虚拟挂载的挂载视图与网盘 App 视图会分叉（缓存延迟 + 移动降级上传到根目录），
在失真视图上抓的快照本身有空洞。快照落盘后抽查：

```python
# 抽查已知存在的知名导演目录，若快照中该目录下条目为 0 → 快照已失真，当场向用户提出
for d in ['滨口龙介', '是枝裕和', '洪尚秀']:
    n = sum(1 for p in SN['files'] if f'/{d}' in p or d.split()[0] in p)
    print(d, '快照条目:', n)   # 0 = 红旗
```

实测教训：滨口龙介整导演目录在快照中为 0 条，影片实际在搬运途中被降级上传到了网盘根目录——
直到用户自己在 App 里发现，才定位根因。

## 完整脚本骨架

```python
import os, json, unicodedata, collections, time

def nfc(s): return unicodedata.normalize('NFC', s)

def walk(root):
    files, dirs, errors = set(), set(), []
    def onerr(name): errors.append(str(name))     # 必须 str()！
    for dp, dn, fn in os.walk(root, onerror=onerr):
        dirs.add(nfc(dp))
        for f in fn:
            files.add(nfc(os.path.join(dp, f)))
    return files, dirs, errors

STORE = {}
for name, root in [('stg', STG), ('tr', TR), ('wait', WAIT), ('base', BASE)]:
    f, d, e = walk(root)
    STORE[name] = sorted(f)
    json.dump(STORE[name], open(f'/tmp/scan23_{name}.json', 'w'), ensure_ascii=False)

BF, SF, TF, WF = (set(STORE[k]) for k in ('base', 'stg', 'tr', 'wait'))
BD = set()  # 如需父链判断，walk 时同时收 dirs

GENERIC = {'movie.nfo','landscape.jpg','poster.jpg','fanart.jpg','backdrop.jpg',
           'logo.png','folder.jpg','clearlogo.png','formal.jpg'}

report = {}
for c in countries:                       # 国家列表按库结构定义
    targets = [p[len(BASE)+1:] for p in SN['files'] if f'/亚洲/{c}/' in p]
    missing = [rel for rel in targets if nfc(os.path.join(BASE, rel)) not in BF]
    cnt = collections.Counter(); samples = collections.defaultdict(list)
    for rel in missing:
        b = os.path.basename(rel)
        generic = b.lower() in GENERIC or os.path.splitext(b)[1].lower() in ('.nfo','.jpg','.png')
        if not generic:
            hits = ([x for x in SF if x.endswith('/'+b)]
                    + [x for x in TF if x.endswith('/'+b)]
                    + [x for x in WF if x.endswith('/'+b)])
            if hits:
                cnt['候选:暂存/回收站有'] += 1
            elif [x for x in BF if x.endswith('/'+b)]:
                cnt['候选:库内他处同名'] += 1
            else:
                cnt['候选:无处可寻'] += 1
        # 父链状态、视频/元数据分类同理在内存完成
    report[c] = {'snap': len(targets), 'missing': len(missing),
                 'buckets': dict(cnt), 'samples': dict(samples)}

json.dump(report, open('/tmp/diff_audit_20260823.json', 'w'), ensure_ascii=False, indent=1)
```
