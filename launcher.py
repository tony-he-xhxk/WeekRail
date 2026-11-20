# -*- coding: utf-8 -*-
"""WeekRail 统一启动器：终端菜单循环，执行完一项回到菜单，不退出。

窗口行为：
- 启动时创建统一托盘图标（唯一系统托盘入口，复用 icon.ico）。
- 终端最小化 ≈0.2 秒后自动隐藏（连任务栏图标一起消失），双击托盘恢复；
  托盘右键：显示主窗口 / 隐藏到托盘 / 启动·关闭课表横条 / 退出。
- 课表横条由托盘与终端菜单共同管理，状态实时同步到托盘菜单项。
- 主菜单输入用非阻塞轮询实现，托盘「退出」随时生效；
  子程序（管理课程/课表等）内部仍是阻塞 input()，
  此时点托盘退出会等当前操作完成后再退出。
- display 进程带父进程看门狗：launcher 异常死亡时横条自动退出，不留孤儿。
"""
import os
import subprocess
import sys
import threading
import time
from datetime import date
from pathlib import Path

import init
import manage_holidays
import manage_lessons
import manage_sources
import manage_subjects
import reset
import storage
import timetable
import tray_win

try:
    import msvcrt  # Windows 专属，用于非阻塞键盘读取
except ImportError:
    msvcrt = None

BASE = Path(__file__).resolve().parent
PY = sys.executable

_display_proc = None   # 当前课表显示进程
_display_sim = None       # 当前横条用的模拟日期（None = 今天）
_proc_lock = threading.Lock()
_quit_requested = threading.Event()  # 托盘退出请求


def _display_alive():
    with _proc_lock:
        return _display_proc is not None and _display_proc.poll() is None


def stop_display():
    """关闭当前课表显示进程（若有），避免多次启动堆叠。"""
    global _display_proc
    with _proc_lock:
        p, _display_proc = _display_proc, None
    if p is not None and p.poll() is None:
        p.terminate()
        try:
            p.wait(timeout=3)
        except subprocess.TimeoutExpired:
            p.kill()
        print("[OK] 已关闭课表横条")
    tray_win.refresh_menu()  # 重建原生菜单，托盘文案立即反映"启动课表横条"


def toggle_display():
    """托盘事件（主线程执行）。

    横条存活则关；否则按「上次 [3] 的输入」直接开：
    - 上次输入了具体日期 -> 继续显示那个日期；
    - 上次直接回车（= 今天）-> 这次同样显示今天；
    - 从没用过 [3] -> 回到交互询问（托盘那侧会先把控制台弹回来）。
    """
    if _display_alive():
        stop_display()
        return
    used, last = storage.load_last_date()
    if not used:
        _start_display()
    else:
        _start_display(sim=(last or None), ask=False)


def _can_auto_start():
    """托盘「启动课表横条」能否不弹控制台直接开（用过一次 [3] 就行）。"""
    return storage.load_last_date()[0]


def _ask_sim_date():
    """询问模拟日期，并记住这次输入（空 = 今天）。"""
    while True:
        raw = input("模拟日期（YYYY-MM-DD，直接回车用今天）：").strip()
        if not raw:
            storage.save_last_date("")
            return ""
        try:
            date.fromisoformat(raw)
        except ValueError:
            print("[ERR] 日期格式无效，应为 YYYY-MM-DD")
            continue
        storage.save_last_date(raw)
        return raw


def _start_display(sim=None, ask=True):
    """启动课表显示（选择 [3] 后调用）。

    ask=True  交互询问模拟日期（直接回车用今天），终端菜单 [3] 走这条路。
    ask=False 不询问，直接用 sim（None 表示今天），--auto 一键启动走这条路。
    """
    global _display_proc, _display_sim
    if ask:
        sim = _ask_sim_date() or None      # 询问并记住这次输入（空 = 今天）
    else:
        storage.save_last_date(sim or "")  # --auto / 托盘 / 重启：记住这次实际用的日期
    _display_sim = sim
    args = [PY, str(BASE / "display.py")]
    if sim:
        args += ["--date", sim]
    # display 用"父进程 PID + 等待句柄"判断 launcher 是否还活着。
    # 旧写法用 DuplicateHandle 传继承句柄，但 Python 的 subprocess 默认 close_fds=True，
    # 子进程拿不到那个句柄，看门狗其实一直没生效。
    env_display = dict(os.environ, WEEKRAIL_PARENT_PID=str(os.getpid()))
    with _proc_lock:
        _display_proc = subprocess.Popen(args, env=env_display)
    tray_win.refresh_menu()  # 重建原生菜单，托盘文案立即反映"关闭课表横条"
    print("[OK] 课表横条已启动（托盘可关闭/退出）")


def _shutdown():
    """统一善后：关课表横条 + 停托盘。"""
    stop_display()
    tray_win.stop()


def _read_choice(prompt):
    """非阻塞读一行输入；等待期间处理托盘事件与退出请求。

    返回输入的字符串；若托盘请求退出则返回 None。
    支持：逐字符回显、退格、忽略方向键前缀。
    """
    if msvcrt is None or not sys.stdin.isatty():
        try:
            return input(prompt)
        except EOFError:
            return None
    print(prompt, end="", flush=True)
    buf = ""
    while True:
        ev = tray_win.get_event()
        if ev == "toggle_display":
            print()
            toggle_display()
            return "\n"  # 特殊标记：托盘事件已处理，main 直接重绘菜单不报错
        if _quit_requested.is_set():
            print()
            return None
        if msvcrt.kbhit():
            ch = msvcrt.getwch()
            if ch in ("\r", "\n"):
                print()
                return buf.strip().lower()
            if ch == "\x00" or ch == "\xe0":  # 方向键/F 键前缀，吞掉扫描码
                msvcrt.getwch()
                continue
            if ch == "\x08":  # 退格
                if buf:
                    buf = buf[:-1]
                    print("\b \b", end="", flush=True)
                continue
            buf += ch
            print(ch, end="", flush=True)
        else:
            time.sleep(0.05)


def _ask_percent(prompt, current):
    """让用户输入 0-100 的百分比；直接回车保持不变。"""
    while True:
        raw = input(prompt % current).strip()
        if not raw:
            return current
        if raw.isdigit() and 0 <= int(raw) <= 100:
            return int(raw)
        print("[ERR] 请输入 0-100 的整数（直接回车保持不变）")


def display_settings():
    """[5] 调整横条不透明度：非假期 / 假期 各两档（正常 + 悬停），共四档。"""
    prefs = storage.load_prefs()
    print("== 显示设置（横条不透明度）==")
    print("提示：数字越大越不透明；鼠标悬停时横条会淡出，方便看清下面的内容。")
    print("假期那两档只作用于显示「今日假期」的横条：不想让它挡住后面的内容，可以调低一些。")
    normal = _ask_percent("非假期 · 正常显示（0-100，当前 %d，回车保持）：", prefs["opacity_normal"])
    hover = _ask_percent("非假期 · 鼠标悬停（0-100，当前 %d，回车保持）：", prefs["opacity_hover"])
    holiday_normal = _ask_percent("假期   · 正常显示（0-100，当前 %d，回车保持）：",
                                  prefs["holiday_normal"])
    holiday_hover = _ask_percent("假期   · 鼠标悬停（0-100，当前 %d，回车保持）：",
                                 prefs["holiday_hover"])
    saved = storage.save_prefs({"opacity_normal": normal, "opacity_hover": hover,
                                "holiday_normal": holiday_normal,
                                "holiday_hover": holiday_hover})
    print("[OK] 已保存：")
    print("     非假期：正常 %d%%，悬停 %d%%" % (saved["opacity_normal"], saved["opacity_hover"]))
    print("     假期  ：正常 %d%%，悬停 %d%%" % (saved["holiday_normal"], saved["holiday_hover"]))
    print("[INFO] 横条按当天是否假期自动选用对应的一套。")
    if _display_alive():
        print("[INFO] 重启课表横条以立即应用新设置…")
        current = _display_sim            # 保持横条当前在看的那一天
        stop_display()
        _start_display(sim=current, ask=False)
    else:
        print("[INFO] 下次打开课表横条时生效。")


def _first_run_needed():
    """还没建立任何课表（全新安装）时返回 True。"""
    import sources
    if sources.has_ics_source():
        return False
    return not (storage.load_config() or storage.load_subjects() or storage.load_lessons())


def _first_run_wizard():
    """首次使用：选择用 ICS 导入还是手动创建。"""
    print("== 首次使用：选择课表来源 ==")
    print("  [i] 从 ICS 文件导入（先把 .ics 放进 课表ics/ 文件夹）")
    print("  [m] 手动创建（先初始化学期，再录入课程 / 课表）")
    while True:
        cmd = input("请选择：").strip().lower()
        if cmd == "i":
            if manage_sources.import_flow(first_run=True):
                return
            print("（没有导入成功，请重新选择）")
        elif cmd == "m":
            init.main()
            return
        else:
            print("[ERR] 请输入 i 或 m")

def main(argv=None):
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    if any(a in ("-h", "--help") for a in argv):
        print("用法：python launcher.py [--auto]")
        print("  --auto  启动后直接打开课表显示（今天），不再询问 [3] 和模拟日期")
        print("  --auto --no-minimize  同上，但保留终端窗口便于查看输出")
        return 0
    auto = any(a in ("--auto", "-a", "--auto-display") for a in argv)
    no_minimize = "--no-minimize" in argv
    print("== WeekRail（周轨）大学生课表工具 ==")
    ok = tray_win.start(on_quit_request=_request_quit,
                        state_getter=_display_alive,
                        can_auto_start=_can_auto_start)
    if ok:
        if tray_win.is_native_conhost():
            print("[OK] 统一托盘已启用：终端最小化约 0.2 秒后自动隐藏，"
                  "双击托盘图标恢复；右键可开关课表横条")
        else:
            print("[INFO] 检测到 Windows Terminal：最小化自动隐藏不可用，"
                  "请用托盘右键「隐藏到托盘」")
    else:
        print("[WARN] 托盘启动失败，以普通终端模式运行")
    print()
    if _first_run_needed():
        print("[INFO] 还没有任何课表，先选择建立方式。")
        _first_run_wizard()
        auto = False      # 首次配置时不要自动隐藏控制台
        print()
    if auto:
        print("[AUTO] 一键启动：直接打开课表显示（今天）")
        _start_display(ask=False)
        if ok and not no_minimize:
            # 先确认 display 进程真的活着，再藏终端，避免出错时窗口被藏起来看不见提示
            waited = 0.0
            while waited < 1.5 and _display_alive():
                time.sleep(0.1)
                waited += 0.1
            if _display_alive():
                tray_win.hide_console()  # 与托盘“隐藏终端窗口”同一路径
                print("[AUTO] 终端已自动最小化，可从托盘图标重新显示。")
            else:
                print("[WARN] 课表显示未启动，保留终端窗口以便查看报错。")
        print()
    while True:
        cfg = storage.load_config()
        if cfg:
            print("学期：%s 开学，共 %s 周" % (cfg["start_date"], cfg["total_weeks"]))
        else:
            print("学期：未初始化")
        print()
        print("[0] 初始化（开学日期 + 总周数）")
        print("[1] 管理课程（科目）")
        print("[2] 管理课表")
        print("[3] 启动课表显示" + ("（已在运行，将先重启刷新）" if _display_alive() else ""))
        print("[4] 清除所有数据（新学期重置）")
        print("[5] 显示设置（横条不透明度）")
        print("[6] 假期管理（添加 / 删除 / 查看）")
        print("[7] 查看课表（文字说明）")
        print("[8] 课表来源（ICS 导入 / 切换）")
        print("[9] 重定义第 1 周（整体平移课表）")
        print("[q] 退出（也可用托盘右键退出）")
        cmd = _read_choice("请选择：")
        if cmd is None or cmd == "q":
            break
        elif cmd == "\n":  # 托盘事件已在 _read_choice 中处理，静默重绘菜单
            continue
        elif cmd == "":   # 直接回车：重绘菜单，不报错
            continue
        elif cmd == "0":
            init.main()
            _drain_events()
        elif cmd == "1":
            manage_subjects.main()
            _drain_events()
        elif cmd == "2":
            manage_lessons.main()
            _drain_events()
        elif cmd == "3":
            stop_display()  # 先关旧显示，避免堆叠
            _start_display()
        elif cmd == "4":
            reset.main()
            _drain_events()
        elif cmd == "5":
            display_settings()
            _drain_events()
        elif cmd == "6":
            manage_holidays.main()
            _drain_events()
        elif cmd == "7":
            timetable.main()
            _drain_events()
        elif cmd == "8":
            changed = manage_sources.main()
            if changed and _display_alive():
                print("[INFO] 课表来源已切换，重启横条…")
                current = _display_sim
                stop_display()
                _start_display(sim=current, ask=False)
            _drain_events()
        elif cmd == "9":
            if init.redefine_week1() and _display_alive():
                print("[INFO] 周次已重定义，重启横条…")
                current = _display_sim
                stop_display()
                _start_display(sim=current, ask=False)
            _drain_events()
        else:
            print("[ERR] 无效选择")

    _shutdown()
    print("再见")


def _drain_events():
    """子程序返回后，消化积压的托盘事件（避免丢失）。"""
    while True:
        ev = tray_win.get_event()
        if ev is None:
            break
        if ev == "toggle_display":
            toggle_display()


def _request_quit():
    """托盘「退出 WeekRail」回调。"""
    _quit_requested.set()


if __name__ == "__main__":
    main()
