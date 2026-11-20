# -*- coding: utf-8 -*-
"""4. 清除所有数据：删除所有课表来源（手动 + ICS）、学期配置、假期（新学期重置用）。"""
import os
import shutil

import sources
import storage


def main():
    data_dir = storage.DATA_DIR
    index = sources.load_index()
    targets = [data_dir / name for name in
               ("config.json", "subjects.json", "lessons.json", "holidays.json")]
    for sid, meta in index["sources"].items():
        if meta.get("kind") == "ics":
            targets.append(data_dir / "ics" / sid)
    print("== 清除所有数据 ==")
    print("将删除以下内容（不可恢复）：")
    for path in targets:
        status = "存在" if path.exists() else "（不存在）"
        try:
            label = path.relative_to(data_dir)
        except ValueError:
            label = path
        print("  - %s  %s" % (label, status))
    print()
    if input("输入 clear 确认清除，其他任意键取消：").strip().lower() != "clear":
        print("已取消")
        return
    removed = 0
    for path in targets:
        if not path.exists():
            continue
        try:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                os.remove(path)
            removed += 1
        except OSError as exc:
            print("[ERR] 删除 %s 失败：%s" % (path, exc))
    sources.reset_all()
    print("[OK] 已清除 %d 项数据，重新初始化后即可开始新学期" % removed)


if __name__ == "__main__":
    main()
