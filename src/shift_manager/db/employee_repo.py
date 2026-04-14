import sqlite3
import json
from datetime import datetime
import datetime as dt_module
from typing import List, Optional, Dict
from shift_manager.models import Employee
from shift_manager.db.core import BaseRepository

class EmployeeRepository(BaseRepository):
    def create_employee(self, employee: Employee) -> Employee:
        """Create a new employee."""
        with self.connection() as conn:
            created_at = self._date_to_str(datetime.now())
            conn.execute("""
                INSERT OR REPLACE INTO employees 
                (id, company_id, team_id, name, max_dayoff_quota, max_leave_quota, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (employee.id, employee.company_id, employee.team_id, employee.name,
                  employee.max_dayoff_quota, employee.max_leave_quota, created_at))
            
        # Initialize quota usage for current year outside the main connection block to avoid nesting
        self._init_quota_usage(employee.id, employee.company_id)
        return employee

    def get_employees(self, company_id: str, team_id: Optional[str] = None) -> List[Employee]:
        """Get employees for a company, optionally filtered by team."""
        with self.connection() as conn:
            if team_id:
                cursor = conn.execute("SELECT * FROM employees WHERE company_id = ? AND team_id = ?", (company_id, team_id))
            else:
                cursor = conn.execute("SELECT * FROM employees WHERE company_id = ?", (company_id,))
            
            rows = cursor.fetchall()
            
        employees = []
        for row in rows:
            emp = Employee(
                id=row['id'], company_id=row['company_id'], team_id=row['team_id'], name=row['name'],
                max_dayoff_quota=row['max_dayoff_quota'], max_leave_quota=row['max_leave_quota']
            )
            # Get current state from quota_usage or state_log outside the main connection block
            quota = self.get_quota_usage(emp.id, company_id)
            if quota:
                emp.used_dayoff_quota = quota['dayoff_used']
                emp.used_leave_quota = quota['leave_used']
                emp.accumulated_hours = self._get_accumulated_hours(emp.id)
            employees.append(emp)
        return employees

    def delete_employee(self, employee_id: str):
        """Delete an employee."""
        with self.connection() as conn:
            conn.execute("DELETE FROM employees WHERE id = ?", (employee_id,))

    def _get_accumulated_hours(self, employee_id: str) -> float:
        """Get the latest accumulated hours from state log."""
        with self.connection() as conn:
            cursor = conn.execute("""
                SELECT accumulated_hours FROM employee_state_log 
                WHERE employee_id = ? ORDER BY recorded_at DESC LIMIT 1
            """, (employee_id,))
            row = cursor.fetchone()
            return row['accumulated_hours'] if row else 120.0  # Default starting hours

    def _init_quota_usage(self, employee_id: str, company_id: str, year: int = None):
        """Initialize quota usage record for an employee."""
        if year is None:
            year = datetime.now().year
        quarter = (datetime.now().month - 1) // 3 + 1
        
        with self.connection() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO quota_usage 
                (company_id, employee_id, year, quarter, dayoff_used, dayoff_max, leave_used, leave_max, last_updated)
                VALUES (?, ?, ?, ?, 0, 52, 0, 13, ?)
            """, (company_id, employee_id, year, quarter, self._date_to_str(datetime.now())))

    def get_quota_usage(self, employee_id: str, company_id: str, year: int = None) -> Optional[Dict]:
        """Get current quota usage for an employee."""
        if year is None:
            year = datetime.now().year
        
        with self.connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM quota_usage 
                WHERE employee_id = ? AND company_id = ? AND year = ?
            """, (employee_id, company_id, year))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def update_quota(self, employee_id: str, company_id: str, quota_type: str, delta: int = 1):
        """Update quota usage (increment or decrement)."""
        year = datetime.now().year
        self._init_quota_usage(employee_id, company_id, year)
        
        with self.connection() as conn:
            last_updated = self._date_to_str(datetime.now())
            if quota_type == "DAY_OFF":
                conn.execute("""
                    UPDATE quota_usage SET dayoff_used = dayoff_used + ?, last_updated = ?
                    WHERE employee_id = ? AND company_id = ? AND year = ?
                """, (delta, last_updated, employee_id, company_id, year))
            elif quota_type == "LEAVE":
                conn.execute("""
                    UPDATE quota_usage SET leave_used = leave_used + ?, last_updated = ?
                    WHERE employee_id = ? AND company_id = ? AND year = ?
                """, (delta, last_updated, employee_id, company_id, year))

    def log_employee_state(self, company_id: str, employee_id: str,
                          schedule_version_id: Optional[int],
                          accumulated_hours: float, used_dayoff: int, used_leave: int,
                          change_type: str, change_reason: str = None,
                          change_blocks: List[int] = None, hours_change: float = 0.0,
                          replacement_for_id: str = None, timestamp: str = None) -> int:
        """Log a change in employee state."""
        with self.connection() as conn:
            recorded_at = timestamp or self._date_to_str(datetime.now())
            if isinstance(recorded_at, (datetime, dt_module.date)):
                 recorded_at = self._date_to_str(recorded_at)

            cursor = conn.execute("""
                INSERT INTO employee_state_log 
                (company_id, employee_id, schedule_version_id, accumulated_hours, 
                 used_dayoff_quota, used_leave_quota, change_type, change_reason,
                 change_blocks, hours_change, replacement_for_id, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (company_id, employee_id, schedule_version_id, accumulated_hours,
                  used_dayoff, used_leave, change_type, change_reason,
                  json.dumps(change_blocks) if change_blocks else None,
                  hours_change, replacement_for_id, recorded_at))
            return cursor.lastrowid

    def get_employee_state_history(self, employee_id: str) -> List[Dict]:
        """Get history of state changes for an employee."""
        with self.connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM employee_state_log 
                WHERE employee_id = ? ORDER BY recorded_at DESC
            """, (employee_id,))
            
            rows = cursor.fetchall()
            
        history = []
        for row in rows:
            d = dict(row)
            if d['change_blocks']: d['change_blocks'] = json.loads(d['change_blocks'])
            history.append(d)
        return history
