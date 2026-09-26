"""样品受理业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "sample"
REQUIRED_FIELDS = ["样品编号", "样品名称", "样品类别"]
ENTRY_FIELDS = ["样品编号", "样品名称", "样品类别", "送检单位", "送检人", "接收日期", "保存条件"]
STATUS_ORDER = ["待受理", "已受理", "已分发", "已退回"]
PENDING_STATUSES = {"待受理", "已受理"}
ACTION_RULES = {"受理样品": "已受理", "分发检测": "已分发", "退回样品": "已退回"}
NEGATIVE_ACTIONS = ["退回样品"]


class SampleService:
    def __init__(self) -> None:
        self._normalize_rows()

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("样品编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def stats(self) -> list[dict[str, Any]]:
        """统计卡片与列表同源：待处理看 pending，分发量看状态，刷新后口径一致。"""
        rows = store.rows(MODULE)
        return [
            {"label": "今日受理样品", "value": len(rows)},
            {"label": "待受理样品", "value": sum(1 for row in rows if row.get("pending"))},
            {"label": "已分发样品", "value": sum(1 for row in rows if row.get("status") == "已分发")},
        ]

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str], str]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing, ""
        code = str(values.get("样品编号") or "").strip()
        rows = store.rows(MODULE)
        if any(str(row.get("样品编号") or "").strip() == code for row in rows):
            return None, [], f"样品编号 {code} 已登记，重复提交已被忽略"
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in ENTRY_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["abnormal"] = False
        self._sync_state(entry)
        rows.append(entry)
        return entry, [], ""

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"样品 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于样品受理可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        current = str(entry.get("status") or STATUS_ORDER[0])
        if current not in STATUS_ORDER:
            current = STATUS_ORDER[0]
        if STATUS_ORDER.index(target) < STATUS_ORDER.index(current):
            return None, f"样品当前状态为「{current}」，不能回退到「{target}」"
        entry["status"] = target
        entry["abnormal"] = bool(entry.get("abnormal")) or action in NEGATIVE_ACTIONS
        self._sync_state(entry)
        return entry, f"样品已{action}"

    @staticmethod
    def _sync_state(entry: dict[str, Any]) -> None:
        """状态、展示字段与待处理标记同源更新，列表、详情、卡片不再各说各话。"""
        status = str(entry.get("status") or STATUS_ORDER[0])
        entry["status"] = status
        entry["样品状态"] = status
        entry["pending"] = status in PENDING_STATUSES

    @classmethod
    def _normalize_rows(cls) -> None:
        """历史数据只重算派生字段（展示状态、待处理），不改写异常标记等既有事实。"""
        for row in store.rows(MODULE):
            cls._sync_state(row)
            row["abnormal"] = bool(row.get("abnormal"))
