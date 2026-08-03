---
name: android-termux-development
description: Android Termux 环境下的软件安装、Python 包兼容性、进程管理和 APK 安装模式。适用于在 Termux 中编译/安装任何 Python 项目或原生应用。
license: MIT
metadata:
  version: "1.0.0"
  author: lynch5mo
  category: devops
---

# Android Termux 开发环境

适用于：在 Termux 中安装、编译、运行软件（Python 项目、原生应用等）

## 核心认知

Termux ≠ 标准 Linux。Android 内核和 Bionic libc 导致：
- C/Rust 扩展包（psutil、jiter、numpy 等）无法直接编译
- 进程信号处理不同（Ctrl+C 行为不一致）
- Python 版本和路径与标准发行版不同
- 包管理器是 `pkg`（基于 apt），不是 pip/conda

## Python 包安装模式

### 问题：C/Rust 扩展无法编译
典型错误：
```
platform android is not supported
error: command 'gcc' failed
```

### 解决方案：分层安装
```bash
# 1. 用 pkg 装 Termux 预编译的系统包
pkg install python-numpy python-psutil python-pillow

# 2. 创建 venv
python -m venv venv
source venv/bin/activate

# 3. 从 pyproject.toml 中删除不兼容的 C 扩展依赖
sed -i '/psutil==7.2.2/d' pyproject.toml   # 直接删除行，不要注释

# 4. 安装项目（不含 C 扩展）
pip install . --no-deps

# 5. 手动安装纯 Python 依赖
pip install pyyaml requests jinja2 pydantic prompt_toolkit tenacity "httpx[socks]" rich

# 6. 复制 Termux 预编译包到 venv
PYTHON_VER=$(python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
cp -r $PREFIX/lib/python${PYTHON_VER}/site-packages/psutil* venv/lib/python${PYTHON_VER}/site-packages/
```

### 已知不兼容包
| 包 | 问题 | 解决方案 |
|---|---|---|
| psutil | `platform android is not supported` | `pkg install python-psutil` + 复制到 venv |
| jiter | Rust 编译卡死 | `pip install jiter --only-binary=:all:` 或跳过 |
| numpy | 编译慢/失败 | `pkg install python-numpy` |
| Pillow | 编译需要 libjpeg 等 | `pkg install python-pillow libjpeg-turbo` |

## Termux 进程管理

### Ctrl+C 不工作
Termux 中 Ctrl+C 经常无响应，尤其是编译/安装进程。

**中断方法（按优先级）：**
1. **下拉通知栏** → Termux 前台服务 → 点「STOP」
2. **新开会话** → 从左边缘右滑 → 「NEW SESSION」→ `pkill -f <进程名>`
3. **强制关闭 Termux** → Home 键 → 重新打开（进程自动终止）

## GitHub APK 安装

当源码编译太复杂时，优先检查是否有预编译 APK：

```bash
# 查看最新 release 的 assets
curl -s https://api.github.com/repos/<owner>/<repo>/releases/latest | \
  python3 -c "import sys,json; d=json.load(sys.stdin); [print(a['browser_download_url']) for a in d.get('assets',[])]"

# 下载 APK
curl -LO <apk_url>

# 安装（需要存储权限）
termux-setup-storage  # 首次需要
cp *.apk ~/storage/downloads/
# 然后用文件管理器点击安装
```

## pyproject.toml 编辑注意事项

### 注释格式
pyproject.toml 的 `project.dependencies` 要求 PEP 508 格式，**不能用 `#` 注释依赖行**：
```toml
# ❌ 错误 — 会报 "must be pep508" 解析错误
# psutil==7.2.2

# ✅ 正确 — 直接删除整行
# (用 sed -i '/psutil==7.2.2/d' pyproject.toml)
```

## 常见坑

1. **Python 版本路径**：Termux 可能是 3.12 或 3.13，不要硬编码版本号。用 `python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"` 获取
2. **pip install -e . 失败**：editable 模式在 Termux 上兼容性差，用 `pip install .`（非 editable）
3. **SSL 重试警告**：`SSL: UNEXPECTED_EOF_WHILE_READING` 通常是网络波动，pip 会自动重试
4. **git clone URL 不完整**：确保 URL 包含完整的 `<owner>/<repo>` 路径
5. **Android Gradle 项目不是 Python 项目**：看到 `build.gradle.kts` 说明是 Android 项目，不能用 pip 安装
6. **termux-open 不可用**：需要安装 `pkg install termux-tools` 或用 `am start` 替代
7. **am start 安装 APK 无反应**：Termux 私有存储对 Android 包安装器不可见，需先 `cp` 到 `~/storage/downloads/` 再用文件管理器安装
