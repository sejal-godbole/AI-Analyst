"""
Schema snapshot caching and change detection.
Computes deterministic hash of database schema and detects table/column changes over time.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Optional
import uuid

from app.observability.models import SchemaChangeRecord


class SchemaTracker:
    def __init__(self):
        self._last_schema_hash: Optional[str] = None
        self._last_schema_data: Optional[dict] = None
        self._history: list[SchemaChangeRecord] = []

    def compute_hash(self, schema: dict) -> str:
        serialized = json.dumps(schema.get("tables", {}), sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]

    def record_and_diff(self, schema: dict) -> tuple[bool, Optional[SchemaChangeRecord]]:
        """
        Records the schema. Returns (is_changed, change_record).
        """
        current_hash = self.compute_hash(schema)
        tables = schema.get("tables", {})
        table_count = len(tables)
        col_count = sum(len(t.get("columns", {})) for t in tables.values())

        if self._last_schema_hash is None:
            # First snapshot
            self._last_schema_hash = current_hash
            self._last_schema_data = schema
            record = SchemaChangeRecord(
                snapshot_id=str(uuid.uuid4())[:8],
                created_at=datetime.now(timezone.utc).isoformat(),
                schema_hash=current_hash,
                table_count=table_count,
                column_count=col_count,
                diff_summary="Initial schema baseline captured.",
            )
            self._history.append(record)
            return False, record

        if current_hash == self._last_schema_hash:
            return False, None

        # Schema changed! Compute diff
        old_tables = self._last_schema_data.get("tables", {}) if self._last_schema_data else {}
        added_tables = set(tables.keys()) - set(old_tables.keys())
        removed_tables = set(old_tables.keys()) - set(tables.keys())
        modified_tables = []

        for tbl in set(tables.keys()) & set(old_tables.keys()):
            old_cols = set(old_tables[tbl].get("columns", {}).keys())
            new_cols = set(tables[tbl].get("columns", {}).keys())
            if old_cols != new_cols:
                modified_tables.append(f"{tbl} (cols: +{len(new_cols - old_cols)}, -{len(old_cols - new_cols)})")

        diff_parts = []
        if added_tables:
            diff_parts.append(f"Added tables: {', '.join(added_tables)}")
        if removed_tables:
            diff_parts.append(f"Removed tables: {', '.join(removed_tables)}")
        if modified_tables:
            diff_parts.append(f"Modified tables: {', '.join(modified_tables)}")

        diff_summary = "; ".join(diff_parts) if diff_parts else "Schema structure or constraints modified."

        record = SchemaChangeRecord(
            snapshot_id=str(uuid.uuid4())[:8],
            created_at=datetime.now(timezone.utc).isoformat(),
            schema_hash=current_hash,
            table_count=table_count,
            column_count=col_count,
            diff_summary=diff_summary,
        )
        self._last_schema_hash = current_hash
        self._last_schema_data = schema
        self._history.append(record)
        return True, record

    def get_history(self) -> list[SchemaChangeRecord]:
        return list(reversed(self._history))


# Global singleton instance
schema_tracker = SchemaTracker()
