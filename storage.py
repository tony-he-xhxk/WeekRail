# -*- coding: utf-8 -*-
"""WeekRail 公共数据层：JSON 读写、范围解析、周次计算。"""
import json
from datetime import date
from pathlib import Path

import palette

DATA_DIR = Path(__file__).resolve().parent / "data"

WEEKDAY_CN = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六", 7: "周日"}


def load_json(name, default):
    path = DATA_DIR / name
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def save_json(name, data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / name
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _source_path(name):
    """当前来源的数据文件路径（手动=data/，ICS=data/ics/<id>/）。"""
    import sources
    return sources.active_dir() / name


def _load_source_json(name, default):
    path = _source_path(name)
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def _save_source_json(name, data):
    path = _source_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_config():
    return _load_source_json("config.json", None)


def save_config(cfg):
    _save_source_json("config.json", cfg)


def load_subjects():
    return _load_source_json("subjects.json", [])


def save_subjects(subjects):
    _save_source_json("subjects.json", subjects)


def load_lessons():
    return _load_source_json("lessons.json", [])


def save_lessons(lessons):
    _save_source_json("lessons.json", lessons)

DEFAULT_PREFS = {"opacity_normal": 80, "opacity_hover": 10,
                 "holiday_normal": 70, "holiday_hover": 10}


def _raw_prefs():
    """prefs.json 的原始内容（除不透明度外还放 last_date 之类的显示状态）。"""
    raw = load_json("prefs.json", None)
    return dict(raw) if isinstance(raw, dict) else {}


def load_prefs():
    """显示偏好：横条不透明度（0-100 的百分比）。"""
    raw = _raw_prefs()
    prefs = dict(DEFAULT_PREFS)
    for key in prefs:
        value = raw.get(key)
        if isinstance(value, (int, float)) and 0 <= value <= 100:
            prefs[key] = int(value)
    return prefs


def save_prefs(prefs):
    """保存显示偏好；非法值回落到默认，保留 last_date 等其它字段。"""
    data = _raw_prefs()
    for key, default in DEFAULT_PREFS.items():
        try:
            value = int(prefs.get(key, data.get(key, default)))
        except (TypeError, ValueError):
            value = default
        data[key] = max(0, min(100, value))
    save_json("prefs.json", data)
    return {key: data[key] for key in DEFAULT_PREFS}


def load_last_date():
    """上次 [3] / 托盘启动横条时输入的模拟日期。

    返回 (是否输入过, 日期文本)：
    - 从未输入过 -> (False, "")
    - 输入过但直接回车（= 今天）-> (True, "")
    - 输入过具体日期 -> (True, "YYYY-MM-DD")
    """
    raw = _raw_prefs()
    if "last_date" not in raw:
        return False, ""
    value = raw.get("last_date")
    if not isinstance(value, str):
        return False, ""
    value = value.strip()
    if value:
        try:
            date.fromisoformat(value)
        except ValueError:
            return False, ""
    return True, value


def save_last_date(text):
    """记住这次输入（空字符串表示「直接回车 = 今天」）。"""
    data = _raw_prefs()
    data["last_date"] = (text or "").strip()
    save_json("prefs.json", data)

def ensure_subject_colors():
    """给还没有颜色的科目分配颜色并落盘，返回科目列表。"""
    subjects = load_subjects()
    if palette.ensure_colors(subjects):
        save_subjects(subjects)
    return subjects


def parse_ranges(text, max_val, label):
    """解析范围文本 '1-2,6-7' 或 '5' -> 排序去重后的整数列表；失败返回 None。"""
    if text is None:
        return None
    text = text.strip()
    if not text:
        return None
    nums = set()
    try:
        for part in text.split(","):
            part = part.strip()
            if not part:
                return None
            if "-" in part:
                a, b = part.split("-", 1)
                a, b = int(a.strip()), int(b.strip())
                if a > b:
                    return None
                nums.update(range(a, b + 1))
            else:
                nums.add(int(part))
    except ValueError:
        return None
    if not nums:
        return None
    if any(n < 1 or n > max_val for n in nums):
        return None
    return sorted(nums)


def _fmt_run(a, b):
    """一段连续整数：正数用 1-3，负数用 -3~-1。"""
    if a == b:
        return str(a)
    if a < 0 or b < 0:
        return "%d~%d" % (a, b)
    return "%d-%d" % (a, b)


def fmt_ranges(nums):
    """整数列表 -> 紧凑范围文本：[1,2,3,6,7] -> '1-3,6-7'。"""
    if not nums:
        return ""
    nums = sorted(set(nums))
    parts = []
    start = prev = nums[0]
    for n in nums[1:]:
        if n == prev + 1:
            prev = n
            continue
        parts.append(_fmt_run(start, prev))
        start = prev = n
    parts.append(_fmt_run(start, prev))
    return ",".join(parts)


def current_week(start_date, today=None):
    """周次计算：开学日为第 1 周周一。today 默认今天。"""
    today = today or date.today()
    return (today - start_date).days // 7 + 1


def week_label(week):
    """显示用周次标签：不出现第 0 周，开学前紧邻的那一周显示为 -1。"""
    week = int(week)
    return week if week >= 1 else week - 1
