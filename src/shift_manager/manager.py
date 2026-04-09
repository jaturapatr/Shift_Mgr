import json
import os
import shutil
from datetime import date, timedelta, datetime
from typing import List, Optional, Dict

from shift_manager.models import Employee, ContextRule, MachineConstraint, Company, Team
from shift_manager.db.company_repo import CompanyRepository
from shift_manager.db.employee_repo import EmployeeRepository
from shift_manager.db.schedule_repo import ScheduleRepository
from shift_manager.db.leave_repo import LeaveRepository

class BusinessManager:
    def __init__(self, db_path: str = "roster_memory.db",
                 context_path: str = "business_context.json",
                 constraint_path: str = "constraints.json"):
        # Initialize repositories
        self.company_repo = CompanyRepository(db_path)
        self.employee_repo = EmployeeRepository(db_path)
        self.schedule_repo = ScheduleRepository(db_path)
        self.leave_repo = LeaveRepository(db_path)
        
        # Backward compatibility alias
        self.db = self # Let self act as the delegate for old db.* calls if needed, 
                       # but better to update the calls.
        
        # Initialize schema once
        self.company_repo._init_schema()
        
        self.context_path = context_path
        self.constraint_path = constraint_path
        self._initialize_default_data()

    def _initialize_default_data(self):
        """Initialize default company, teams, and employees if none exist."""
        companies = self.company_repo.get_all_companies()
        if not companies:
            # Create default company
            default_company = Company(
                id="COMP_01",
                name="Gas Station A",
                natural_language_context="Operate 24/7"
            )
            self.company_repo.create_company(default_company)

            # Create default teams
            team_c = Team(id="TEAM_CASHIER", company_id=default_company.id, name="CASHIER")
            team_s = Team(id="TEAM_SERVICE", company_id=default_company.id, name="SERVICE")
            self.company_repo.create_team(team_c)
            self.company_repo.create_team(team_s)

            # Create default employees
            employees = (
                [Employee(id=f"EMP_{i:02}", company_id=default_company.id, team_id=team_c.id,
                          name=f"Cashier {chr(64+i)}", accumulated_hours=120)
                 for i in range(1, 4)] +
                [Employee(id=f"EMP_{i:02}", company_id=default_company.id, team_id=team_s.id,
                          name=f"Service {chr(64+i-3)}", accumulated_hours=110)
                 for i in range(4, 13)]
            )
            for e in employees:
                self.employee_repo.create_employee(e)
                # Log initial state
                self.employee_repo.log_employee_state(
                    company_id=default_company.id,
                    employee_id=e.id,
                    schedule_version_id=None,
                    accumulated_hours=e.accumulated_hours,
                    used_dayoff=0, used_leave=0,
                    change_type="INITIAL",
                    change_reason="System initialization"
                )

    def reset_to_defaults(self):
        """
        Restores constraints from backup and clears all roster operational data.
        """
        # 1. Restore JSONs from backup
        backups = {
            "default_constraints.json": self.constraint_path,
            "default_business_context.json": self.context_path
        }
        for src, dst in backups.items():
            if os.path.exists(src):
                shutil.copy(src, dst)
        
        # 2. Clear Database Operational Data
        import sqlite3
        conn = sqlite3.connect(self.schedule_repo.db_path)
        try:
            cursor = conn.cursor()
            tables = [
                "schedule_versions", "employee_state_log", "dayoff_preferences",
                "leave_records", "attendance_records", "quota_usage"
            ]
            for table in tables:
                cursor.execute(f"DELETE FROM {table}")
            
            # Reset auto-increments
            cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('schedule_versions', 'employee_state_log', 'dayoff_preferences', 'leave_records', 'attendance_records', 'quota_usage')")
            conn.commit()
        finally:
            conn.close()

    def export_operational_data(self, company_id: str) -> str:
        """
        Exports all data (Master + Operational) for a company to a JSON string.
        """
        import sqlite3
        conn = sqlite3.connect(self.schedule_repo.db_path)
        try:
            cursor = conn.cursor()
            data = {
                "metadata": {"company_id": company_id, "exported_at": datetime.now().isoformat(), "version": "2.0"},
                "tables": {}
            }
            # All relevant tables for a full backup
            tables = [
                "teams", "employees", "schedule_versions", "employee_state_log", 
                "dayoff_preferences", "leave_records", "attendance_records", "quota_usage"
            ]
            for table in tables:
                cursor.execute(f"SELECT * FROM {table} WHERE company_id = ?", (company_id,))
                columns = [description[0] for description in cursor.description]
                data["tables"][table] = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            return json.dumps(data, indent=4)
        finally:
            conn.close()

    def import_operational_data(self, company_id: str, json_content: str):
        """
        Clears current data and restores from provided JSON content.
        """
        import sqlite3
        data = json.loads(json_content)
        if data.get("metadata", {}).get("company_id") != company_id:
            raise ValueError("Import file company_id mismatch.")

        conn = sqlite3.connect(self.schedule_repo.db_path)
        try:
            cursor = conn.cursor()
            # 1. Clear existing (Master + Operational)
            tables = [
                "quota_usage", "attendance_records", "leave_records", "dayoff_preferences",
                "employee_state_log", "schedule_versions", "employees", "teams"
            ]
            for table in tables:
                cursor.execute(f"DELETE FROM {table} WHERE company_id = ?", (company_id,))
            
            # 2. Insert new
            # Order matters for foreign keys: teams -> employees -> others
            import_order = [
                "teams", "employees", "schedule_versions", "employee_state_log", 
                "dayoff_preferences", "leave_records", "attendance_records", "quota_usage"
            ]
            
            for table in import_order:
                rows = data.get("tables", {}).get(table, [])
                if not rows: continue
                columns = list(rows[0].keys())
                placeholders = ", ".join(["?"] * len(columns))
                sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
                for row in rows:
                    cursor.execute(sql, tuple(row.values()))
            
            conn.commit()
        finally:
            conn.close()

    # ============================================
    # DELEGATED OPERATIONS
    # ============================================

    def get_companies(self) -> List[Company]:
        return self.company_repo.get_all_companies()

    def create_company(self, name: str, natural_language_context: str = "Operate 24/7") -> Company:
        company_id = f"COMP_{len(self.get_companies()) + 1:02d}"
        company = Company(id=company_id, name=name, natural_language_context=natural_language_context)
        self.company_repo.create_company(company)
        # Default rules
        rules = [
            ContextRule(id="POL_01", company_id=company_id, natural_language="Operate 24/7"),
            ContextRule(id="POL_02", company_id=company_id, natural_language="Every employee must have at least 1 day-off per week"),
            ContextRule(id="POL_03", company_id=company_id, natural_language="Employee must have rest period over 8 hrs a day"),
            ContextRule(id="POL_04", company_id=company_id, natural_language="We allow OT but we're not prefer OT")
        ]
        self.save_context(rules)
        return company

    def get_teams(self, company_id: str) -> List[Team]:
        return self.company_repo.get_teams(company_id)

    def create_team(self, company_id: str, name: str) -> Team:
        existing_teams = self.get_teams(company_id)
        team_id = f"TEAM_{company_id}_{len(existing_teams) + 1:02d}"
        team = Team(id=team_id, company_id=company_id, name=name)
        return self.company_repo.create_team(team)

    def delete_team(self, team_id: str):
        self.company_repo.delete_team(team_id)

    def load_employees(self, company_id: str, team_id: Optional[str] = None) -> List[Employee]:
        return self.employee_repo.get_employees(company_id, team_id)

    def remove_employee(self, employee_id: str):
        self.employee_repo.delete_employee(employee_id)

    def get_employee_state_history(self, employee_id: str) -> List[Dict]:
        return self.employee_repo.get_employee_state_history(employee_id)

    def update_quota(self, employee_id: str, company_id: str, quota_type: str, delta: int = 1):
        self.employee_repo.update_quota(employee_id, company_id, quota_type, delta)

    # ============================================
    # CONTEXT & CONSTRAINTS
    # ============================================

    def load_context(self, company_id: str) -> List[ContextRule]:
        rules = []
        if os.path.exists(self.context_path):
            try:
                with open(self.context_path, "r") as f:
                    content = f.read().strip()
                    if content:
                        data = json.loads(content)
                        all_rules = [ContextRule(**p) for p in data]
                        rules = [r for r in all_rules if r.company_id == company_id]
            except: pass
        if not rules:
            rules = [
                ContextRule(id="POL_01", company_id=company_id, natural_language="Operate 24/7"),
                ContextRule(id="POL_02", company_id=company_id, natural_language="Every employee must have at least 1 day-off per week"),
                ContextRule(id="POL_03", company_id=company_id, natural_language="Employee must have rest period over 8 hrs a day"),
                ContextRule(id="POL_04", company_id=company_id, natural_language="We allow OT but we're not prefer OT")
            ]
            self.save_context(rules)
        return rules

    def save_context(self, context: List[ContextRule]):
        existing = []
        if os.path.exists(self.context_path):
            try:
                with open(self.context_path, "r") as f:
                    content = f.read().strip()
                    if content: existing = [ContextRule(**p) for p in json.loads(content)]
            except: pass
        c_ids = {r.company_id for r in context}
        final = [r for r in existing if r.company_id not in c_ids] + context
        with open(self.context_path, "w") as f:
            json.dump([p.model_dump() for p in final], f, indent=4)

    def load_constraints(self, company_id: str) -> List[MachineConstraint]:
        if os.path.exists(self.constraint_path):
            try:
                with open(self.constraint_path, "r") as f:
                    content = f.read().strip()
                    if not content: return []
                    constraints = [MachineConstraint(**c) for c in json.loads(content)]
                    return [c for c in constraints if c.company_id == company_id]
            except: return []
        return []

    def sync_constraints(self, company_id: str, policy_id: str, translated_list: List[MachineConstraint]):
        all_constraints = []
        if os.path.exists(self.constraint_path):
            try:
                with open(self.constraint_path, "r") as f:
                    content = f.read().strip()
                    if content: all_constraints = [MachineConstraint(**c) for c in json.loads(content)]
            except: pass
        final = [c for c in all_constraints if not (c.policy_id == policy_id and c.company_id == company_id)]
        for tc in translated_list:
            tc.policy_id = policy_id
            tc.company_id = company_id
            final.append(tc)
        with open(self.constraint_path, "w") as f:
            json.dump([c.model_dump() for c in final], f, indent=4)

    # ============================================
    # SCHEDULE & LEAVE
    # ============================================

    def get_active_schedule_version(self, company_id: str) -> Optional[Dict]:
        return self.schedule_repo.get_active_schedule_version(company_id)

    def create_schedule_version(self, company_id: str, schedule_type: str,
                                start_date: date, end_date: date,
                                assignments: Dict, constraints: List = None,
                                score: float = None, parent_version_id: int = None) -> int:
        version_id = self.schedule_repo.create_schedule_version(
            company_id=company_id, schedule_type=schedule_type,
            start_date=start_date, end_date=end_date,
            assignments=assignments, constraints=constraints,
            score=score, parent_version_id=parent_version_id
        )
        # Log states
        employees = self.employee_repo.get_employees(company_id)
        for emp in employees:
            self.employee_repo.log_employee_state(
                company_id=company_id, employee_id=emp.id,
                schedule_version_id=version_id, accumulated_hours=emp.accumulated_hours,
                used_dayoff=emp.used_dayoff_quota, used_leave=emp.used_leave_quota,
                change_type="SCHEDULE_PUBLISH", change_reason=f"Schedule {schedule_type} created"
            )
        return version_id

    def publish_draft_version(self, draft_version_id: int) -> Optional[int]:
        return self.schedule_repo.publish_draft_version(draft_version_id)

    def archive_schedule_version(self, version_id: int):
        self.schedule_repo.archive_schedule_version(version_id)

    def record_leave_without_replacement(self, assignments: dict, date_str: str,
                                         all_blocks: List[int], emp_id: str, company_id: str,
                                         external_timestamp: str = None):
        active = self.get_active_schedule_version(company_id)
        if not active: raise ValueError("No active schedule found")
        version_id = active['id']
        day_data = assignments.get(date_str, {})
        event_ts = external_timestamp or datetime.now().isoformat()

        if emp_id in day_data:
            day_data[emp_id] = [b for b in day_data[emp_id] if b not in all_blocks]
            if not day_data[emp_id]: del day_data[emp_id]
        
        assignments[date_str] = day_data
        self.schedule_repo.update_schedule_assignments(version_id, assignments, timestamp=event_ts)
        
        hours_lost = len(all_blocks) * 4.0
        emp = next((e for e in self.employee_repo.get_employees(company_id) if e.id == emp_id), None)
        
        self.leave_repo.save_leave_record(
            company_id=company_id, schedule_version_id=version_id,
            employee_id=emp_id, date_obj=date.fromisoformat(date_str),
            shift_blocks=all_blocks, hours_lost=hours_lost, event_timestamp=event_ts
        )
        for b in all_blocks:
            self.leave_repo.remove_attendance(company_id, version_id, emp_id, date.fromisoformat(date_str), b)
        
        self.employee_repo.update_quota(emp_id, company_id, "LEAVE", 1)
        self.employee_repo.log_employee_state(
            company_id=company_id, employee_id=emp_id, schedule_version_id=version_id,
            accumulated_hours=emp.accumulated_hours - hours_lost,
            used_dayoff=emp.used_dayoff_quota, used_leave=emp.used_leave_quota + 1,
            change_type="LEAVE_TAKEN", change_reason="Leave approved",
            change_blocks=all_blocks, hours_change=-hours_lost, timestamp=event_ts
        )
        return assignments

    def swap_employee_assignment(self, assignments: dict, date_str: str,
                                  target_blocks: List[int], original_emp_id: str,
                                  replacement_emp_id: str, company_id: str,
                                  external_timestamp: str = None):
        active = self.get_active_schedule_version(company_id)
        if not active: raise ValueError("No active schedule found")
        version_id = active['id']
        day_data = assignments.get(date_str, {})
        event_ts = external_timestamp or datetime.now().isoformat()
        was_off = replacement_emp_id not in day_data

        # Logic
        if original_emp_id in day_data:
            day_data[original_emp_id] = [b for b in day_data[original_emp_id] if b not in target_blocks]
            if not day_data[original_emp_id]: del day_data[original_emp_id]
        if replacement_emp_id not in day_data: day_data[replacement_emp_id] = []
        for b in target_blocks:
            if b not in day_data[replacement_emp_id]: day_data[replacement_emp_id].append(b)
        day_data[replacement_emp_id].sort()

        assignments[date_str] = day_data
        self.schedule_repo.update_schedule_assignments(version_id, assignments, timestamp=event_ts)

        replacer_name = next(e.name for e in self.employee_repo.get_employees(company_id) if e.id == replacement_emp_id)
        leave_id = self.leave_repo.save_leave_record(
            company_id=company_id, schedule_version_id=version_id,
            employee_id=original_emp_id, date_obj=date.fromisoformat(date_str),
            shift_blocks=target_blocks, hours_lost=len(target_blocks)*4.0,
            replacement_id=replacement_emp_id, replacement_name=replacer_name,
            event_timestamp=event_ts
        )
        for b in target_blocks:
            self.leave_repo.remove_attendance(company_id, version_id, original_emp_id, date.fromisoformat(date_str), b)
            self.leave_repo.log_attendance(
                company_id=company_id, schedule_version_id=version_id,
                employee_id=replacement_emp_id, date_obj=date.fromisoformat(date_str),
                shift_block=b, is_replacement=True, original_employee_id=original_emp_id,
                leave_record_id=leave_id
            )
        if was_off: self.employee_repo.update_quota(replacement_emp_id, company_id, "DAY_OFF", -1)
        if original_emp_id not in day_data: self.employee_repo.update_quota(original_emp_id, company_id, "LEAVE", 1)

        original_emp = next(e for e in self.employee_repo.get_employees(company_id) if e.id == original_emp_id)
        replacement_emp = next(e for e in self.employee_repo.get_employees(company_id) if e.id == replacement_emp_id)

        self.employee_repo.log_employee_state(
            company_id=company_id, employee_id=original_emp_id, schedule_version_id=version_id,
            accumulated_hours=original_emp.accumulated_hours - len(target_blocks)*4.0,
            used_dayoff=original_emp.used_dayoff_quota, used_leave=original_emp.used_leave_quota + (1 if original_emp_id not in day_data else 0),
            change_type="LEAVE_TAKEN", change_reason=f"Covered by {replacer_name}",
            change_blocks=target_blocks, hours_change=-(len(target_blocks)*4.0), timestamp=event_ts
        )
        self.employee_repo.log_employee_state(
            company_id=company_id, employee_id=replacement_emp_id, schedule_version_id=version_id,
            accumulated_hours=replacement_emp.accumulated_hours + len(target_blocks)*4.0,
            used_dayoff=replacement_emp.used_dayoff_quota - (1 if was_off else 0), used_leave=replacement_emp.used_leave_quota,
            change_type="REPLACEMENT", change_reason="Covering leave",
            change_blocks=target_blocks, hours_change=len(target_blocks)*4.0, 
            replacement_for_id=original_emp_id, timestamp=event_ts
        )
        return assignments

    def save_dayoff_preference(self, company_id: str, employee_id: str, date_obj: date):
        self.leave_repo.save_dayoff_preference(company_id, None, employee_id, date_obj, "APPROVED")
        self.employee_repo.update_quota(employee_id, company_id, "DAY_OFF", 1)

    def remove_dayoff_preference(self, company_id: str, employee_id: str, date_obj: date):
        self.leave_repo.delete_dayoff_preference(company_id, employee_id, date_obj)
        self.employee_repo.update_quota(employee_id, company_id, "DAY_OFF", -1)

    def get_dayoff_preferences(self, company_id: str, start_date: date, end_date: date) -> List[Dict]:
        return self.leave_repo.get_dayoff_preferences(company_id, start_date, end_date)

    def get_leave_records(self, company_id: str, start_date: date = None, end_date: date = None) -> List[Dict]:
        return self.leave_repo.get_leave_records(company_id, start_date, end_date)

    def get_attendance_summary(self, company_id: str, start_date: date, end_date: date) -> List[Dict]:
        return self.leave_repo.get_attendance_summary(company_id, start_date, end_date)

    def get_schedule_version_history(self, company_id: str, schedule_type: str = None) -> List[Dict]:
        # Filter logic for schedule_repo
        history = self.schedule_repo.get_schedule_version_history(company_id)
        if schedule_type:
            return [v for v in history if v['schedule_type'] == schedule_type]
        return history

# Alias
ShiftManager = BusinessManager
