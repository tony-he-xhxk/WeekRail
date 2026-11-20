# -*- coding: utf-8 -*-
"""课表来源管理：一份手动课表 + 任意多个 ICS 导入的课表，可随时切换。

目录约定：
- 全局文件：data/holidays.json、data/prefs.json、data/sources.json
- 手动课表：data/config.json、data/subjects.json、data/lessons.json（与旧版本兼容，无需迁移）
- ICS 课表：data/ics/<来源 id>/config.json|subjects.json|lessons.json
"""
import json
import re
import shutil
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
INDEX_NAME = "sources.json"
MANUAL_ID = "manual"


def _index_path():
    return DATA_DIR / INDEX_NAME


def load_index():
    """读取来源索引；没有时返回"只有手动课表"的默认结构。"""
    data = None
    path = _index_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None
    if not isinstance(data, dict):
        data = {}
    sources = data.get("sources")
    if not isinstance(sources, dict):
        sources = {}
    sources.setdefault(MANUAL_ID, {"kind": "manual", "label": "手动课表"})
    active = data.get("active")
    if active not in sources:
        active = MANUAL_ID
    return {"active": active, "sources": sources}


def save_index(index):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    sources = dict(index.get("sources") or {})
    sources.setdefault(MANUAL_ID, {"kind": "manual", "label": "手动课表"})
    active = index.get("active")
    if active not in sources:
        active = MANUAL_ID
    data = {"active": active, "sources": sources}
    _index_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def active_id():
    return load_index()["active"]


def set_active(source_id):
    index = load_index()
    if source_id not in index["sources"]:
        return False
    index["active"] = source_id
    save_index(index)
    return True


def source_dir(source_id):
    if source_id == MANUAL_ID:
        return DATA_DIR
    return DATA_DIR / "ics" / source_id


def active_dir():
    return source_dir(active_id())


def all_sources():
    """[(id, meta, 是否当前)]，手动课表排在最前。"""
    index = load_index()
    ids = sorted(index["sources"], key=lambda s: (s != MANUAL_ID, s))
    return [(sid, index["sources"][sid], sid == index["active"]) for sid in ids]


def has_ics_source():
    return any(meta.get("kind") == "ics" for meta in load_index()["sources"].values())


def new_ics_id(label, existing=()):
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", label).strip("-").lower() or "ics"
    slug = slug[:40]
    candidate = "ics-" + slug
    n = 2
    existing = set(existing)
    while candidate in existing:
        candidate = "ics-%s-%d" % (slug, n)
        n += 1
    return candidate


def add_source(source_id, meta):
    index = load_index()
    meta = dict(meta)
    meta.setdefault("kind", "ics")
    index["sources"][source_id] = meta
    save_index(index)
    return meta


def find_by_file(file_hint):
    """按 ICS 路径找已导入过的来源，返回 (id, meta) 或 (None, None)。"""
    if not file_hint:
        return None, None
    target = str(file_hint).replace("\\", "/").lower()
    for sid, meta in load_index()["sources"].items():
        if meta.get("kind") != "ics":
            continue
        if str(meta.get("file", "")).replace("\\", "/").lower() == target:
            return sid, meta
    return None, None


def remove_source(source_id):
    """删除一个 ICS 来源（数据目录 + 索引项）；手动来源不能删。"""
    if source_id == MANUAL_ID:
        return False
    index = load_index()
    if source_id not in index["sources"]:
        return False
    index["sources"].pop(source_id, None)
    if index["active"] == source_id:
        index["active"] = MANUAL_ID
    save_index(index)
    shutil.rmtree(DATA_DIR / "ics" / source_id, ignore_errors=True)
    return True


def reset_all():
    """清空所有来源的数据，只保留手动课表这个空壳。"""
    shutil.rmtree(DATA_DIR / "ics", ignore_errors=True)
    save_index({"active": MANUAL_ID, "sources": {}})
