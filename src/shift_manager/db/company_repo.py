import sqlite3
from datetime import datetime
from typing import List, Optional
from shift_manager.models import Company, Team
from shift_manager.db.core import BaseRepository

class CompanyRepository(BaseRepository):
    def create_company(self, company: Company) -> Company:
        """Create a new company."""
        with self.connection() as conn:
            created_at = self._date_to_str(datetime.now())
            conn.execute("""
                INSERT OR REPLACE INTO companies (id, name, natural_language_context, created_at)
                VALUES (?, ?, ?, ?)
            """, (company.id, company.name, company.natural_language_context, created_at))
            return company

    def get_company(self, company_id: str) -> Optional[Company]:
        """Get a company by ID."""
        with self.connection() as conn:
            cursor = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
            row = cursor.fetchone()
            if row:
                return Company(
                    id=row['id'], 
                    name=row['name'], 
                    natural_language_context=row['natural_language_context']
                )
            return None

    def get_all_companies(self) -> List[Company]:
        """Get all companies."""
        with self.connection() as conn:
            cursor = conn.execute("SELECT * FROM companies")
            return [
                Company(
                    id=row['id'], 
                    name=row['name'], 
                    natural_language_context=row['natural_language_context']
                ) for row in cursor.fetchall()
            ]

    def update_company_context(self, company_id: str, context: str):
        """Update natural language context for a company."""
        with self.connection() as conn:
            conn.execute(
                "UPDATE companies SET natural_language_context = ? WHERE id = ?", 
                (context, company_id)
            )

    def create_team(self, team: Team) -> Team:
        """Create a new team."""
        with self.connection() as conn:
            created_at = self._date_to_str(datetime.now())
            conn.execute("""
                INSERT OR REPLACE INTO teams (id, company_id, name, created_at)
                VALUES (?, ?, ?, ?)
            """, (team.id, team.company_id, team.name, created_at))
            return team

    def get_teams(self, company_id: str) -> List[Team]:
        """Get all teams for a company."""
        with self.connection() as conn:
            cursor = conn.execute("SELECT * FROM teams WHERE company_id = ?", (company_id,))
            return [
                Team(
                    id=row['id'], 
                    company_id=row['company_id'], 
                    name=row['name']
                ) for row in cursor.fetchall()
            ]

    def delete_team(self, team_id: str):
        """Delete a team."""
        with self.connection() as conn:
            conn.execute("DELETE FROM teams WHERE id = ?", (team_id,))
