import sqlite3
import json
from datetime import datetime, date
from typing import List, Optional, Dict
from shift_manager.db.core import BaseRepository

class LeaveRepository(BaseRepository):
    def save_dayoff_preference(self, company_id: str, schedule_version_id: Optional[int],
                              employee_id: str, date_obj: date, status: str = "PENDING") -> int:
        """Save a day-off preference."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            created_at = datetime.now().isoformat()
            
            cursor.execute("""
                INSERT OR REPLACE INTO dayoff_preferences 
                (company_id, schedule_version_id, employee_id, date, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (company_id, schedule_version_id, employee_id, self._date_to_str(date_obj), status, created_at))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def delete_dayoff_preference(self, company_id: str, employee_id: str, date_obj: date):
        """Delete a day-off preference."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM dayoff_preferences 
                WHERE company_id = ? AND employee_id = ? AND date = ?
            """, (company_id, employee_id, self._date_to_str(date_obj)))
            conn.commit()
        finally:
            conn.close()

    def get_dayoff_preferences(self, company_id: str, start_date: date, end_date: date,
                               schedule_version_id: int = None) -> List[Dict]:
        """Get day-off preferences for a date range."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            if schedule_version_id:
                cursor.execute("""
                    SELECT * FROM dayoff_preferences 
                    WHERE company_id = ? AND schedule_version_id = ? 
                    AND date BETWEEN ? AND ?
                """, (company_id, schedule_version_id, self._date_to_str(start_date), self._date_to_str(end_date)))
            else:
                cursor.execute("""
                    SELECT * FROM dayoff_preferences 
                    WHERE company_id = ? AND date BETWEEN ? AND ?
                """, (company_id, self._date_to_str(start_date), self._date_to_str(end_date)))
            return [{
                'id': row[0], 'company_id': row[1], 'schedule_version_id': row[2],
                'employee_id': row[3], 'date': row[4], 'status': row[5],
                'created_at': row[6], 'fulfilled_at': row[7]
            } for row in cursor.fetchall()]
        finally:
            conn.close()

    def save_leave_record(self, company_id: str, schedule_version_id: int,
                         employee_id: str, date_obj: date, shift_blocks: List[int],
                         hours_lost: float, replacement_id: str = None,
                         replacement_name: str = None, approved_by: str = "SYSTEM",
                         reason: str = None, event_timestamp: str = None) -> int:
        """Save a leave record."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            approved_at = datetime.now().isoformat()
            ts = event_timestamp or approved_at
            
            cursor.execute("""
                INSERT INTO leave_records 
                (company_id, schedule_version_id, employee_id, date, shift_blocks,
                 hours_lost, replacement_id, replacement_name, approved_at, event_timestamp, 
                 approved_by, reason, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'APPROVED')
            """, (company_id, schedule_version_id, employee_id, self._date_to_str(date_obj),
                  json.dumps(shift_blocks), hours_lost, replacement_id, replacement_name,
                  approved_at, ts, approved_by, reason))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_leave_records(self, company_id: str, start_date: date = None, end_date: date = None,
                          schedule_version_id: int = None) -> List[Dict]:
        """Get leave records for a date range or schedule version."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            
            if schedule_version_id:
                cursor.execute("""
                    SELECT * FROM leave_records 
                    WHERE company_id = ? AND schedule_version_id = ?
                    ORDER BY date ASC
                """, (company_id, schedule_version_id))
            elif start_date and end_date:
                cursor.execute("""
                    SELECT * FROM leave_records 
                    WHERE company_id = ? AND date BETWEEN ? AND ? AND status = 'APPROVED'
                    ORDER BY date ASC
                """, (company_id, self._date_to_str(start_date), self._date_to_str(end_date)))
            else:
                cursor.execute("""
                    SELECT * FROM leave_records 
                    WHERE company_id = ? AND status = 'APPROVED'
                    ORDER BY date DESC LIMIT 100
                """, (company_id,))
            
            records = []
            for row in cursor.fetchall():
                records.append({
                    'id': row[0], 'company_id': row[1], 'schedule_version_id': row[2],
                    'employee_id': row[3], 'date': row[4], 'shift_blocks': json.loads(row[5]),
                    'hours_lost': row[6], 'replacement_id': row[7], 'replacement_name': row[8],
                    'approved_at': row[9], 'event_timestamp': row[10], 'approved_by': row[11],
                    'reason': row[12], 'status': row[13]
                })
            return records
        finally:
            conn.close()

    def log_attendance(self, company_id: str, schedule_version_id: int,
                      employee_id: str, date_obj: date, shift_block: int,
                      hours_worked: float = 4.0, is_replacement: bool = False,
                      original_employee_id: str = None, leave_record_id: int = None) -> int:
        """Log an attendance record."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            recorded_at = datetime.now().isoformat()
            
            cursor.execute("""
                INSERT OR REPLACE INTO attendance_records 
                (company_id, schedule_version_id, employee_id, date, shift_block,
                 hours_worked, is_replacement, original_employee_id, leave_record_id, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (company_id, schedule_version_id, employee_id, self._date_to_str(date_obj),
                  shift_block, hours_worked, 1 if is_replacement else 0,
                  original_employee_id, leave_record_id, recorded_at))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def remove_attendance(self, company_id: str, schedule_version_id: int,
                         employee_id: str, date_obj: date, shift_block: int):
        """Remove an attendance record."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM attendance_records 
                WHERE company_id = ? AND schedule_version_id = ? 
                AND employee_id = ? AND date = ? AND shift_block = ?
            """, (company_id, schedule_version_id, employee_id, 
                  self._date_to_str(date_obj), shift_block))
            conn.commit()
        finally:
            conn.close()

    def get_attendance_summary(self, company_id: str, start_date: date, end_date: date) -> List[Dict]:
        """Get attendance summary grouped by employee."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT employee_id, 
                       SUM(hours_worked) as total_hours,
                       SUM(CASE WHEN is_replacement = 1 THEN hours_worked ELSE 0 END) as replacement_hours,
                       COUNT(*) as blocks_worked
                FROM attendance_records
                WHERE company_id = ? AND date BETWEEN ? AND ?
                GROUP BY employee_id
            """, (company_id, self._date_to_str(start_date), self._date_to_str(end_date)))
            return [{
                'employee_id': row[0], 'total_hours': row[1] or 0,
                'replacement_hours': row[2] or 0, 'blocks_worked': row[3]
            } for row in cursor.fetchall()]
        finally:
            conn.close()
