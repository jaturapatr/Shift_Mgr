import sqlite3
from datetime import datetime
from typing import List, Optional
from shift_manager.models import Company, Team
from shift_manager.db.core import BaseRepository

class CompanyRepository(BaseRepository):
    def create_company(self, company: Company) -> Company:
        """Create a new company."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            created_at = datetime.now().isoformat()
            cursor.execute("""
                INSERT OR REPLACE INTO companies (id, name, natural_language_context, created_at)
                VALUES (?, ?, ?, ?)
            """, (company.id, company.name, company.natural_language_context, created_at))
            conn.commit()
            return company
        finally:
            conn.close()

    def get_company(self, company_id: str) -> Optional[Company]:
        """Get a company by ID."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
            row = cursor.fetchone()
            if row:
                return Company(id=row[0], name=row[1], natural_language_context=row[2])
            return None
        finally:
            conn.close()

    def get_all_companies(self) -> List[Company]:
        """Get all companies."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM companies")
            return [Company(id=row[0], name=row[1], natural_language_context=row[2]) for row in cursor.fetchall()]
        finally:
            conn.close()

    def update_company_context(self, company_id: str, context: str):
        """Update natural language context for a company."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE companies SET natural_language_context = ? WHERE id = ?", (context, company_id))
            conn.commit()
        finally:
            conn.close()

    def create_team(self, team: Team) -> Team:
        """Create a new team."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            created_at = datetime.now().isoformat()
            cursor.execute("""
                INSERT OR REPLACE INTO teams (id, company_id, name, created_at)
                VALUES (?, ?, ?, ?)
            """, (team.id, team.company_id, team.name, created_at))
            conn.commit()
            return team
        finally:
            conn.close()

    def get_teams(self, company_id: str) -> List[Team]:
        """Get all teams for a company."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM teams WHERE company_id = ?", (company_id,))
            return [Team(id=row[0], company_id=row[1], name=row[2]) for row in cursor.fetchall()]
        finally:
            conn.close()

    def delete_team(self, team_id: str):
        """Delete a team."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM teams WHERE id = ?", (team_id,))
            conn.commit()
        finally:
            conn.close()
