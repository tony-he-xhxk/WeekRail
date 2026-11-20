# -*- coding: utf-8 -*-
"""0. 初始化：设置学期开始日期与总周数。"""
from datetime import date

import storage


def redefine_week1():
    """把当前来源的第 1 周改到另一个周一，并整体平移课表周次。

    返回 True 表示有修改（launcher 据此重启横条）。
    """
    cfg = storage.load_config()
    if not cfg:
        print("[ERR] 先执行 [0] 初始化学期。")
        return False
    try:
        old_start = date.fromisoformat(cfg["start_date"])
        old_total = int(cfg["total_weeks"])
    except (ValueError, KeyError):
        print("[ERR] 学期配置无效，请先重新初始化。")
        return False
    print("== 重定义第 1 周 ==")
    print("当前：第 1 周 = %s，共 %d 周" % (old_start.isoformat(), old_total))
    while True:
        raw = input("新的第 1 周日期（必须是周一，YYYY-MM-DD；回车取消）：").strip()
        if not raw:
            return False
        try:
            new_start = date.fromisoformat(raw)
        except ValueError:
            print("[ERR] 日期格式应为 YYYY-MM-DD")
            continue
        if new_start.weekday() != 0:
            print("[ERR] %s 不是周一，已拒绝重定义。" % new_start.isoformat())
            continue
        break
    delta = (new_start - old_start).days // 7
    if delta == 0:
        print("[INFO] 第 1 周没有变化。")
        return False
    new_total = max(1, old_total - delta)
    print("第 1 周：%s -> %s（整体%s %d 周）"
          % (old_start.isoformat(), new_start.isoformat(),
             "后移" if delta > 0 else "前移", abs(delta)))
    if delta > 0:
        print("原第 %d 周将变成第 1 周；更早的周显示为 -1、-2、-3……（没有第 0 周）。" % (1 + delta))
    else:
        print("第 1 周整体前移 %d 周。" % abs(delta))
    if input("确认重定义？(y/n)：").strip().lower() != "y":
        print("已取消")
        return False
    lessons = storage.load_lessons()
    for lesson in lessons:
        lesson["weeks"] = [int(w) - delta for w in lesson.get("weeks", [])]
    storage.save_lessons(lessons)
    storage.save_config({"start_date": new_start.isoformat(), "total_weeks": new_total})
    print("[OK] 已重定义：第 1 周 = %s，共 %d 周" % (new_start.isoformat(), new_total))
    return True

def main():
    cfg = storage.load_config()
    print("== 学期初始化 ==")
    if cfg:
        print("当前设置：开学 %s，总周数 %s 周" % (cfg["start_date"], cfg["total_weeks"]))
        print("提示：只想把第 1 周改到另一个周一（并整体平移课表），请用 [9]；这里改日期不会平移课表。")
    else:
        print("尚未初始化。")

    while True:
        raw = input("开学日期（第 1 周周一，格式 YYYY-MM-DD）：").strip()
        try:
            y, m, d = map(int, raw.split("-"))
            sd = date(y, m, d)
        except ValueError:
            print("[ERR] 格式错误，应为 YYYY-MM-DD")
            continue
        if sd.weekday() != 0:
            print("[WARN] %s 不是周一（%s），周次将以该日期为第 1 周起点计算" % (sd, storage.WEEKDAY_CN[sd.weekday() + 1]))
            if input("仍要使用该日期吗？(y/n)：").strip().lower() != "y":
                continue
        break

    while True:
        raw = input("总周数（正整数）：").strip()
        if not raw.isdigit() or int(raw) <= 0:
            print("[ERR] 请输入正整数")
            continue
        total = int(raw)
        break

    storage.save_config({"start_date": sd.isoformat(), "total_weeks": total})
    print("[OK] 已保存：开学 %s（%s），共 %d 周" % (sd.isoformat(), storage.WEEKDAY_CN[sd.weekday() + 1], total))
    input("按回车返回菜单...")


if __name__ == "__main__":
    main()
