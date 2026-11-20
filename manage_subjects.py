# -*- coding: utf-8 -*-
"""1. 管理课程（科目）：冻结窗口显示现有科目，支持新建 / 编辑 / 删除。"""
import palette
import storage


def show_subjects():
    subjects = storage.ensure_subject_colors()
    print("-- 现有科目 --")
    if not subjects:
        print("  （暂无科目）")
    else:
        for s in subjects:
            print("  [%3d] %-6s %s  %s" % (s["id"], s["short_name"], s["name"], s.get("color", "")))
    return subjects


def main():
    while True:
        subjects = show_subjects()
        print()
        print("[n] 新建科目    [e] 编辑科目    [d] 删除科目    [q] 返回")
        cmd = input("请选择：").strip().lower()
        if cmd == "q":
            break
        elif cmd == "n":
            add_subject(subjects)
        elif cmd == "e":
            edit_subject(subjects)
        elif cmd == "d":
            del_subject(subjects)
        else:
            print("[ERR] 无效选择")
        print()


def add_subject(subjects):
    name = input("科目全称：").strip()
    if not name:
        print("[ERR] 全称不能为空")
        return
    short = input("科目简称（回车默认用全称）：").strip() or name
    new_id = max((s["id"] for s in subjects), default=0) + 1
    subjects.append({"id": new_id, "name": name, "short_name": short})
    storage.save_subjects(subjects)
    subjects = storage.ensure_subject_colors()
    print("[OK] 已添加： [%d] %s  %s  %s" % (new_id, short, name, next((s.get("color", "") for s in subjects if s["id"] == new_id), "")))


def edit_subject(subjects):
    raw = input("要编辑的科目编号（直接回车返回）：").strip()
    if not raw:
        return
    if not raw.isdigit():
        print("[ERR] 编号无效")
        return
    sid = int(raw)
    sub = next((s for s in subjects if s["id"] == sid), None)
    if not sub:
        print("[ERR] 编号 %d 不存在" % sid)
        return
    print("当前：%s（%s）" % (sub["short_name"], sub["name"]))
    name = input("新全称（回车不变）：").strip()
    short = input("新简称（回车不变）：").strip()
    if name:
        sub["name"] = name
    if short:
        sub["short_name"] = short
    color = input("颜色（#RRGGBB，回车保持，auto=自动重排，当前 %s）：" % sub.get("color", "自动")).strip()
    if color:
        if color.lower() == "auto":
            sub.pop("color", None)
        elif palette.is_valid_color(color):
            sub["color"] = palette.normalize_color(color)
        else:
            print("[ERR] 颜色格式应为 #RRGGBB，保持原值")
    storage.save_subjects(subjects)
    storage.ensure_subject_colors()
    print("[OK] 已更新 [%d] %s（%s）" % (sid, sub["short_name"], sub["name"]))


def del_subject(subjects):
    raw = input("要删除的科目编号（直接回车返回）：").strip()
    if not raw:
        return
    if not raw.isdigit():
        print("[ERR] 编号无效")
        return
    sid = int(raw)
    sub = next((s for s in subjects if s["id"] == sid), None)
    if not sub:
        print("[ERR] 编号 %d 不存在" % sid)
        return
    lessons = storage.load_lessons()
    refs = [l for l in lessons if l["subject_id"] == sid]
    if refs:
        print("[WARN] 该科目被 %d 条课表条目引用，删除科目将同时删除这些条目" % len(refs))
    if input("确认删除 [%d] %s？(y/n)：" % (sid, sub["short_name"])).strip().lower() != "y":
        print("已取消")
        return
    subjects.remove(sub)
    storage.save_subjects(subjects)
    if refs:
        storage.save_lessons([l for l in lessons if l["subject_id"] != sid])
        print("[OK] 已删除科目及其 %d 条课表条目" % len(refs))
    else:
        print("[OK] 已删除 [%d] %s" % (sid, sub["short_name"]))


if __name__ == "__main__":
    main()
