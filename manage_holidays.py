# -*- coding: utf-8 -*-
"""6. 管理假期：添加 / 删除 / 查看。

- 添加：输入起止日期，把这段设为假期（原本有课也不上；课程数据不会被删除）。
- 删除：只删除落在已有假期里的部分，没落在假期里的日期会提示已忽略。
- 查看：手动假期段 + 自动假期（学期内整天没课的日期）。
"""
from datetime import date, timedelta

import holidays


def _ask_date(prompt, default=None):
    while True:
        raw = input(prompt).strip()
        if not raw and default is not None:
            return default
        try:
            return date.fromisoformat(raw)
        except ValueError:
            print("[ERR] 日期格式应为 YYYY-MM-DD")


def _fmt_ranges(ranges):
    return "、".join("%s~%s" % (s.isoformat(), e.isoformat()) for s, e in ranges)


def _days_count(ranges):
    return sum((e - s).days + 1 for s, e in ranges)


def show_list():
    ranges = holidays.load_ranges()
    print("-- 手动假期段 --")
    if not ranges:
        print("  （暂无；整天没课的日子会自动按假期显示）")
    else:
        for s, e in ranges:
            print("  %s ~ %s  （%d 天）" % (s.isoformat(), e.isoformat(), (e - s).days + 1))
        print("  合计 %d 天" % _days_count(ranges))
    free = holidays.free_dates()
    print("-- 自动假期（学期内整天没课，实时判定，不落盘）--")
    if not free:
        print("  （没有整天没课的日子）")
    else:
        print("  共 %d 天：%s" % (len(free), " ".join(d.strftime("%m-%d") for d in free)))
    return ranges


def add_holiday():
    print("== 添加假期 ==")
    start = _ask_date("开始日期（YYYY-MM-DD）：")
    end = _ask_date("结束日期（YYYY-MM-DD，直接回车 = 同开始）：", default=start)
    if end < start:
        start, end = end, start
    days = (end - start).days + 1
    busy = holidays.busy_dates()
    hit = [d for d in (start + timedelta(days=i) for i in range(days)) if d in busy]
    if hit:
        print("[INFO] 这段里有 %d 天原本有课（例如 %s）：设成假期后横条显示「今日假期」，"
              "课程数据不会被删除。" % (len(hit), hit[0].isoformat()))
    if input("确认把 %s ~ %s（%d 天）设为假期？(y/n)："
             % (start.isoformat(), end.isoformat(), days)).strip().lower() != "y":
        print("已取消")
        return
    holidays.add_range(start, end)
    print("[OK] 已添加假期 %s ~ %s" % (start.isoformat(), end.isoformat()))


def remove_holiday():
    print("== 删除假期 ==")
    if not holidays.load_ranges():
        print("[INFO] 当前没有任何手动假期，无需删除。")
        return
    start = _ask_date("开始日期（YYYY-MM-DD）：")
    end = _ask_date("结束日期（YYYY-MM-DD，直接回车 = 同开始）：", default=start)
    if end < start:
        start, end = end, start
    covered = holidays.intersect(start, end)
    if not covered:
        print("[INFO] %s ~ %s 不在任何已添加的假期时段内，未做任何修改。"
              % (start.isoformat(), end.isoformat()))
        return
    print("这些日期确实在假期里，将删除：%s" % _fmt_ranges(covered))
    if covered != [(start, end)]:
        print("[INFO] 以下日期本来就不是假期，将忽略：%s"
              % _fmt_ranges(holidays.subtract(start, end, covered)))
    if input("确认删除上述 %d 天假期？(y/n)：" % _days_count(covered)).strip().lower() != "y":
        print("已取消")
        return
    removed, uncovered = holidays.remove_range(start, end)
    print("[OK] 已删除 %d 个假期时段（共 %d 天）" % (len(removed), _days_count(removed)))
    if uncovered:
        print("[INFO] 已忽略本来不是假期的 %d 天" % _days_count(uncovered))


def main():
    while True:
        print()
        print("[a] 添加假期    [d] 删除假期    [l] 查看假期    [q] 返回")
        cmd = input("请选择：").strip().lower()
        if cmd == "q":
            break
        elif cmd == "a":
            add_holiday()
        elif cmd == "d":
            remove_holiday()
        elif cmd == "l":
            show_list()
        else:
            print("[ERR] 无效选择")


if __name__ == "__main__":
    main()
