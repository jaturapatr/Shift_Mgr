from shift_manager.db.company_repo import CompanyRepository
from shift_manager.db.employee_repo import EmployeeRepository
from shift_manager.db.schedule_repo import ScheduleRepository
from shift_manager.db.leave_repo import LeaveRepository

class DatabaseManager(CompanyRepository, EmployeeRepository, ScheduleRepository, LeaveRepository):
    """
    Facade class that combines all repositories for backward compatibility.
    New code should prefer using specific repositories or BusinessManager.
    """
    def __init__(self, db_path: str = "roster_memory.db"):
        super().__init__(db_path)
        self._init_schema()

# Alias for backward compatibility
MemoryManager = DatabaseManager
