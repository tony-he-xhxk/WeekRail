# -*- coding: utf-8 -*-
"""假期：手动假期段（落盘）+「当天整天没课」的自动假期（实时判定）。

两层设计：
- 手动假期段存 data/holidays.json，形如 [{"start": "2026-10-01", "end": "2026-10-08"}]，
  保存时自动排序并合并重叠 / 相邻的段。中秋国庆这类「原本有课也不上」的日子放这里。
- 自动假期不落盘：学期内某一天，如果那一周那一星期几没有任何课程，就按假期显示。
  所以初始化 / 改课表 / 加课之后都不需要额外同步，显示时实时算出来。
- 往假期里加课时用 clear_dates() 把那几天从手动假期里挖掉（会把整段拆开）。
"""
from datetime import date, timedelta

import storage

NAME = "holidays.json"


def _parse(value):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def normalize(ranges):
    """排序并合并重叠 / 相邻的段。"""
    out = []
    for start, end in sorted(ranges):
        if end < start:
            start, end = end, start
        if out and start <= out[-1][1] + timedelta(days=1):
            if end > out[-1][1]:
                out[-1] = (out[-1][0], end)
        else:
            out.append((start, end))
    return out


def load_ranges():
    """读取手动假期段（已排序合并）。"""
    raw = storage.load_json(NAME, [])
    ranges = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            start = _parse(item.get("start"))
            end = _parse(item.get("end"))
            if start and end:
                ranges.append((start, end))
    return normalize(ranges)


def save_ranges(ranges):
    storage.save_json(NAME, [{"start": s.isoformat(), "end": e.isoformat()}
                             for s, e in normalize(ranges)])


def add_range(start, end):
    """新增假期段，返回合并后的全部段。"""
    if end < start:
        start, end = end, start
    ranges = normalize(load_ranges() + [(start, end)])
    save_ranges(ranges)
    return ranges


def intersect(start, end):
    """请求区间与已有假期段的交集（可能多段）。"""
    if end < start:
        start, end = end, start
    out = []
    for s, e in load_ranges():
        a, b = max(s, start), min(e, end)
        if a <= b:
            out.append((a, b))
    return out


def subtract(start, end, removed):
    """请求区间减去 removed 之后剩下的部分（用于提示「这些天本来不是假期」）。"""
    rest = []
    cur = start
    for s, e in removed:
        if s > cur:
            rest.append((cur, s - timedelta(days=1)))
        cur = max(cur, e + timedelta(days=1))
    if cur <= end:
        rest.append((cur, end))
    return rest


def remove_range(start, end):
    """删除 [start,end] 落在假期里的部分。

    返回 (removed, uncovered)：removed 是真正删掉的段，uncovered 是请求范围里
    本来就不是假期的部分（调用方用来提示"已忽略"）。
    """
    if end < start:
        start, end = end, start
    removed = intersect(start, end)
    if not removed:
        return [], [(start, end)]
    keep = []
    for s, e in load_ranges():
        pieces = [(s, e)]
        for rs, re_ in removed:
            nxt = []
            for ps, pe in pieces:
                if re_ < ps or rs > pe:
                    nxt.append((ps, pe))
                    continue
                if ps < rs:
                    nxt.append((ps, rs - timedelta(days=1)))
                if pe > re_:
                    nxt.append((re_ + timedelta(days=1), pe))
            pieces = nxt
        keep.extend(pieces)
    save_ranges(keep)
    return removed, subtract(start, end, removed)


def is_holiday(day, ranges=None):
    """这一天是否落在手动假期里。"""
    ranges = load_ranges() if ranges is None else ranges
    return any(s <= day <= e for s, e in ranges)


def clear_dates(days):
    """把若干具体日期从手动假期里挖掉（往假期里加课时用），返回被挖掉的日期。"""
    targets = {d for d in days if d}
    if not targets:
        return []
    keep, hit = [], []
    for s, e in load_ranges():
        cur, day = s, s
        while day <= e:
            if day in targets:
                hit.append(day)
                if cur <= day - timedelta(days=1):
                    keep.append((cur, day - timedelta(days=1)))
                cur = day + timedelta(days=1)
            day += timedelta(days=1)
        if cur <= e:
            keep.append((cur, e))
    if hit:
        save_ranges(keep)
    return sorted(hit)


def lesson_dates(lesson, start_date):
    """把课表条目（星期 + 周次）展开成具体日期。"""
    out = set()
    for wd in lesson.get("weekdays", []):
        for week in lesson.get("weeks", []):
            out.add(start_date + timedelta(days=(int(week) - 1) * 7 + (int(wd) - 1)))
    return sorted(out)


def busy_dates(cfg=None, lessons=None):
    """学期内「当天有课」的所有日期。"""
    cfg = cfg or storage.load_config()
    if not cfg:
        return set()
    start = _parse(cfg.get("start_date"))
    if not start:
        return set()
    lessons = storage.load_lessons() if lessons is None else lessons
    out = set()
    for lesson in lessons:
        out.update(lesson_dates(lesson, start))
    return out


def free_dates(cfg=None, lessons=None):
    """学期内「整天没课」的日期（自动假期，不落盘）。"""
    cfg = cfg or storage.load_config()
    if not cfg:
        return []
    start = _parse(cfg.get("start_date"))
    if not start:
        return []
    total = int(cfg.get("total_weeks") or 0)
    busy = busy_dates(cfg, lessons)
    out = []
    for week in range(1, total + 1):
        for wd in range(1, 8):
            day = start + timedelta(days=(week - 1) * 7 + (wd - 1))
            if day not in busy:
                out.append(day)
    return out


def is_day_off(day, cfg=None, lessons=None, ranges=None):
    """这一天该不该显示「今日假期」：落在手动假期里，或学期内整天没课。"""
    if is_holiday(day, ranges):
        return True
    cfg = cfg or storage.load_config()
    if not cfg:
        return False
    start = _parse(cfg.get("start_date"))
    if not start:
        return False
    total = int(cfg.get("total_weeks") or 0)
    week = storage.current_week(start, day)
    if week < 1 or week > total:
        return False
    lessons = storage.load_lessons() if lessons is None else lessons
    for lesson in lessons:
        if day.isoweekday() in lesson.get("weekdays", []) and week in lesson.get("weeks", []):
            return False
    return True
