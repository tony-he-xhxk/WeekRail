# -*- coding: utf-8 -*-
"""WeekRail 统一托盘（唯一系统托盘图标，管理终端 + 课表横条）。

线程模型（关键设计，勿破坏）：
- pystray 菜单点击回调运行在它自己的消息循环线程里，
  回调中【禁止】执行任何阻塞操作（input / subprocess 等待）——
  否则整条线程被卡死，托盘假死。
- 因此回调只做两类事：纯 Win32 窗口操作（show/hide），或把事件
  塞进 _events 队列；launcher 主循环通过 get_event() 取出并执行。

功能：
1. 每 0.15 秒轮询终端窗口是否被最小化（IsIconic），是则 SW_HIDE，
   视觉效果等同「最小化到托盘」（约 0.2 秒过渡动画）。
2. 右键菜单（动态文案）：
   - 显示主窗口（双击同效）：恢复终端并置前
   - 隐藏到托盘：手动隐藏终端
   - 启动/关闭课表横条：文字由 state_getter 实时求值；
     点击后只发事件给主线程处理（可能需要终端输入模拟日期）
   - 退出 WeekRail：发退出事件，launcher 统一善后
3. 动态菜单文案用「可调用标签」（每次弹出菜单实时计算），
   不依赖 update_menu 刷新（Win32 后端对已建项的文字赋值不生效）。

已知限制：Windows Terminal 下 GetConsoleWindow 返回的是隐藏伪窗口，
轮询失效；可用「隐藏到托盘」手动隐藏。传统 conhost 完全可用。
"""
import ctypes
import queue
import threading
from pathlib import Path

from PIL import Image, ImageDraw
from pystray import Icon, Menu, MenuItem

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

SW_HIDE = 0
SW_SHOW = 5
SW_RESTORE = 9

POLL_INTERVAL = 0.15  # 轮询间隔（秒）

BASE = Path(__file__).resolve().parent
ICON_PATH = BASE / "icon.ico"

_hwnd = 0
_wt_target = 0   # WT 模式下枚举到的真终端窗口（手动隐藏后记忆，用于恢复）
_hidden = False
_stop_event = threading.Event()
_on_quit_request = None       # 退出请求回调（只设 Event，不做重活）
_state_getter = None          # 横条状态查询函数（lambda -> bool）
_can_auto_start = None      # 回调：能否不弹控制台直接启动横条
_events = queue.Queue()       # 托盘 -> 主线程的事件队列
_icon = None


def _load_image():
    try:
        return Image.open(str(ICON_PATH))
    except Exception:
        img = Image.new("RGB", (64, 64), "#185FA5")
        ImageDraw.Draw(img)
        return img


def is_native_conhost():
    """GetConsoleWindow 返回的是否为真实可见的控制台窗口。

    Windows Terminal 下该句柄是隐藏的伪窗口（不可见），轮询失效。
    """
    return bool(_hwnd) and bool(user32.IsWindowVisible(_hwnd))


def find_terminal_window():
    """WT 下的兜底：按窗口标题找真正的终端顶层窗口。返回 hwnd 或 0。"""
    if not _hwnd:
        return 0
    result = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def _enum(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        title = buf.value
        if ("Windows Terminal" in title or "终端" in title) and title.strip():
            result.append(hwnd)
        return True

    user32.EnumWindows(_enum, None)
    return result[0] if result else 0


def is_hidden():
    return _hidden


def _active_hwnd():
    """当前应被隐藏/恢复的窗口句柄：conhost 用控制台句柄，WT 用枚举到的真终端。"""
    if is_native_conhost():
        return _hwnd
    return find_terminal_window()


def hide_console():
    """手动隐藏终端（纯 Win32，可在回调线程直接执行）。"""
    global _hidden, _wt_target
    hwnd = _active_hwnd()
    if hwnd:
        user32.ShowWindow(hwnd, SW_HIDE)
        _hidden = True
        if hwnd != _hwnd:
            _wt_target = hwnd


def show_console():
    """恢复终端显示并置于前台（纯 Win32，可在回调线程直接执行）。"""
    global _hidden, _wt_target
    hwnd = _wt_target if (_wt_target and not is_native_conhost()) else _hwnd
    if hwnd:
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        _hidden = False


def _poll_loop():
    global _hidden
    while not _stop_event.wait(POLL_INTERVAL):
        try:
            if _hwnd and not _hidden and user32.IsIconic(_hwnd):
                user32.ShowWindow(_hwnd, SW_HIDE)
                _hidden = True
        except Exception:
            pass


# ---------------- 菜单回调（轻量！不做阻塞操作） ----------------

def _bar_label(item):
    """动态菜单文案：每次菜单弹出时由 pystray 实时求值。"""
    try:
        running = bool(_state_getter and _state_getter())
    except Exception:
        running = False
    return "关闭课表横条" if running else "启动课表横条"


def _cb_show(icon, item):
    show_console()


def _cb_hide(icon, item):
    hide_console()


def _can_auto_start_now():
    """托盘能否不弹控制台直接启动横条（用户至少输入过一次日期）。"""
    try:
        return bool(_can_auto_start and _can_auto_start())
    except Exception:
        return False


def _cb_toggle_display(icon, item):
    # 只有「第一次用、需要用户输入日期」时才把终端弹回来；能自动启动就不打扰
    running = bool(_state_getter and _state_getter())
    if not running and _hidden and not _can_auto_start_now():
        show_console()
    _events.put("toggle_display")
def _cb_quit(icon, item):
    icon.stop()
    _stop_event.set()
    show_console()  # 弹回终端让 launcher 的退出日志可见
    if _on_quit_request:
        _on_quit_request()


def get_event():
    """主线程非阻塞取一个托盘事件；无事件返回 None。"""
    try:
        return _events.get_nowait()
    except queue.Empty:
        return None


def refresh_menu():
    """状态变化后强制重建原生菜单，让可调用标签立即生效。

    说明：pystray Win32 后端只在菜单结构变更时重建文本，
    光靠弹出不会重算；必须在横条启停的源头调用本函数。
    """
    if _icon is not None:
        try:
            _icon.update_menu()
        except Exception:
            pass


def start(on_quit_request=None, state_getter=None, can_auto_start=None):
    """启动统一托盘图标 + 最小化监听线程。成功返回 True。

    can_auto_start：回调，返回 True 表示「点托盘就能直接开横条，不用弹控制台」。
    """
    global _hwnd, _on_quit_request, _state_getter, _can_auto_start, _icon
    _on_quit_request = on_quit_request
    _state_getter = state_getter
    _can_auto_start = can_auto_start
    _hwnd = kernel32.GetConsoleWindow()
    try:
        menu = Menu(
            MenuItem("显示主窗口", _cb_show, default=True),
            MenuItem("隐藏到托盘", _cb_hide),
            Menu.SEPARATOR,
            MenuItem(_bar_label, _cb_toggle_display),
            Menu.SEPARATOR,
            MenuItem("退出 WeekRail", _cb_quit),
        )
        _icon = Icon("WeekRail", _load_image(), "WeekRail · 周轨", menu)
        _icon.run_detached()
    except Exception:
        _icon = None
        return False
    threading.Thread(target=_poll_loop, daemon=True).start()
    return True


def stop():
    """停止托盘图标与轮询线程（launcher 退出路径调用）。"""
    _stop_event.set()
    if _icon is not None:
        try:
            _icon.stop()
        except Exception:
            pass
