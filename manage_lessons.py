# -*- coding: utf-8 -*-
"""2. 管理课表：四元组录入（科目+星期+节次+周次），冲突检测与二次确认，支持删除。"""
from datetime import date

import holidays
import storage


def show_subjects():
    subjects = storage.load_subjects()
    print("-- 科目列表 --")
    if not subjects:
        print("  （暂无科目，请先执行 [1] 管理课程 添加）")
    for s in subjects:
        print("  [%3d] %s（%s）" % (s["id"], s["short_name"], s["name"]))
    return subjects


def wd_cn(weekdays):
    return "、".join(storage.WEEKDAY_CN[w] for w in weekdays)


def _sync_holidays(lesson):
    """往假期里加课时，把那几天从手动假期里挖掉（课程数据不受影响）。"""
    cfg = storage.load_config()
    if not cfg:
        return
    start = date.fromisoformat(cfg["start_date"])
    hit = holidays.clear_dates(holidays.lesson_dates(lesson, start))
    if hit:
        print("[INFO] 这些天原本是假期，已自动取消其假期属性：%s"
              % "、".join(d.isoformat() for d in hit))



def main():
    subjects = show_subjects()
    if not subjects:
        print("[ERR] 没有科目，请先到 [1] 管理课程 添加")
        input("按回车返回...")
        return
    sub_map = {s["id"]: s for s in subjects}
    while True:
        print()
        print("[a] 添加 / 编辑课程    [d] 删除整条课程    [p] 精确删除（科目+星期+节次）    [q] 返回")
        cmd = input("请选择：").strip().lower()
        if cmd == "q":
            break
        elif cmd == "a":
            add_or_edit(sub_map)
        elif cmd == "d":
            delete_lesson(sub_map)
        elif cmd == "p":
            precise_delete(sub_map)
        else:
            print("[ERR] 无效选择")


def add_or_edit(sub_map):
    lessons = storage.load_lessons()
    raw = input("科目编号：").strip()
    if not raw.isdigit() or int(raw) not in sub_map:
        print("[ERR] 科目编号无效")
        return
    sid = int(raw)

    wd = input("星期（1-7，周一=1，支持范围如 2,4）：").strip()
    weekdays = storage.parse_ranges(wd, 7, "星期")
    if weekdays is None:
        print("[ERR] 星期范围无效")
        return

    pe = input("节次（1-13，支持范围如 3-5,6-7）：").strip()
    periods = storage.parse_ranges(pe, 13, "节次")
    if periods is None:
        print("[ERR] 节次范围无效")
        return

    cfg = storage.load_config()
    max_week = cfg["total_weeks"] if cfg else 20
    wk = input("周次（1-%d，支持范围如 1-2,6-7）：" % max_week).strip()
    weeks = storage.parse_ranges(wk, max_week, "周次")
    if weeks is None:
        print("[ERR] 周次范围无效（应为 1-%d）" % max_week)
        return

    sub = sub_map[sid]
    wd_text = wd_cn(weekdays)
    pe_fmt = storage.fmt_ranges(periods)
    wk_fmt = storage.fmt_ranges(weeks)

    # 1) 同科目 + 同星期 + 同节次：只在"周次完全相同"时算重复；周次有重叠问是否合并；
    #    周次不重叠（例如已有第5周、再录第6周）按新增处理，不再走"编辑"把旧周次覆盖掉。
    same_slot = [l for l in lessons
                 if l["subject_id"] == sid
                 and set(l["weekdays"]) == set(weekdays)
                 and set(l["periods"]) == set(periods)]
    if same_slot:
        if any(set(l["weeks"]) == set(weeks) for l in same_slot):
            print("[INFO] 已存在完全相同的条目：【%s】星期%s 第%s节 第%s周，未做修改。"
                  % (sub["short_name"], wd_text, pe_fmt, wk_fmt))
            return
        overlapping = [l for l in same_slot if set(l["weeks"]) & set(weeks)]
        if overlapping:
            old = overlapping[0]
            merged = sorted(set(old["weeks"]) | set(weeks))
            if input("该时段已有【%s】第%s周，与本次第%s周有重叠，要合并成第%s周吗？(y/n)："
                     % (sub["short_name"], storage.fmt_ranges(old["weeks"]), wk_fmt,
                        storage.fmt_ranges(merged))).strip().lower() == "y":
                old["weeks"] = merged
                storage.save_lessons(lessons)
                print("[OK] 已合并【%s】星期%s 第%s节 -> 第%s周"
                      % (sub["short_name"], wd_text, pe_fmt, storage.fmt_ranges(merged)))
                _sync_holidays(old)
                return

    # 2) 星期 ∩ 节次 ∩ 周次 均有交集的其他科目 -> 冲突（同科目的不同周次不算冲突，各存一条）
    conflict = [l for l in lessons
                if l["subject_id"] != sid
                and set(l["weekdays"]) & set(weekdays)
                and set(l["periods"]) & set(periods)
                and set(l["weeks"]) & set(weeks)]
    if conflict:
        for l in conflict:
            other = sub_map.get(l["subject_id"], {"short_name": "?%d" % l["subject_id"]})
            print("[WARN] 与现有课程冲突：【%s】星期%s 第%s节 第%s周" % (
                other["short_name"], wd_cn(l["weekdays"]),
                storage.fmt_ranges(l["periods"]), storage.fmt_ranges(l["weeks"])))
        if input("继续将删除以上 %d 条冲突课程并创建新课程，确定吗？(y/n)：" % len(conflict)).strip().lower() != "y":
            print("已取消")
            return
        lessons = [l for l in lessons if l not in conflict]
        lessons.append({"subject_id": sid, "weekdays": weekdays, "periods": periods, "weeks": weeks})
        storage.save_lessons(lessons)
        print("[OK] 已覆盖并创建【%s】星期%s 第%s节 第%s周" % (sub["short_name"], wd_text, pe_fmt, wk_fmt))
        _sync_holidays(lessons[-1])
        return

    # 3) 创建
    if input("您即将创建第 %s 周的【%s】（星期%s 第%s节），确定吗？(y/n)：" % (wk_fmt, sub["short_name"], wd_text, pe_fmt)).strip().lower() != "y":
        print("已取消")
        return
    lessons.append({"subject_id": sid, "weekdays": weekdays, "periods": periods, "weeks": weeks})
    storage.save_lessons(lessons)
    print("[OK] 已创建【%s】星期%s 第%s节 第%s周" % (sub["short_name"], wd_text, pe_fmt, wk_fmt))
    _sync_holidays(lessons[-1])


def delete_lesson(sub_map):
    lessons = storage.load_lessons()
    if not lessons:
        print("（暂无课程条目）")
        return
    print("-- 当前课表 --")
    for i, l in enumerate(lessons):
        sub = sub_map.get(l["subject_id"], {"short_name": "?%d" % l["subject_id"]})
        print("  #%d  [%s] 星期%s 第%s节 第%s周" % (i, sub["short_name"], wd_cn(l["weekdays"]),
                                                   storage.fmt_ranges(l["periods"]),
                                                   storage.fmt_ranges(l["weeks"])))
    raw = input("输入要删除的条目序号 #（直接回车返回）：").strip()
    if not raw:
        return
    if not raw.isdigit() or int(raw) >= len(lessons):
        print("[ERR] 序号无效")
        return
    idx = int(raw)
    l = lessons[idx]
    sub = sub_map.get(l["subject_id"], {"short_name": "?%d" % l["subject_id"]})
    if input("确认删除 #%d  [%s] 星期%s 第%s节 第%s周？(y/n)：" % (idx, sub["short_name"], wd_cn(l["weekdays"]),
                                                               storage.fmt_ranges(l["periods"]),
                                                               storage.fmt_ranges(l["weeks"]))).strip().lower() != "y":
        print("已取消")
        return
    lessons.pop(idx)
    storage.save_lessons(lessons)
    print("[OK] 已删除 #%d" % idx)


def precise_delete(sub_map):
    """按 科目 + 星期 + 节次（可选限定周次）精确删掉某几节。

    删除后会按剩余内容自动重组条目：
    - 同一条记录里的其它星期几：原样保留；
    - 限定了周次时：未命中的周次原样保留，命中的周次只删掉指定节次；
    - 某条记录被删空则整条移除。
    """
    lessons = storage.load_lessons()
    raw = input("科目编号：").strip()
    if not raw.isdigit() or int(raw) not in sub_map:
        print("[ERR] 科目编号无效")
        return
    sid = int(raw)
    sub = sub_map[sid]

    wd = input("星期（1-7，周一=1，支持 3 或 2,4）：").strip()
    weekdays = storage.parse_ranges(wd, 7, "星期")
    if not weekdays:
        print("[ERR] 星期范围无效")
        return
    pe = input("要删除的节次（1-13，支持 3-5 或 4）：").strip()
    periods = storage.parse_ranges(pe, 13, "节次")
    if not periods:
        print("[ERR] 节次范围无效")
        return
    cfg = storage.load_config()
    max_week = cfg["total_weeks"] if cfg else 20
    wk = input("限定周次（直接回车 = 所有周次；支持 5 或 5-7）：").strip()
    week_filter = None
    if wk:
        week_filter = storage.parse_ranges(wk, max_week, "周次")
        if week_filter is None:
            print("[ERR] 周次范围无效")
            return

    days = set(weekdays)
    pset = set(periods)
    wset = None if week_filter is None else set(week_filter)

    plan = []          # (条目, 命中的星期, 命中的周次, 命中的节次)
    for lesson in lessons:
        if lesson["subject_id"] != sid:
            continue
        days_hit = set(lesson["weekdays"]) & days
        if not days_hit:
            continue
        weeks_hit = set(lesson["weeks"]) & (wset if wset is not None else set(lesson["weeks"]))
        if not weeks_hit:
            continue
        periods_hit = set(lesson["periods"]) & pset
        if not periods_hit:
            continue
        plan.append((lesson, days_hit, weeks_hit, periods_hit))
    if not plan:
        print("[INFO] 没有找到匹配的节次（该科目在这些星期/周次里没有这几节），未做修改。")
        return

    print("-- 将删除以下节次 --")
    for lesson, days_hit, weeks_hit, periods_hit in plan:
        print("  【%s】星期%s 第%s节（第%s周）"
              % (sub["short_name"], wd_cn(sorted(days_hit)),
                 storage.fmt_ranges(sorted(periods_hit)),
                 storage.fmt_ranges(sorted(weeks_hit))))

    # 先算出删除后的完整数据（不落盘），供确认时预览
    planned = {id(lesson) for lesson, *_ in plan}
    rebuilt = []
    for lesson in lessons:
        if id(lesson) not in planned:
            rebuilt.append(lesson)
            continue
        _, days_hit, weeks_hit, periods_hit = next(p for p in plan if p[0] is lesson)
        days_out = set(lesson["weekdays"]) - days_hit
        weeks_out = set(lesson["weeks"]) - weeks_hit
        periods_left = set(lesson["periods"]) - periods_hit
        if days_out:                                   # 其它星期几：原样保留
            rebuilt.append({"subject_id": sid, "weekdays": sorted(days_out),
                            "periods": sorted(lesson["periods"]),
                            "weeks": sorted(lesson["weeks"])})
        if days_hit and weeks_out:                     # 命中的星期几 + 未命中的周次
            rebuilt.append({"subject_id": sid, "weekdays": sorted(days_hit),
                            "periods": sorted(lesson["periods"]),
                            "weeks": sorted(weeks_out)})
        if days_hit and weeks_hit and periods_left:    # 命中的周次里剩下的节次
            rebuilt.append({"subject_id": sid, "weekdays": sorted(days_hit),
                            "periods": sorted(periods_left),
                            "weeks": sorted(weeks_hit)})

    seen, deduped = set(), []
    for lesson in rebuilt:
        key = (lesson["subject_id"], tuple(sorted(lesson["weekdays"])),
               tuple(sorted(lesson["periods"])), tuple(sorted(lesson["weeks"])))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(lesson)

    print("-- 删除后该科目的条目 --")
    remaining = [l for l in deduped if l["subject_id"] == sid]
    if not remaining:
        print("  （该科目没有任何条目了）")
    for lesson in remaining:
        print("  星期%s 第%s节 第%s周"
              % (wd_cn(lesson["weekdays"]), storage.fmt_ranges(lesson["periods"]),
                 storage.fmt_ranges(lesson["weeks"])))

    if input("确认删除以上节次？(y/n)：").strip().lower() != "y":
        print("已取消")
        return
    storage.save_lessons(deduped)
    print("[OK] 已删除 %d 处匹配的节次；当前共 %d 条课程记录。" % (len(plan), len(deduped)))

if __name__ == "__main__":
    main()
