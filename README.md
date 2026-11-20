# UniSchedule 大学生课表工具

Windows 桌面课表横条：置顶显示当天课程，按大学周次排课，支持假期、文字课表、ICS 导入与多套课表来源切换。

## 功能

- **顶部横条**：`第X周 · 日期 · 周几` + 13 节课逐节显示；科目配色、连堂合并、空节灰横杠、圆角卡片。
- **置顶与穿透**：始终置顶（其他窗口抢置顶后 1 秒内自动恢复），鼠标穿透，悬停自动变淡。
- **课表管理**：科目 / 课表增删改、冲突检测、按 `科目 + 星期 + 节次` 精确删除。
- **ICS 导入**：BitUp、BIT101 等导出的 `.ics` 直接导入；导入后可逐门编辑横条简称。
- **多课表来源**：手动课表与多个 ICS 课表各自独立保存，随时切换，互不覆盖。
- **假期**：手动添加 / 删除假期段；整天没课的日子自动显示「今日假期」。
- **学期周次**：可把第 1 周重定义到另一个周一，之前的周显示为 `第-1周`、`第-2周`……
- **文字课表**：`[7]` 按课程输出自然语言描述（自动合并周次 / 星期 / 节次）。
- **托盘与自启**：单个托盘图标；终端最小化后自动隐藏；`autostart.bat` 适合开机自启。

## 快速开始

1. 安装 **64 位 Python 3.10+**（安装时勾选 *Add Python to PATH*）。确认位数：

   ```powershell
   python -c "import platform,sys;print(sys.version);print(platform.architecture()[0])"
   ```

   最后一行应为 `64bit`。
2. 在本目录打开终端，安装依赖：

   ```powershell
   pip install -r requirements.txt
   ```

3. 双击 **`launcher.bat`**。
4. 首次使用会先选课表来源：
   - `i` 从 ICS 导入：把 `.ics` 放进 **`课表ics/`**，按提示选择文件；
   - `m` 手动创建：先设置开学日期与总周数，再录入科目和课表。
5. 选 `[3] 启动课表显示`，横条会出现在屏幕顶部；平时可通过托盘图标控制。

## 菜单一览

| 菜单 | 功能 |
|------|------|
| `[0]` | 初始化（开学日期 + 总周数） |
| `[1]` | 管理课程（科目全名 / 简称 / 颜色） |
| `[2]` | 管理课表（录入、冲突检测、删除整条、精确删除） |
| `[3]` | 启动课表显示（可输入模拟日期） |
| `[4]` | 清除所有数据（所有课表来源 + 假期） |
| `[5]` | 显示设置（非假期 / 假期 × 正常 / 悬停 四档不透明度） |
| `[6]` | 假期管理（添加 / 删除 / 查看） |
| `[7]` | 查看课表（文字说明） |
| `[8]` | 课表来源（ICS 导入 / 切换 / 查看 / 删除） |
| `[9]` | 重定义第 1 周（整体平移课表） |
| `q` | 退出 |

## 课表来源与 ICS 导入

`[8] 课表来源` 提供：

- `i` 导入 / 重新导入 ICS：列出 `课表ics/` 下的文件，显示解析摘要，可先把第 1 周重定义到某个周一，确认后导入。
- `s` 切换来源：手动课表与各个 ICS 课表之间切换。
- `l` 查看来源：原始文件、导入时间、学期设置。
- `d` 删除 ICS 来源：只删导入的数据，原始 `.ics` 不动。

导入完成后会**逐门询问横条简称**（回车保持自动生成的 2–4 字简称，输入则覆盖）。

每个来源独立保存：手动课表在 `data/`，ICS 课表在 `data/ics/<id>/`，各自带学期配置；切换来源不会影响其它来源。

## 节次时间表

ICS 里的时间通过根目录 **`period_times.json`** 换算成节次。默认是北京理工大学 13 节时间表；换学校时修改这个文件后重新导入即可。

## 学期与周次

- 当前周 = `(今天 − 开学日) // 7 + 1`。
- 开学前的周不显示第 0 周：紧邻第 1 周之前显示 `第-1周`，更早依次为 `第-2周`、`第-3周`……
- `[9] 重定义第 1 周` 只接受**周一**（非周一直接拒绝），会把当前来源的课表周次整体平移，并更新学期配置。
- 导入 ICS 时也会询问是否重定义第 1 周。

## 课表横条与托盘

- 横条贴在屏幕顶部、始终置顶、鼠标穿透；鼠标移到上面会按 `[5]` 的设置变淡。
- 放假（手动假期或当天整天没课）时不显示 13 节，显示绿色「今日假期」。
- 托盘图标右键：显示 / 隐藏主窗口、启动 / 关闭课表横条、退出 UniSchedule。终端最小化约 0.2 秒后自动隐藏。
- 开机自启：`Win + R` 输入 `shell:startup`，把 `autostart.bat` 的快捷方式放进打开的文件夹。

## 依赖

- **Python 3.10+**（其余全部使用 Python 标准库）
- 第三方包（见 `requirements.txt`）：

  ```text
  PySide6>=6.5,<7
  pystray>=0.19
  Pillow>=9
  ```

| 包 | 用途 | 安装后占用 |
|----|------|-----------|
| **PySide6**（含 shiboken6） | 课表横条界面 | **≈ 635 MB** |
| **Pillow** | 托盘图标 / 图片处理 | **≈ 15 MB** |
| **pystray** | 系统托盘图标 | **< 1 MB** |

> **体积提示**：PySide6 占绝大部分，`pip install -r requirements.txt` 首次需要下载数百 MB，请预留约 **700 MB** 磁盘空间。测试版本：PySide6 6.11.2、pystray 0.19.5、Pillow 12.2.0。

### 安装报 `from versions: none`

这表示 pip 在当前 Python 上找不到可用的 PySide6 轮子，常见原因：

- Python 是 **32 位**（PySide6 只提供 64 位 Windows 轮子 `win_amd64`）；
- Python 版本过旧：PySide6 6.9 / 6.10 要求 **≥3.9**，6.11+ 要求 **≥3.10**；
- **Python 3.14**：PySide6 6.9 / 6.10 声明 `Requires-Python <3.14`，需要 **6.11+**（本项目会自动选最新，目前镜像上是 6.12.x）；镜像节点没同步到 6.11/6.12 时也会显示 `none`；
- 镜像同步异常。

排查与处理：

```powershell
python --version
python -c "import sys,platform;print(sys.executable);print(platform.architecture()[0])"
py -0p
```

装好 64 位 Python 3.10+ 后，用明确指定的解释器安装（避免 PATH 指到旧版本）：

```powershell
py -3.10 -m pip install -r requirements.txt
```

镜像缓存/节点未更新时，先加 `--no-cache-dir` 重试，再换官方源：

```powershell
py -3.14 -m pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
py -3.14 -m pip install -r requirements.txt -i https://pypi.org/simple
```

验证镜像是否能给 Python 3.14 找到 PySide6（应下载 6.11.x / 6.12.x）：

```powershell
py -3.14 -m pip download --no-deps --only-binary=:all: --python-version 3.14 PySide6 -d "$env:TEMP\pyside-test"
```

## 数据与隐私

- 个人课表保存在 `data/`，ICS 文件放在 `课表ics/`；两者都在 `.gitignore` 中，不会被提交。
- `outputs/`、`*.bak*`、`__pycache__/` 同样不会进入仓库。
- 备份：升级或修改数据前可自行复制 `data/` 目录。

## 目录结构

```text
UniSchedule/
├── launcher.bat / autostart.bat   启动（含经典 conhost 单窗口）
├── launcher.py                   终端菜单循环
├── display.py                    课表横条（PySide6）
├── tray_win.py                   托盘图标与终端隐藏
├── storage.py / sources.py       数据层与课表来源
├── period_times.json              节次 ↔ 时间对照表
├── ics_import.py                  ICS 解析与导入
├── manage_*.py                   课程 / 课表 / 假期 / 来源菜单
├── holidays.py / timetable.py    假期判定 / 文字课表
├── requirements.txt              Python 依赖
└── data/                         个人数据（不进入 Git）
```

