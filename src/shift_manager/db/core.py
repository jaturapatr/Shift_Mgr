import sqlite3
import json
from datetime import datetime, date
from typing import List, Optional, Dict, Any

class BaseRepository:
    def __init__(self, db_path: str = "roster_memory.db"):
        self.db_path = db_path

    def _date_to_str(self, date_obj: date) -> str:
        return date_obj.isoformat() if isinstance(date_obj, date) else str(date_obj)

    def _init_schema(self):
        """Initialize all tables for the unified schema."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            # === CORE MASTER DATA ===
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS companies (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    natural_language_context TEXT,
                    created_at TEXT NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS teams (
                    id TEXT PRIMARY KEY,
                    company_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (company_id) REFERENCES companies(id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS employees (
                    id TEXT PRIMARY KEY,
                    company_id TEXT NOT NULL,
                    team_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    max_dayoff_quota INTEGER DEFAULT 52,
                    max_leave_quota INTEGER DEFAULT 13,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (company_id) REFERENCES companies(id),
                    FOREIGN KEY (team_id) REFERENCES teams(id)
                )
            """)

            # === SCHEDULE VERSIONING ===
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schedule_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id TEXT NOT NULL,
                    schedule_type TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    assignments_json TEXT NOT NULL,
                    constraints_json TEXT,
                    score REAL,
                    parent_version_id INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT,
                    created_by TEXT DEFAULT 'SYSTEM',
                    metadata_json TEXT,
                    FOREIGN KEY (company_id) REFERENCES companies(id),
                    FOREIGN KEY (parent_version_id) REFERENCES schedule_versions(id)
                )
            """)

            # === EMPLOYEE STATE TRACKING ===
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS employee_state_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id TEXT NOT NULL,
                    employee_id TEXT NOT NULL,
                    schedule_version_id INTEGER,
                    accumulated_hours REAL NOT NULL,
                    used_dayoff_quota INTEGER NOT NULL,
                    used_leave_quota INTEGER NOT NULL,
                    change_type TEXT NOT NULL,
                    change_reason TEXT,
                    change_blocks TEXT,
                    hours_change REAL DEFAULT 0.0,
                    replacement_for_id TEXT,
                    recorded_at TEXT NOT NULL,
                    FOREIGN KEY (company_id) REFERENCES companies(id),
                    FOREIGN KEY (employee_id) REFERENCES employees(id),
                    FOREIGN KEY (schedule_version_id) REFERENCES schedule_versions(id)
                )
            """)

            # === DAY-OFF PREFERENCES ===
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dayoff_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id TEXT NOT NULL,
                    schedule_version_id INTEGER,
                    employee_id TEXT NOT NULL,
                    date TEXT NOT NULL,
                    status TEXT DEFAULT 'PENDING',
                    created_at TEXT NOT NULL,
                    fulfilled_at TEXT,
                    FOREIGN KEY (company_id) REFERENCES companies(id),
                    FOREIGN KEY (employee_id) REFERENCES employees(id),
                    FOREIGN KEY (schedule_version_id) REFERENCES schedule_versions(id)
                )
            """)

            # === LEAVE RECORDS ===
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS leave_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id TEXT NOT NULL,
                    schedule_version_id INTEGER NOT NULL,
                    employee_id TEXT NOT NULL,
                    date TEXT NOT NULL,
                    shift_blocks TEXT NOT NULL,
                    hours_lost REAL NOT NULL,
                    replacement_id TEXT,
                    replacement_name TEXT,
                    approved_at TEXT NOT NULL,
                    event_timestamp TEXT,
                    approved_by TEXT DEFAULT 'SYSTEM',
                    reason TEXT,
                    status TEXT DEFAULT 'APPROVED',
                    FOREIGN KEY (company_id) REFERENCES companies(id),
                    FOREIGN KEY (employee_id) REFERENCES employees(id),
                    FOREIGN KEY (replacement_id) REFERENCES employees(id),
                    FOREIGN KEY (schedule_version_id) REFERENCES schedule_versions(id)
                )
            """)

            # === ATTENDANCE RECORDS ===
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS attendance_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id TEXT NOT NULL,
                    schedule_version_id INTEGER NOT NULL,
                    employee_id TEXT NOT NULL,
                    date TEXT NOT NULL,
                    shift_block INTEGER NOT NULL,
                    hours_worked REAL DEFAULT 4.0,
                    is_replacement INTEGER DEFAULT 0,
                    original_employee_id TEXT,
                    leave_record_id INTEGER,
                    recorded_at TEXT NOT NULL,
                    FOREIGN KEY (company_id) REFERENCES companies(id),
                    FOREIGN KEY (employee_id) REFERENCES employees(id),
                    FOREIGN KEY (schedule_version_id) REFERENCES schedule_versions(id),
                    FOREIGN KEY (leave_record_id) REFERENCES leave_records(id)
                )
            """)

            # === QUOTA USAGE ===
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS quota_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id TEXT NOT NULL,
                    employee_id TEXT NOT NULL,
                    year INTEGER NOT NULL,
                    quarter INTEGER,
                    dayoff_used INTEGER DEFAULT 0,
                    dayoff_max INTEGER DEFAULT 52,
                    leave_used INTEGER DEFAULT 0,
                    leave_max INTEGER DEFAULT 13,
                    last_updated TEXT NOT NULL,
                    FOREIGN KEY (company_id) REFERENCES companies(id),
                    FOREIGN KEY (employee_id) REFERENCES employees(id)
                )
            """)
            conn.commit()
        finally:
            conn.close()

