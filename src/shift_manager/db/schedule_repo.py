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
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            created_at = datetime.now().isoformat()
            
            constraints_json = json.dumps([c.model_dump(mode='json') for c in constraints]) if constraints else None
            
            cursor.execute("""
                INSERT INTO schedule_versions 
                (company_id, schedule_type, start_date, end_date, assignments_json, 
                 constraints_json, score, parent_version_id, created_at, updated_at, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (company_id, schedule_type, self._date_to_str(start_date), self._date_to_str(end_date),
                  json.dumps(assignments), constraints_json, score, parent_version_id, created_at, created_at, created_by))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_active_schedule_version(self, company_id: str) -> Optional[Dict]:
        """Get the current active schedule version."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM schedule_versions 
                WHERE company_id = ? AND schedule_type = 'ACTIVE'
                ORDER BY created_at DESC LIMIT 1
            """, (company_id,))
            row = cursor.fetchone()
            if row:
                return {
                    'id': row[0], 'company_id': row[1], 'schedule_type': row[2],
                    'start_date': row[3], 'end_date': row[4],
                    'assignments_json': row[5], 'constraints_json': row[6],
                    'score': row[7], 'parent_version_id': row[8],
                    'created_at': row[9], 'updated_at': row[10], 'created_by': row[11],
                    'metadata_json': row[12]
                }
            return None
        finally:
            conn.close()

    def get_schedule_version_history(self, company_id: str, limit: int = 20) -> List[Dict]:
        """Get schedule version history."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM schedule_versions 
                WHERE company_id = ? 
                ORDER BY created_at DESC LIMIT ?
            """, (company_id, limit))
            return [{
                'id': row[0], 'company_id': row[1], 'schedule_type': row[2],
                'start_date': row[3], 'end_date': row[4],
                'assignments_json': row[5], 'constraints_json': row[6],
                'score': row[7], 'parent_version_id': row[8],
                'created_at': row[9], 'updated_at': row[10], 'created_by': row[11],
                'metadata_json': row[12]
            } for row in cursor.fetchall()]
        finally:
            conn.close()

    def update_schedule_assignments(self, version_id: int, assignments: Dict, timestamp: str = None):
        """Update the assignments for a schedule version."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            updated_at = timestamp or datetime.now().isoformat()
            cursor.execute("""
                UPDATE schedule_versions SET assignments_json = ?, updated_at = ?
                WHERE id = ?
            """, (json.dumps(assignments), updated_at, version_id))
            conn.commit()
        finally:
            conn.close()

    def archive_schedule_version(self, version_id: int):
        """Archive a schedule version."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            updated_at = datetime.now().isoformat()
            cursor.execute("""
                UPDATE schedule_versions SET schedule_type = 'ARCHIVED', updated_at = ?
                WHERE id = ?
            """, (updated_at, version_id))
            conn.commit()
        finally:
            conn.close()

    def publish_draft_version(self, draft_version_id: int) -> Optional[int]:
        """Publish a draft version as active (creates new active, archives old)."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            updated_at = datetime.now().isoformat()
            
            # Get draft details
            cursor.execute("SELECT company_id FROM schedule_versions WHERE id = ?", (draft_version_id,))
            row = cursor.fetchone()
            if not row:
                return None
            company_id = row[0]
            
            # Archive current active
            cursor.execute("""
                UPDATE schedule_versions SET schedule_type = 'ARCHIVED', updated_at = ?
                WHERE company_id = ? AND schedule_type = 'ACTIVE'
            """, (updated_at, company_id))
            
            # Update draft to active
            cursor.execute("""
                UPDATE schedule_versions SET schedule_type = 'ACTIVE', updated_at = ?
                WHERE id = ?
            """, (updated_at, draft_version_id))
            conn.commit()
            
            return draft_version_id
        finally:
            conn.close()
