import sqlite3
import json
from datetime import datetime, date
from typing import List, Optional, Dict
from shift_manager.db.core import BaseRepository

class ScheduleRepository(BaseRepository):
    def create_schedule_version(self, company_id: str, schedule_type: str, 
                                start_date: date, end_date: date, 
                                assignments: Dict, constraints: List = None, 
                                score: float = None, parent_version_id: int = None,
                                created_by: str = "SYSTEM") -> int:
        """Create a new schedule version."""
        with self.connection() as conn:
            created_at = self._date_to_str(datetime.now())
            
            # Note: We assume constraints objects have a model_dump method if they are Pydantic models.
            # If not, we fall back to a safe representation.
            constraints_json = None
            if constraints:
                try:
                    constraints_json = json.dumps([c.model_dump(mode='json') for c in constraints])
                except AttributeError:
                    constraints_json = json.dumps(constraints)
            
            cursor = conn.execute("""
                INSERT INTO schedule_versions 
                (company_id, schedule_type, start_date, end_date, assignments_json, 
                 constraints_json, score, parent_version_id, created_at, updated_at, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (company_id, schedule_type, self._date_to_str(start_date), self._date_to_str(end_date),
                  json.dumps(assignments), constraints_json, score, parent_version_id, 
                  created_at, created_at, created_by))
            return cursor.lastrowid

    def get_active_schedule_version(self, company_id: str) -> Optional[Dict]:
        """Get the current active schedule version."""
        with self.connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM schedule_versions 
                WHERE company_id = ? AND schedule_type = 'ACTIVE'
                ORDER BY created_at DESC LIMIT 1
            """, (company_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def get_schedule_version_history(self, company_id: str, limit: int = 20) -> List[Dict]:
        """Get schedule version history."""
        with self.connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM schedule_versions 
                WHERE company_id = ? 
                ORDER BY created_at DESC LIMIT ?
            """, (company_id, limit))
            return [dict(row) for row in cursor.fetchall()]

    def update_schedule_assignments(self, version_id: int, assignments: Dict, timestamp: str = None):
        """Update the assignments for a schedule version."""
        with self.connection() as conn:
            updated_at = timestamp or self._date_to_str(datetime.now())
            conn.execute("""
                UPDATE schedule_versions SET assignments_json = ?, updated_at = ?
                WHERE id = ?
            """, (json.dumps(assignments), updated_at, version_id))

    def archive_schedule_version(self, version_id: int):
        """Archive a schedule version."""
        with self.connection() as conn:
            updated_at = self._date_to_str(datetime.now())
            conn.execute("""
                UPDATE schedule_versions SET schedule_type = 'ARCHIVED', updated_at = ?
                WHERE id = ?
            """, (updated_at, version_id))

    def publish_draft_version(self, draft_version_id: int) -> Optional[int]:
        """Publish a draft version as active (creates new active, archives old)."""
        with self.connection() as conn:
            updated_at = self._date_to_str(datetime.now())
            
            # Get draft details
            cursor = conn.execute("SELECT company_id FROM schedule_versions WHERE id = ?", (draft_version_id,))
            row = cursor.fetchone()
            if not row:
                return None
            company_id = row['company_id']
            
            # Archive current active
            conn.execute("""
                UPDATE schedule_versions SET schedule_type = 'ARCHIVED', updated_at = ?
                WHERE company_id = ? AND schedule_type = 'ACTIVE'
            """, (updated_at, company_id))
            
            # Update draft to active
            conn.execute("""
                UPDATE schedule_versions SET schedule_type = 'ACTIVE', updated_at = ?
                WHERE id = ?
            """, (updated_at, draft_version_id))
            
            return draft_version_id
