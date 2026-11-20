# -*- coding: utf-8 -*-
"""把 .ics 课表（BitUp 导出格式）转换成 WeekRail 的科目 / 课表条目。

流程：
1. 展开 ICS 折行，解析 VEVENT（SUMMARY / DTSTART / DTEND / DESCRIPTION）；
2. 时间从 UTC 转成本机时区，再按 period_times.json 的节次起止时间映射成节次；
3. 周次优先取 DESCRIPTION 里的「上课周次」，没有才按学期开始日推算；
4. 按 (科目, 星期, 节次) 合并周次，生成 subjects.json / lessons.json 的结构。
"""
import json
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
PERIOD_FILE = BASE / "period_times.json"
ICS_DIR = BASE / "课表ics"

DEFAULT_PERIODS = [
    (1, "08:00", "08:45"), (2, "08:50", "09:35"), (3, "09:55", "10:40"),
    (4, "10:45", "11:30"), (5, "11:35", "12:20"), (6, "13:20", "14:05"),
    (7, "14:10", "14:55"), (8, "15:15", "16:00"), (9, "16:05", "16:50"),
    (10, "16:55", "17:40"), (11, "18:30", "19:15"), (12, "19:20", "20:05"),
    (13, "20:10", "20:55"),
]


def _minutes(text):
    h, m = str(text).strip().split(":")
    return int(h) * 60 + int(m)


def load_period_table():
    """返回 [(节次, 开始分钟, 结束分钟)]；文件缺失/损坏时用内置的北理工表。"""
    data = None
    if PERIOD_FILE.exists():
        try:
            data = json.loads(PERIOD_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None
    rows = []
    if isinstance(data, dict):
        for item in data.get("periods", []):
            try:
                rows.append((int(item["index"]), _minutes(item["start"]), _minutes(item["end"])))
            except (KeyError, TypeError, ValueError):
                continue
    if not rows:
        rows = [(i, _minutes(s), _minutes(e)) for i, s, e in DEFAULT_PERIODS]
    return sorted(rows)


def overlap_minutes(a0, a1, b0, b1):
    return max(0, min(a1, b1) - max(a0, b0))


def map_periods(start, end, table):
    """事件时间段 -> (节次列表, 是否只能近似匹配)。

    某节课与事件重叠达到该节时长一半就算命中；一节都没命中时取重叠最多的一节并标记近似。
    """
    a0 = start.hour * 60 + start.minute
    a1 = end.hour * 60 + end.minute
    if a1 <= a0:
        a1 = a0 + 1
    hit, best, best_overlap = [], None, 0
    for index, b0, b1 in table:
        ov = overlap_minutes(a0, a1, b0, b1)
        if ov >= (b1 - b0) / 2:
            hit.append(index)
        if ov > best_overlap:
            best, best_overlap = index, ov
    if not hit and best is not None:
        return [best], True
    return hit, False


def _unfold(text):
    lines = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw.startswith((" ", "\t")) and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _unescape(value):
    return (value.replace("\\n", "\n").replace("\\N", "\n")
                 .replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\"))


def _parse_dt(value):
    value = str(value or "").strip()
    if not value:
        return None
    if value.endswith("Z"):
        try:
            return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    for fmt in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    try:
        return datetime.strptime(value, "%Y%m%d")
    except ValueError:
        return None


def parse_weeks(text):
    """'1' / '1-16' / '1,3,5' -> [1, 3, 5]；无法解析返回 []。"""
    out = set()
    for part in str(text or "").replace("，", ",").split(","):
        part = part.strip()
        m = re.fullmatch(r"(\d+)\s*[-–~]\s*(\d+)", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            out.update(range(a, b + 1))
        elif part.isdigit():
            out.add(int(part))
    return sorted(out)


def _read_text(path):
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def parse_ics(path):
    """解析 ICS，返回 (事件列表, 警告列表)。事件时间已转成本机时区。"""
    text = _read_text(path)
    lines = _unfold(text)
    raw_events, cur = [], None
    rrule_count = 0
    for line in lines:
        if line.strip() == "BEGIN:VEVENT":
            cur = {}
            continue
        if line.strip() == "END:VEVENT":
            if cur is not None:
                raw_events.append(cur)
            cur = None
            continue
        if cur is None or ":" not in line:
            continue
        key, value = line.split(":", 1)
        name = key.split(";", 1)[0].upper()
        if name == "RRULE":
            rrule_count += 1
        cur.setdefault(name, []).append(value)

    events, warnings = [], []
    for raw in raw_events:
        summary = _unescape((raw.get("SUMMARY") or [""])[0]).strip()
        start = _parse_dt((raw.get("DTSTART") or [""])[0])
        end = _parse_dt((raw.get("DTEND") or [""])[0])
        if not summary or not start or not end:
            warnings.append("跳过缺少 SUMMARY/DTSTART/DTEND 的事件")
            continue
        if start.tzinfo is not None:
            start = start.astimezone()
        if end.tzinfo is not None:
            end = end.astimezone()
        if end <= start:
            end = start + timedelta(minutes=45)
        if end.date() > start.date():
            end = datetime.combine(start.date(), datetime.strptime("23:59", "%H:%M").time())
        desc = _unescape("\n".join(raw.get("DESCRIPTION") or []))
        # 周次：BitUp 写成「上课周次: 5」，BIT101 写成「7周」/「1-16周」
        week_match = re.search(r"上课周次\s*[:：]\s*([0-9,，\-–~\s]+)", desc)
        if week_match:
            weeks = parse_weeks(week_match.group(1))
        else:
            week_match = re.search(r"(\d+(?:\s*[-–~]\s*\d+)?)\s*周", desc)
            weeks = parse_weeks(week_match.group(1)) if week_match else []
        # 教师：BitUp 有「授课教师:」，BIT101 是「范哲意,李东伟 | 7周 ...」
        teacher_match = re.search(r"授课教师\s*[:：]\s*([^\n]+)", desc)
        if teacher_match:
            teacher = teacher_match.group(1).strip()
        else:
            head = desc.split("|")[0].strip()
            teacher = head if head and "周" not in head and len(head) <= 40 else ""
        events.append({
            "summary": summary,
            "location": _unescape((raw.get("LOCATION") or [""])[0]).strip(),
            "teacher": teacher,
            "start": start,
            "end": end,
            "weeks": weeks,
        })
    if rrule_count:
        warnings.append("发现 %d 个 RRULE 重复规则：目前按单个事件导入（BitUp 导出的逐条事件不受影响）"
                        % rrule_count)
    return events, warnings


def derive_semester(events):
    """用「上课周次」反推第 1 周周一；返回 (start_date 或 None, 总周数, 无周次信息的事件数)。"""
    mondays = Counter()
    unknown = 0
    for ev in events:
        if not ev["weeks"]:
            unknown += 1
            continue
        day = ev["start"].date()
        for week in ev["weeks"]:
            mondays[day - timedelta(days=day.isoweekday() - 1) - timedelta(weeks=week - 1)] += 1
    if not mondays:
        return None, 0, unknown
    start = mondays.most_common(1)[0][0]
    total = max((max(ev["weeks"]) for ev in events if ev["weeks"]), default=0)
    for ev in events:
        if ev["weeks"]:
            continue
        total = max(total, (ev["start"].date() - start).days // 7 + 1)
    return start, total, unknown


def _auto_short(name, used):
    """给 ICS 里的全名生成一个 2-4 字的简称（之后可在 [1] 管理课程里改）。"""
    base = re.sub(r"（[^）]*）|\([^)]*\)", "", name)
    base = base.split("/")[0]
    base = re.sub(r"[\s\[\]【】]+", "", base)
    base = base or name
    short = base[:4]
    candidate, n = short, 2
    while candidate in used:
        candidate = (short[:3] + str(n))[:4]
        n += 1
    return candidate


def _week_of(start, day):
    return (day - start).days // 7 + 1


def analyze(path, week1=None):
    """解析 + 转换，不写盘。返回统计字典（含 subjects/lessons/config/warnings）。"""
    events, warnings = parse_ics(path)
    table = load_period_table()
    start, total, unknown = derive_semester(events)
    if start is None:
        if events:
            start = min(ev["start"].date() for ev in events)
            start -= timedelta(days=start.isoweekday() - 1)
        else:
            start = date.today()
    if total <= 0:
        total = 20

    names = sorted({ev["summary"] for ev in events})
    used, subjects, id_of = set(), [], {}
    for i, name in enumerate(names, 1):
        short = _auto_short(name, used)
        used.add(short)
        id_of[name] = i
        subjects.append({"id": i, "name": name, "short_name": short})

    entries, approx = {}, 0
    for ev in events:
        periods, is_approx = map_periods(ev["start"].time(), ev["end"].time(), table)
        if is_approx:
            approx += 1
            warnings.append("时间只能近似匹配：%s %s-%s -> 第%s节"
                            % (ev["summary"], ev["start"].strftime("%H:%M"),
                               ev["end"].strftime("%H:%M"), periods))
        if not periods:
            warnings.append("无法匹配任何节次，已跳过：%s %s-%s"
                            % (ev["summary"], ev["start"].strftime("%H:%M"),
                               ev["end"].strftime("%H:%M")))
            continue
        weeks = ev["weeks"] or [_week_of(start, ev["start"].date())]
        weeks = [w for w in weeks if 1 <= w <= total]
        if not weeks:
            continue
        key = (id_of[ev["summary"]], ev["start"].isoweekday(), tuple(periods))
        entries.setdefault(key, set()).update(weeks)

    lessons = []
    for (sid, weekday, periods), weeks in sorted(entries.items()):
        lessons.append({"subject_id": sid, "weekdays": [weekday],
                        "periods": list(periods), "weeks": sorted(weeks)})
    if week1 is not None:
        week1 = week1 if isinstance(week1, date) else date.fromisoformat(str(week1))
        delta = (week1 - start).days // 7
        start = week1
        total = max(1, total - delta)
        for lesson in lessons:
            lesson["weeks"] = [w - delta for w in lesson["weeks"]]
    return {
        "events": len(events),
        "subjects": subjects,
        "lessons": lessons,
        "config": {"start_date": start.isoformat(), "total_weeks": total},
        "warnings": warnings,
        "approx": approx,
        "unknown_weeks": unknown,
    }


def import_ics(path, source_id, label=None, week1=None):
    """把 ICS 写成 data/ics/<source_id>/ 下的三个 JSON，并在 sources.json 登记。"""
    import sources

    stats = analyze(path, week1=week1)
    target = sources.source_dir(source_id)
    target.mkdir(parents=True, exist_ok=True)
    for name, data in (("config.json", stats["config"]),
                       ("subjects.json", stats["subjects"]),
                       ("lessons.json", stats["lessons"])):
        (target / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    sources.add_source(source_id, {
        "kind": "ics",
        "label": label or Path(path).stem,
        "file": file_hint(path),
        "imported": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "start_date": stats["config"]["start_date"],
        "total_weeks": stats["config"]["total_weeks"],
    })
    return stats


def file_hint(path):
    """ICS 路径在项目内的相对写法（便于 sources.json 可移植）。"""
    try:
        return str(Path(path).resolve().relative_to(BASE))
    except ValueError:
        return str(path)
