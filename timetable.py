# -*- coding: utf-8 -*-
"""7. 查看课表（文字说明）：按课程输出自然语言描述。

唯一的归组规则：**按"每一周的课表指纹"分段**（不再区分"按周次"还是"按时段"两套规则）
1. 先算出每一周"这周要上什么"：星期几 -> 第几节（同一周同一星期几的多条条目取并集）；
2. 指纹完全相同的周合并成一段——第 5、6、7、10、11 周都是"周二 3-5 节"，于是合成
   `第5-7, 10-11周，星期二 第3-5节`；第 9 周是"周一 + 周四都是 11-12 节"，于是
   `第9周，星期一、四 第11-12节`；
3. 段内按「节次集合」合并星期几（节次相同的日子写成 `星期一、四`），不同时段用 `，` 接着写；
4. 不同指纹的周段之间用 `；` 分隔，按各段最小周次排序。

示例：
[11]大学物理实验II（大物实验）：第4周，星期六 第11-12节；第5-7, 10-11周，星期二 第3-5节；
第8周，星期日 第8-10节；第9周，星期一、四 第11-12节；第12周，星期四 第11-12节。
"""
import storage


def _fmt_weeks(weeks):
    return storage.fmt_ranges(sorted(storage.week_label(w) for w in weeks)).replace(",", ", ")


def _fmt_periods(periods):
    return storage.fmt_ranges(sorted(periods)).replace(",", ", ")


def _weekday_text(weekdays):
    chars = [storage.WEEKDAY_CN[w][-1] for w in sorted(weekdays)]
    return "星期" + "、".join(chars)


def describe_subject(subject, entries):
    """把一门课的所有课表条目合并成一句话。"""
    head = "[%d]%s（%s）：" % (subject["id"], subject.get("name", ""), subject.get("short_name", ""))
    # 每一周的"课表指纹"：星期几 -> 第几节
    week_shape = {}
    for entry in entries:
        periods = set(entry.get("periods", []))
        for week in set(entry.get("weeks", [])):
            shape = week_shape.setdefault(int(week), {})
            for weekday in entry.get("weekdays", []):
                shape.setdefault(weekday, set()).update(periods)
    if not week_shape:
        return head + "暂无课表条目。"

    # 指纹相同的周合并成一段
    groups = {}
    for week, shape in week_shape.items():
        key = tuple(sorted((wd, tuple(sorted(pe))) for wd, pe in shape.items() if pe))
        groups.setdefault(key, []).append(week)

    parts = []
    for key in sorted(groups, key=lambda k: (min(groups[k]), k)):
        by_periods = {}
        for weekday, periods in key:
            by_periods.setdefault(frozenset(periods), []).append(weekday)
        chunks = []
        for periods, weekdays in sorted(by_periods.items(), key=lambda kv: (min(kv[0]), min(kv[1]))):
            chunks.append("%s 第%s节" % (_weekday_text(weekdays), _fmt_periods(periods)))
        parts.append("第%s周，%s" % (_fmt_weeks(sorted(groups[key])), "，".join(chunks)))
    return head + "；".join(parts) + "。"


def describe_all():
    """所有课程的文字课表（按课程编号排序）。"""
    subjects = sorted(storage.load_subjects(), key=lambda s: s["id"])
    lessons = storage.load_lessons()
    return [describe_subject(sub, [l for l in lessons if l.get("subject_id") == sub["id"]])
            for sub in subjects]


def main():
    print("== 当前课表（文字说明）==")
    lines = describe_all()
    if not lines:
        print("  （还没有课程，请先到 [1] 管理课程 添加）")
    else:
        for line in lines:
            print("  " + line)
    print()
    input("按回车返回菜单...")


if __name__ == "__main__":
    main()
