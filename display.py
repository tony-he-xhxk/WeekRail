# -*- coding: utf-8 -*-
"""3. 前端课表横条（PySide6）。

显示：第X周 · X月X日 周X | 1-5节 | 6-10节 | 11-13节（没课的节次显示浅灰"—"）
样式：圆角卡片 + 柔光描边 + 投影；每门课一个颜色（palette.py 分配），
      相邻同科目节次连成一条，一眼看出连堂；
      平时不透明度 / 鼠标悬停（穿透）不透明度可在终端菜单 [5] 里调。

用法：python display.py [--date YYYY-MM-DD] [--render out.png [--render-width 1880]]
      --date   模拟日期（调试用）
      --render 把横条离屏渲染成 PNG 后退出（预览/调试用，不弹窗）
退出：系统托盘图标右键 -> 退出
"""
import argparse
import ctypes
import os
import sys
from ctypes import wintypes
from datetime import date
from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QWidget

import holidays
import palette
import storage

BASE = Path(__file__).resolve().parent
ICON_PATH = BASE / "icon.ico"

# 默认不透明度（1.0 = 100%）；实际值来自 data/prefs.json，菜单 [5] 可调
DEFAULT_OPACITY_NORMAL = 1.0
DEFAULT_OPACITY_HOVER = 0.1
DEFAULT_HOLIDAY_NORMAL = 0.7   # 假期版默认更淡：别让「今日假期」这条挡住后面的内容
DEFAULT_HOLIDAY_HOVER = 0.1    # 假期版悬停（穿透）时

CARD_H = 52              # 卡片高度
CARD_RADIUS = 14         # 圆角半径
SHADOW = 10              # 投影预留的透明边距
PAD_X = 18               # 卡片内左右留白
PAD_Y = 6                # 卡片内上下留白
INFO_W = 230             # 左侧"第X周 日期 周几"区域宽度
SEGMENTS = ((1, 5), (6, 10), (11, 13))

EMPTY_COLOR = palette.EMPTY_COLOR   # 空节横杠的灰（对白底 3.7:1，明显可见）
SEP_COLOR = "#9AA3AE"               # 两条分段竖线（比横杠略淡，但足够看清）
HOLIDAY_BG = "#E7F6EC"              # 「今日假期」徽章：绿底 / 绿边 / 绿字
HOLIDAY_BORDER = "#4CAF50"
HOLIDAY_TEXT = "#1B7F3B"
FONT_QSS = "font-family:'Microsoft YaHei UI','Microsoft YaHei','Segoe UI',sans-serif;"

# 置顶自检：有些应用（如 ChatGPT 桌面版）会把自己的窗口抢到最前，连带把横条的
# WS_EX_TOPMOST 清掉，横条就"退化"到被普通窗口盖住。这里定时检查并补回来。
GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SW_SHOWNOACTIVATE = 4
TOPMOST_CHECK_MS = 1000        # 每 1 秒自检一次：标志位丢了 / 被别的窗口盖住都会补
SYNCHRONIZE = 0x00100000
GW_HWNDPREV = 3                # z 序里"在本窗口之上"的那个窗口

# 外壳窗口（桌面 / 任务栏 / 开始菜单 / 任务视图）不抢：它们本来就该盖在最上面
SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
                 "XamlExplorerHostIslandWindow", "MultitaskingViewFrame",
                 "ForegroundStaging", "TaskListThumbnailWnd", "Windows.Internal.Shell.TabProxyWindow"}


class _RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

# 状态指纹：不"睡到墙钟时刻"，而是周期性比对绝对状态，这样休眠唤醒 / 时钟跳变 /
# 手动改时间都会在下一个心跳自动纠正。日期每拍比（≈0.1 微秒），数据文件 mtime
# 每 STATE_CHECK_TICKS 拍比一次（4 个 stat ≈ 30 微秒）。
STATE_CHECK_TICKS = 15
DATA_FILES = ("config.json", "subjects.json", "lessons.json", "prefs.json", "holidays.json")
_DEBUG = os.environ.get("UNISCHEDULE_DEBUG") == "1"

try:
    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32
    _user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    _user32.SetWindowPos.restype = wintypes.BOOL
    _user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.GetWindowLongW.restype = ctypes.c_long
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.IsIconic.argtypes = [wintypes.HWND]
    _user32.IsIconic.restype = wintypes.BOOL
    _user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.ShowWindow.restype = wintypes.BOOL
    _user32.GetWindow.argtypes = [wintypes.HWND, ctypes.c_uint]
    _user32.GetWindow.restype = wintypes.HWND
    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(_RECT)]
    _user32.GetWindowRect.restype = wintypes.BOOL
    _user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.GetCurrentProcessId.restype = wintypes.DWORD
    _kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _kernel32.WaitForSingleObject.restype = wintypes.DWORD
except Exception:                                  # 非 Windows 或 API 不可用时降级
    _user32 = None
    _kernel32 = None

_parent_handle = None    # launcher 进程的等待句柄（看门狗用）


def _open_parent_watch():
    """打开 launcher 进程的等待句柄。

    用 PID 而不是继承句柄：Python 的 subprocess 默认 close_fds=True，不会把我们
    DuplicateHandle 出来的句柄交给子进程，所以老写法里看门狗其实拿不到有效句柄。
    """
    global _parent_handle
    if _kernel32 is None:
        return False
    raw = os.environ.get("UNISCHEDULE_PARENT_PID")
    if not raw:
        return False
    try:
        pid = int(raw)
    except ValueError:
        return False
    handle = _kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if not handle:
        return False
    _parent_handle = handle
    return True


def _pct(prefs, key, default):
    """把 prefs 里的百分比读成 0.0-1.0；非法值用默认值。"""
    try:
        return max(0, min(100, int(prefs.get(key, default)))) / 100.0
    except (TypeError, ValueError):
        return default / 100.0


def _log(message):
    """调试输出：设环境变量 UNISCHEDULE_DEBUG=1 时打印到 stdout。"""
    if _DEBUG:
        print(message, flush=True)


def _now_date():
    """当前系统日期（单独抽一层，测试时可以替换）。"""
    return date.today()


def _data_stamp():
    """数据文件指纹（mtime 纳秒）：用来发现课表 / 科目 / 配置被改动过。"""
    stamp = []
    for name in DATA_FILES:
        try:
            stamp.append(os.stat(storage.DATA_DIR / name).st_mtime_ns)
        except OSError:
            stamp.append(0)
    return tuple(stamp)


def compute_view(today):
    """算这一天要显示的内容，返回 (week, weekday, period_map, holiday)。

    week 为 None 表示未开学 / 已结课（横条只显示日期）；配置缺失返回 None。
    holiday=True 表示今天放假（手动假期，或学期内整天没课）：不显示 13 节课，
    改显示绿色「今日假期」。
    """
    cfg = storage.load_config()
    if not cfg:
        return None
    start = date.fromisoformat(cfg["start_date"])
    week = storage.current_week(start, today)
    weekday = today.isoweekday()
    lessons = storage.load_lessons()
    data_weeks = [w for lesson in lessons for w in lesson.get("weeks", [])]
    low = min(data_weeks) if data_weeks else 1
    if week < low or week > int(cfg["total_weeks"]):
        return None, weekday, {}, False
    if holidays.is_day_off(today, cfg):
        return week, weekday, {}, True
    subjects = storage.ensure_subject_colors()
    subs = {s["id"]: s for s in subjects}
    period_map = build_period_map(lessons, subs, week, weekday)
    return week, weekday, period_map, False


def build_period_map(lessons, subs, week, weekday):
    """period -> (科目简称, 配色)；同一节被多门课占用时保留先出现的那门。"""
    result = {}
    for lesson in lessons:
        if weekday in lesson["weekdays"] and week in lesson["weeks"]:
            sub = subs.get(lesson["subject_id"], {})
            style = palette.chip_style(palette.color_of(sub))
            name = sub.get("short_name", "?")
            for period in lesson["periods"]:
                result.setdefault(period, (name, style))
    return result


class Bar(QWidget):
    """顶部横条：圆角卡片 + 13 节 + 两条分段线。"""

    def __init__(self, week, weekday, period_map, today,
                 opacity_normal=DEFAULT_OPACITY_NORMAL, opacity_hover=DEFAULT_OPACITY_HOVER,
                 simulated=False, holiday=False,
                 holiday_normal=None, holiday_hover=None):
        super().__init__()
        self._hover = False
        # 两套不透明度：非假期 / 假期，各含"正常"和"鼠标悬停（穿透）"两档
        self._opacity = {"normal": opacity_normal, "hover": opacity_hover}
        self._holiday_opacity = {
            "normal": opacity_normal if holiday_normal is None else holiday_normal,
            "hover": opacity_hover if holiday_hover is None else holiday_hover,
        }
        self._today = today
        self._simulated = simulated          # --date 模拟模式：日期不自动前进
        self._holiday = holiday              # 今天放假：不显示 13 节，显示「今日假期」
        self._date_ord = today.toordinal()
        self._data_stamp = _data_stamp()
        self._tick_count = 0
        self.setWindowTitle("UniSchedule")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._apply_opacity()
        self.setStyleSheet(FONT_QSS)

        self._root = QHBoxLayout(self)
        self._root.setContentsMargins(SHADOW + PAD_X, SHADOW + PAD_Y, SHADOW + PAD_X, SHADOW + PAD_Y)
        self._root.setSpacing(0)
        self._set_content(week, weekday, period_map, today, holiday)

        # 鼠标穿透 + 悬停降不透明度（穿透态收不到 enter/leave，只能轮询全局鼠标）
        self.setWindowFlag(Qt.WindowTransparentForInput, True)
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._check_hover)
        self._timer.start()

        # 心跳：补置顶 + 比对状态指纹（跨零点、改完课表都会自动刷新）
        self.topmost_fixes = 0
        self.show_fixes = 0
        self._top_timer = QTimer(self)
        self._top_timer.setInterval(TOPMOST_CHECK_MS)
        self._top_timer.timeout.connect(self._tick)
        self._top_timer.start()

        # 看门狗：launcher 若单独消失就自动退出，避免终端没了横条留在屏幕上
        if _parent_handle:
            self._wd_timer = QTimer(self)
            self._wd_timer.setInterval(1000)
            self._wd_timer.timeout.connect(self._watchdog)
            self._wd_timer.start()

    # ---------------------------------------------------------------- 子控件
    def _info(self, week, today, weekday):
        box = QWidget(self)
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        if week is not None:
            label = storage.week_label(week)
            pill = QLabel(("第 %d 周" % label) if label >= 1 else ("第%d周" % label))
            pill.setStyleSheet("background-color:#2F6FEB; color:#FFFFFF; border-radius:11px;"
                               "padding:3px 10px; font-size:14px; font-weight:600;")
            lay.addWidget(pill)
        label = QLabel("%d月%d日" % (today.month, today.day))
        label.setStyleSheet("color:#111827; font-size:17px; font-weight:600;")
        lay.addWidget(label)
        wd = QLabel(storage.WEEKDAY_CN[weekday])
        wd.setStyleSheet("color:#6B7280; font-size:14px; font-weight:500;")
        lay.addWidget(wd)
        lay.addStretch(1)
        box.setFixedWidth(INFO_W)
        return box

    def _separator(self):
        sep = QLabel("")
        sep.setStyleSheet("background-color:%s; min-width:2px; max-width:2px; margin:9px 10px;"
                          % SEP_COLOR)
        return sep

    def _slot(self, name, style, prev_name, next_name):
        """一节：有课=圆角色块（连堂自动相连），没课=浅灰横杠。"""
        if not name:
            empty = QLabel("—")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("color:%s; font-size:17px; font-weight:600; margin:7px 4px;"
                                % EMPTY_COLOR)
            return empty
        join_left = prev_name == name
        join_right = next_name == name
        radius_l = 3 if join_left else 9
        radius_r = 3 if join_right else 9
        left = "none" if join_left else "2px solid %s" % style["border"]
        right = "none" if join_right else "2px solid %s" % style["border"]
        margin = "7px %s %s %s" % (
            "0px" if join_right else "4px", "7px", "0px" if join_left else "4px")
        chip = QLabel(name)
        chip.setAlignment(Qt.AlignCenter)
        chip.setStyleSheet(
            "background-color:%s; color:%s; font-size:17px; font-weight:600;"
            "border-top:2px solid %s; border-bottom:2px solid %s;"
            "border-left:%s; border-right:%s;"
            "border-top-left-radius:%dpx; border-bottom-left-radius:%dpx;"
            "border-top-right-radius:%dpx; border-bottom-right-radius:%dpx;"
            "margin:%s;" % (style["bg"], style["text"], style["border"], style["border"],
                            left, right, radius_l, radius_l, radius_r, radius_r, margin))
        return chip

    # ------------------------------------------------------- 内容刷新（状态指纹）
    def _set_content(self, week, weekday, period_map, today, holiday=False):
        """按给定状态重建条内容：原地换子控件，不重建窗口（不闪、不丢置顶）。"""
        while self._root.count():
            item = self._root.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._root.addWidget(self._info(week, today, weekday))
        if holiday:
            self._root.addStretch(1)
            badge = QLabel("今日假期")
            badge.setAlignment(Qt.AlignCenter)
            badge.setStyleSheet(
                "background-color:%s; color:%s; border:1px solid %s; border-radius:9px;"
                "font-size:18px; font-weight:600; padding:0 26px; margin:7px 4px;"
                % (HOLIDAY_BG, HOLIDAY_TEXT, HOLIDAY_BORDER))
            self._root.addWidget(badge)
            self._root.addStretch(1)
            return
        for index, (first, last) in enumerate(SEGMENTS):
            if index:
                self._root.addWidget(self._separator())
            for period in range(first, last + 1):
                name, style = period_map.get(period, (None, None))
                prev_name = period_map.get(period - 1, (None, None))[0]
                next_name = period_map.get(period + 1, (None, None))[0]
                self._root.addWidget(self._slot(name, style, prev_name, next_name), 1)

    def reload(self):
        """按"当前日期 + 当前数据"重算并刷新，顺带应用最新的不透明度设置。"""
        today = self._today if self._simulated else _now_date()
        view = compute_view(today)
        if view is None:
            return
        week, weekday, period_map, holiday = view
        self._today = today
        self._date_ord = today.toordinal()
        self._data_stamp = _data_stamp()
        self._holiday = holiday
        self._load_opacity()
        self._set_content(week, weekday, period_map, today, holiday)
        self.place()

    def _load_opacity(self):
        """从 prefs 读四档不透明度，并按「当前是否假期 + 是否悬停」立刻应用。"""
        prefs = storage.load_prefs()
        self._opacity = {"normal": _pct(prefs, "opacity_normal", 100),
                         "hover": _pct(prefs, "opacity_hover", 10)}
        self._holiday_opacity = {"normal": _pct(prefs, "holiday_normal", 70),
                                 "hover": _pct(prefs, "holiday_hover", 10)}
        self._apply_opacity()

    def _apply_opacity(self):
        """按当前假期状态 + 悬停状态选一套不透明度（假期属性会随日期/课表变化）。"""
        pair = self._holiday_opacity if self._holiday else self._opacity
        self.setWindowOpacity(pair["hover"] if self._hover else pair["normal"])

    def _tick(self):
        """心跳（每 2 秒）：先补置顶，再比对状态指纹。"""
        self._keep_on_top()
        self._check_state()

    def _check_state(self):
        """日期每拍比，数据文件 mtime 每 STATE_CHECK_TICKS 拍比；有变化就整条刷新。"""
        reasons = []
        if not self._simulated:
            today = _now_date()
            if today.toordinal() != self._date_ord:
                reasons.append("日期变为 %s" % today.isoformat())
        self._tick_count += 1
        if reasons or self._tick_count % STATE_CHECK_TICKS == 0:
            stamp = _data_stamp()
            if stamp != self._data_stamp:
                reasons.append("课表/科目/配置有改动")
        if reasons:
            _log("[STATE] %s -> 重载横条" % "，".join(reasons))
            self.reload()

    # ---------------------------------------------------------------- 绘制
    def _card_rect(self):
        return QRectF(self.rect()).adjusted(SHADOW, SHADOW, -SHADOW, -SHADOW)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        card = self._card_rect()
        # 1) 投影：多层圆角矩形，越靠外越淡
        painter.setPen(Qt.NoPen)
        for i in range(SHADOW, 0, -1):
            t = 1.0 - (i - 1) / float(SHADOW)
            painter.setBrush(QColor(15, 23, 42, int(3 + 9 * t * t)))
            painter.drawRoundedRect(card.adjusted(-i, -i + 2, i, i + 2),
                                    CARD_RADIUS + i, CARD_RADIUS + i)
        # 2) 卡片底色（白色玻璃感）
        grad = QLinearGradient(card.topLeft(), card.bottomLeft())
        grad.setColorAt(0.0, QColor(255, 255, 255, 242))
        grad.setColorAt(1.0, QColor(255, 255, 255, 228))
        painter.setBrush(grad)
        painter.setPen(QPen(QColor(15, 23, 42, 24), 1))
        painter.drawRoundedRect(card.adjusted(0.5, 0.5, -0.5, -0.5), CARD_RADIUS, CARD_RADIUS)
        # 3) 顶部内高光
        painter.setPen(QPen(QColor(255, 255, 255, 210), 1))
        y = card.top() + 1.5
        painter.drawLine(QRectF(card.left() + CARD_RADIUS, y,
                                card.width() - 2 * CARD_RADIUS, 0).topLeft(),
                         QRectF(card.left() + CARD_RADIUS, y,
                                card.width() - 2 * CARD_RADIUS, 0).topRight())

    # ---------------------------------------------------------------- 行为
    def _check_hover(self):
        hit = self._card_rect().contains(self.mapFromGlobal(QCursor.pos()))
        if hit != self._hover:
            self._hover = hit
            self._apply_opacity()

    def _keep_on_top(self):
        """把被抢走的置顶位补回来；顺带救回被系统隐藏的横条。不动位置/大小/焦点。

        注意：只检查 WS_EX_TOPMOST 是不够的——别的窗口（例如最大化 / 全屏的 Chrome）
        会把横条压到下面，却不一定会清掉那个标志位。所以还要看 z 序里有没有窗口盖住横条。
        """
        if _user32 is None:
            return
        try:
            hwnd = wintypes.HWND(int(self.winId()))
            if not _user32.IsWindowVisible(hwnd):
                _user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
                self.show_fixes += 1
            missing = not (_user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOPMOST)
            cover = "" if missing else self._covered_by()
            if missing or cover:
                _user32.SetWindowPos(hwnd, wintypes.HWND(HWND_TOPMOST), 0, 0, 0, 0,
                                     SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
                self.topmost_fixes += 1
                if cover:
                    _log("[TOP] 被 %s 盖住 -> 重新置顶（第 %d 次）"
                         % (cover, self.topmost_fixes))
        except Exception:
            pass

    def _covered_by(self):
        """z 序里是否有别的窗口盖在横条上；有就返回它的窗口类名（用于日志）。"""
        try:
            mine = wintypes.HWND(int(self.winId()))
            rect = _RECT()
            if not _user32.GetWindowRect(mine, ctypes.byref(rect)):
                return ""
            my_pid = _kernel32.GetCurrentProcessId()
            hwnd = _user32.GetWindow(mine, GW_HWNDPREV)      # 从"我们上面"往上一层层走
            while hwnd:
                cls = self._covering_class(hwnd, rect, my_pid)
                if cls:
                    return cls
                hwnd = _user32.GetWindow(hwnd, GW_HWNDPREV)
        except Exception:
            pass
        return ""

    @staticmethod
    def _covering_class(hwnd, rect, my_pid):
        """给定窗口是否可见、属于别的进程、且与横条矩形相交（跳过外壳窗口）。"""
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == my_pid:
            return ""                                    # 自己进程的辅助窗口（IME、Qt 内部窗口）
        buf = ctypes.create_unicode_buffer(128)
        _user32.GetClassNameW(hwnd, buf, 128)
        if buf.value in SHELL_CLASSES:
            return ""
        if not _user32.IsWindowVisible(hwnd) or _user32.IsIconic(hwnd):
            return ""
        other = _RECT()
        if not _user32.GetWindowRect(hwnd, ctypes.byref(other)):
            return ""
        if (other.left < rect.right and rect.left < other.right
                and other.top < rect.bottom and rect.top < other.bottom):
            return buf.value
        return ""

    def _watchdog(self):
        """launcher 消失（被单独结束或崩溃）时自动退出。"""
        if _parent_handle is None or _kernel32 is None:
            return
        try:
            if _kernel32.WaitForSingleObject(_parent_handle, 0) == 0:
                QApplication.quit()
        except Exception:
            pass

    def place(self, width=None):
        geo = self.screen().availableGeometry()
        self.resize(width or (geo.width() - 40), CARD_H + 2 * SHADOW)
        self.move(geo.x() + 20, max(geo.y(), geo.y() + 12 - SHADOW))


def make_bar(today, prefs=None, simulated=False):
    """按当前数据生成横条（配置缺失时返回 None）。"""
    view = compute_view(today)
    if view is None:
        return None
    week, weekday, period_map, holiday = view
    prefs = prefs or storage.load_prefs()
    return Bar(week, weekday, period_map, today,
               _pct(prefs, "opacity_normal", 100), _pct(prefs, "opacity_hover", 10),
               simulated, holiday,
               holiday_normal=_pct(prefs, "holiday_normal", 70),
               holiday_hover=_pct(prefs, "holiday_hover", 10))


def _load_preview_font():
    """离屏渲染（--render）时 Qt 默认字体没有中文字形，显式挂载系统里的中文字体。"""
    from PySide6.QtGui import QFontDatabase
    for path in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc"):
        families = QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(path))
        if families:
            return families[0]
    return None


def main():
    parser = argparse.ArgumentParser(description="UniSchedule 课表横条")
    parser.add_argument("--date", help="模拟日期 YYYY-MM-DD（调试用）")
    parser.add_argument("--render", help="渲染成 PNG 后退出（预览/调试用）")
    parser.add_argument("--render-width", type=int, default=1880, help="--render 时的横条宽度")
    args = parser.parse_args()

    cfg = storage.load_config()
    if not cfg:
        print("[ERR] 未初始化：请先在启动器里执行 [0] 初始化")
        return 1
    try:
        today = date.fromisoformat(args.date) if args.date else _now_date()
    except ValueError:
        print("[WARN] 日期格式无效，改用今天")
        today = _now_date()

    if args.render:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    if args.render:
        _load_preview_font()

    _open_parent_watch()

    bar = make_bar(today, simulated=bool(args.date))
    if bar is None:
        print("[ERR] 未初始化：请先在启动器里执行 [0] 初始化")
        return 1
    if args.render:
        bar.place(width=args.render_width)
        bar.show()
        app.processEvents()
        pixmap = bar.grab()
        pixmap.save(args.render)
        print("[OK] 已渲染 %dx%d -> %s" % (pixmap.width(), pixmap.height(), args.render))
        return 0
    bar.place()
    bar.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
