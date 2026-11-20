# -*- coding: utf-8 -*-
"""8. 课表来源：导入 ICS、切换「手动 / ICS」课表、查看与删除 ICS 来源。"""
import json
from datetime import date
from pathlib import Path

import ics_import
import sources
import storage


def _ics_files():
    if not ics_import.ICS_DIR.exists():
        return []
    return sorted(ics_import.ICS_DIR.glob("*.ics"))


def _ask_file():
    files = _ics_files()
    if not files:
        folder = ics_import.ICS_DIR
        created = False
        if not folder.exists():
            try:
                folder.mkdir(parents=True, exist_ok=True)
                created = True
            except OSError as exc:
                print("[ERR] 无法创建 ICS 文件夹：%s" % exc)
                print("      请手动创建这个文件夹后重试：")
                print("        %s" % folder)
                return None
        print("[ERR] 没有找到任何 .ics 文件。")
        print("      %s：" % ("已自动创建文件夹，请把 ICS 文件放进去" if created
                              else "请把 ICS 文件放到这个文件夹"))
        print("        %s" % folder)
        print("      放好后重新进入 [8] → i。")
        return None
    print("-- ICS 文件目录：%s --" % ics_import.ICS_DIR)
    for i, path in enumerate(files, 1):
        print("  [%d] %s" % (i, path.name))
    raw = input("选择文件编号（回车取消，也可直接输入 .ics 路径）：").strip()
    if not raw:
        return None
    if raw.isdigit() and 1 <= int(raw) <= len(files):
        return files[int(raw) - 1]
    path = Path(raw.strip('"'))
    if not path.exists():
        print("[ERR] 文件不存在：%s" % path)
        return None
    return path


def _print_stats(stats, name):
    cfg = stats["config"]
    print("  文件：%s" % name)
    print("  事件 %d 个 -> 科目 %d 门，课表条目 %d 条"
          % (stats["events"], len(stats["subjects"]), len(stats["lessons"])))
    print("  学期：%s 开学，共 %d 周（由 ICS 的「上课周次」推算）"
          % (cfg["start_date"], cfg["total_weeks"]))
    print("  科目简称（可在 [1] 管理课程 里改）：%s"
          % "、".join("%s→%s" % (s["name"], s["short_name"]) for s in stats["subjects"][:8])
          + ("…" if len(stats["subjects"]) > 8 else ""))
    for line in stats["warnings"][:8]:
        print("  [WARN] " + line)
    neg = sorted({w for lesson in stats["lessons"] for w in lesson["weeks"] if w <= 0})
    if neg:
        print("  开学前周次：%s（会显示为第%s周）"
              % (storage.fmt_ranges(neg),
                 "、".join(str(storage.week_label(w)) for w in neg)))


def _ask_week1(stats):
    """询问是否重定义第 1 周；非周一直接拒绝并重问。返回新的 date 或 None。"""
    if input("要把第 1 周重定义为其他日期吗？(y/n，直接回车 = 不重定义)：").strip().lower() != "y":
        return None
    print("  当前第 1 周：%s（由 ICS 推算）" % stats["config"]["start_date"])
    while True:
        raw = input("  新的第 1 周日期（必须是周一，YYYY-MM-DD；回车取消）：").strip()
        if not raw:
            return None
        try:
            day = date.fromisoformat(raw)
        except ValueError:
            print("  [ERR] 日期格式应为 YYYY-MM-DD")
            continue
        if day.weekday() != 0:
            print("  [ERR] %s 不是周一，已拒绝重定义。" % day.isoformat())
            continue
        return day


def _edit_short_names(source_id):
    """导入后逐门确认横条上的简称；直接回车保持自动生成的名字。"""
    path = sources.source_dir(source_id) / "subjects.json"
    if not path.exists():
        return
    try:
        subjects = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not subjects:
        return
    print()
    print("-- 设置横条上的课程简称（共 %d 门；直接回车保持自动生成的）--" % len(subjects))
    used = set()
    for i, sub in enumerate(subjects, 1):
        current = sub.get("short_name", "")
        raw = input("  [%2d/%d] %-30s 简称（%s）："
                    % (i, len(subjects), sub.get("name", ""), current)).strip()
        if raw:
            if len(raw) > 6:
                print("       [WARN] 简称较长，横条上可能显示不全")
            if raw in used:
                print("       [WARN] 与前面的简称重复")
            sub["short_name"] = raw
        used.add(sub["short_name"])
    path.write_text(json.dumps(subjects, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[OK] 简称已保存：%s" % "、".join(s["short_name"] for s in subjects))


def import_flow(first_run=False):
    """导入一份 ICS；成功返回 True。first_run=True 时自动切换过去。"""
    path = _ask_file()
    if path is None:
        return False
    try:
        stats = ics_import.analyze(path)
    except Exception as exc:
        print("[ERR] 解析失败：%s" % exc)
        return False
    _print_stats(stats, path.name)
    if not stats["lessons"]:
        print("[ERR] 没有解析出任何课表条目，未导入。")
        return False
    week1 = _ask_week1(stats)
    if week1 is not None:
        stats = ics_import.analyze(path, week1=week1)
        print("[INFO] 已重定义第 1 周：%s（共 %d 周）"
              % (stats["config"]["start_date"], stats["config"]["total_weeks"]))
        _print_stats(stats, path.name)
    if input("确认导入这份 ICS 吗？(y/n)：").strip().lower() != "y":
        print("已取消")
        return False

    hint = ics_import.file_hint(path)
    existing_id, meta = sources.find_by_file(hint)
    if existing_id:
        if input("这份 ICS 已经导入过（%s）。重新导入会重新解析 ICS，覆盖该来源里你改过的"
                 "课表、简称和颜色，继续吗？(y/n)："
                 % meta.get("label", existing_id)).strip().lower() != "y":
            print("已取消")
            return False
        source_id = existing_id
    else:
        source_id = sources.new_ics_id(path.stem, [s[0] for s in sources.all_sources()])
    try:
        ics_import.import_ics(path, source_id, label=path.stem, week1=week1)
    except Exception as exc:
        print("[ERR] 写入失败：%s" % exc)
        return False
    _edit_short_names(source_id)
    if first_run or input("现在切换到这个课表吗？(y/n)：").strip().lower() == "y":
        sources.set_active(source_id)
        print("[OK] 已导入并切换：%s" % path.stem)
    else:
        print("[OK] 已导入；可稍后在 [8] 里切换。")
    return True


def switch_flow():
    items = sources.all_sources()
    print("-- 课表来源 --")
    for i, (sid, meta, active) in enumerate(items, 1):
        kind = "手动" if meta.get("kind") == "manual" else "ICS"
        print("  [%d] %-4s %s%s" % (i, kind, meta.get("label", sid), "  （当前）" if active else ""))
    raw = input("切换到哪个来源编号？（回车取消）：").strip()
    if not raw.isdigit() or not 1 <= int(raw) <= len(items):
        return False
    sid, meta, active = items[int(raw) - 1]
    if active:
        print("[INFO] 已经是当前来源。")
        return False
    sources.set_active(sid)
    print("[OK] 已切换到：%s" % meta.get("label", sid))
    return True


def list_flow():
    for i, (sid, meta, active) in enumerate(sources.all_sources(), 1):
        kind = "手动" if meta.get("kind") == "manual" else "ICS"
        print("  [%d] %-4s %s%s" % (i, kind, meta.get("label", sid), "  （当前）" if active else ""))
        if meta.get("kind") == "ics":
            print("       文件：%s" % meta.get("file", "-"))
            print("       导入：%s    学期：%s 起，共 %s 周"
                  % (meta.get("imported", "-"), meta.get("start_date", "-"),
                     meta.get("total_weeks", "-")))


def delete_flow():
    items = [(sid, meta, active) for sid, meta, active in sources.all_sources()
             if meta.get("kind") == "ics"]
    if not items:
        print("[INFO] 没有可删除的 ICS 来源。")
        return False
    print("-- 可删除的 ICS 来源 --")
    for i, (sid, meta, active) in enumerate(items, 1):
        print("  [%d] %s%s" % (i, meta.get("label", sid), "  （当前）" if active else ""))
    raw = input("删除哪个来源编号？（回车取消）：").strip()
    if not raw.isdigit() or not 1 <= int(raw) <= len(items):
        return False
    sid, meta, active = items[int(raw) - 1]
    if input("确认删除「%s」？只会删掉导入的数据，不会动原始 .ics 文件。(y/n)："
             % meta.get("label", sid)).strip().lower() != "y":
        print("已取消")
        return False
    sources.remove_source(sid)
    print("[OK] 已删除来源：%s" % meta.get("label", sid))
    return active


def main():
    """返回 True 表示当前来源变了（launcher 据此重启横条）。"""
    changed = False
    while True:
        print()
        print("[i] 导入 / 重新导入 ICS    [s] 切换课表来源    [l] 查看来源"
              "    [d] 删除 ICS 来源    [q] 返回")
        cmd = input("请选择：").strip().lower()
        if cmd == "q":
            break
        elif cmd in ("i", "a"):
            changed = import_flow() or changed
        elif cmd == "s":
            changed = switch_flow() or changed
        elif cmd == "l":
            list_flow()
        elif cmd == "d":
            changed = delete_flow() or changed
        else:
            print("[ERR] 无效选择")
    return changed
