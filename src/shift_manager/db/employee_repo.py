import sqlite3
import json
from datetime import datetime
from typing import List, Optional, Dict
from shift_manager.models import Employee
from shift_manager.db.core import BaseRepository

class EmployeeRepository(BaseRepository):
    def create_employee(self, employee: Employee) -> Employee:
        """Create a new employee."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            created_at = datetime.now().isoformat()
            cursor.execute("""
                INSERT OR REPLACE INTO employees 
                (id, company_id, team_id, name, max_dayoff_quota, max_leave_quota, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (employee.id, employee.company_id, employee.team_id, employee.name,
                  employee.max_dayoff_quota, employee.max_leave_quota, created_at))
            conn.commit()
            
            # Initialize quota usage for current year
            self._init_quota_usage(employee.id, employee.company_id)
            return employee
        finally:
            conn.close()

    def get_employees(self, company_id: str, team_id: Optional[str] = None) -> List[Employee]:
        """Get employees for a company, optionally filtered by team."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            if team_id:
                cursor.execute("SELECT * FROM employees WHERE company_id = ? AND team_id = ?", (company_id, team_id))
            else:
                cursor.execute("SELECT * FROM employees WHERE company_id = ?", (company_id,))
            
            employees = []
            for row in cursor.fetchall():
                emp = Employee(
                    id=row[0], company_id=row[1], team_id=row[2], name=row[3],
                    max_dayoff_quota=row[4], max_leave_quota=row[5]
                )
                # Get current state from quota_usage or state_log
                quota = self.get_quota_usage(emp.id, company_id)
                if quota:
                    emp.used_dayoff_quota = quota['dayoff_used']
                    emp.used_leave_quota = quota['leave_used']
                    emp.accumulated_hours = self._get_accumulated_hours(emp.id)
                employees.append(emp)
            return employees
        finally:
            conn.close()

    def delete_employee(self, employee_id: str):
        """Delete an employee."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM employees WHERE id = ?", (employee_id,))
            conn.commit()
        finally:
            conn.close()

    def _get_accumulated_hours(self, employee_id: str) -> float:
        """Get the latest accumulated hours from state log."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT accumulated_hours FROM employee_state_log 
                WHERE employee_id = ? ORDER BY recorded_at DESC LIMIT 1
            """, (employee_id,))
            row = cursor.fetchone()
            return row[0] if row else 120.0  # Default starting hours
        finally:
            conn.close()

    def _init_quota_usage(self, employee_id: str, company_id: str, year: int = None):
        """Initialize quota usage record for an employee."""
        if year is None:
            year = datetime.now().year
        quarter = (datetime.now().month - 1) // 3 + 1
        
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO quota_usage 
                (company_id, employee_id, year, quarter, dayoff_used, dayoff_max, leave_used, leave_max, last_updated)
                VALUES (?, ?, ?, ?, 0, 52, 0, 13, ?)
            """, (company_id, employee_id, year, quarter, datetime.now().isoformat()))
            conn.commit()
        finally:
            conn.close()

    def get_quota_usage(self, employee_id: str, company_id: str, year: int = None) -> Optional[Dict]:
        """Get current quota usage for an employee."""
        if year is None:
            year = datetime.now().year
        
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM quota_usage 
                WHERE employee_id = ? AND company_id = ? AND year = ?
            """, (employee_id, company_id, year))
            row = cursor.fetchone()
            if row:
                return {
                    'company_id': row[1], 'employee_id': row[2], 'year': row[3], 'quarter': row[4],
                    'dayoff_used': row[5], 'dayoff_max': row[6], 'leave_used': row[7], 'leave_max': row[8]
                }
            return None
        finally:
            conn.close()

    def update_quota(self, employee_id: str, company_id: str, quota_type: str, delta: int = 1):
        """Update quota usage (increment or decrement)."""
        year = datetime.now().year
        self._init_quota_usage(employee_id, company_id, year)
        
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            if quota_type == "DAY_OFF":
                cursor.execute("""
                    UPDATE quota_usage SET dayoff_used = dayoff_used + ?, last_updated = ?
                    WHERE employee_id = ? AND company_id = ? AND year = ?
                """, (delta, datetime.now().isoformat(), employee_id, company_id, year))
            elif quota_type == "LEAVE":
                cursor.execute("""
                    UPDATE quota_usage SET leave_used = leave_used + ?, last_updated = ?
                    WHERE employee_id = ? AND company_id = ? AND year = ?
                """, (delta, datetime.now().isoformat(), employee_id, company_id, year))
            conn.commit()
        finally:
            conn.close()

    def log_employee_state(self, company_id: str, employee_id: str,
                          schedule_version_id: Optional[int],
                          accumulated_hours: float, used_dayoff: int, used_leave: int,
                          change_type: str, change_reason: str = None,
                          change_blocks: List[int] = None, hours_change: float = 0.0,
                          replacement_for_id: str = None, timestamp: str = None) -> int:
        """Log a change in employee state."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            recorded_at = timestamp or datetime.now().isoformat()
            
            cursor.execute("""
                INSERT INTO employee_state_log 
                (company_id, employee_id, schedule_version_id, accumulated_hours, 
                 used_dayoff_quota, used_leave_quota, change_type, change_reason,
                 change_blocks, hours_change, replacement_for_id, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (company_id, employee_id, schedule_version_id, accumulated_hours,
                  used_dayoff, used_leave, change_type, change_reason,
                  json.dumps(change_blocks) if change_blocks else None,
                  hours_change, replacement_for_id, recorded_at))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_employee_state_history(self, employee_id: str) -> List[Dict]:
        """Get history of state changes for an employee."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM employee_state_log 
                WHERE employee_id = ? ORDER BY recorded_at DESC
            """, (employee_id,))
            
            history = []
            for row in cursor.fetchall():
                history.append({
                    'id': row[0], 'company_id': row[1], 'employee_id': row[2],
                    'schedule_version_id': row[3], 'accumulated_hours': row[4],
                    'used_dayoff': row[5], 'used_leave': row[6],
                    'change_type': row[7], 'change_reason': row[8],
                    'change_blocks': json.loads(row[9]) if row[9] else None,
                    'hours_change': row[10], 'replacement_for_id': row[11], 'recorded_at': row[12]
                })
            return history
        finally:
            conn.close()
