import pytest
from datetime import date, timedelta
from shift_manager.manager import BusinessManager
from shift_manager.models import Employee, Team, Company, DailyRequirement, ShiftBlock

@pytest.fixture
def manager():
    # Use a separate test database
    db_path = "test_roster.db"
    if hasattr(BusinessManager, '__init__'):
        mgr = BusinessManager(db_path=db_path)
    else:
        mgr = BusinessManager()
    yield mgr
    import os
    if os.path.exists(db_path):
        os.remove(db_path)

def test_full_roster_lifecycle(manager):
    """Verify end-to-end roster lifecycle in modular architecture."""
    company_id = "TEST_COMP"
    
    # 1. Setup Master Data
    company = Company(id=company_id, name="Test Company")
    manager.company_repo.create_company(company)
    
    team = manager.create_team(company_id, "TEST_TEAM")
    
    emp = Employee(
        id="TEST_EMP", 
        company_id=company_id, 
        team_id=team.id, 
        name="Test Employee",
        accumulated_hours=100
    )
    manager.employee_repo.create_employee(emp)
    
    # 2. Create DRAFT Roster
    start_date = date(2026, 5, 4)
    end_date = start_date + timedelta(days=6)
    
    assignments = {
        str(start_date): {emp.id: [0, 1]} # 8h shift
    }
    
    draft_id = manager.create_schedule_version(
        company_id=company_id,
        schedule_type="DRAFT",
        start_date=start_date,
        end_date=end_date,
        assignments=assignments,
        score=100.0
    )
    
    assert draft_id is not None
    
    # 3. Record Leave (Working Phase)
    # First publish to make it active so leave recording works
    manager.publish_draft_version(draft_id)
    
    active = manager.get_active_schedule_version(company_id)
    assert active['id'] == draft_id
    assert active['schedule_type'] == 'ACTIVE'
    
    # Record leave for the block 0
    event_ts = "TRANSACTION_001"
    updated_assignments = manager.record_leave_without_replacement(
        assignments=assignments,
        date_str=str(start_date),
        all_blocks=[0],
        emp_id=emp.id,
        company_id=company_id,
        external_timestamp=event_ts
    )
    
    # 4. Verify Persistence
    # Check assignment update
    active_now = manager.get_active_schedule_version(company_id)
    import json
    saved_assignments = json.loads(active_now['assignments_json'])
    assert saved_assignments[str(start_date)][emp.id] == [1]
    
    # Check leave record
    leaves = manager.get_leave_records(company_id, start_date, end_date)
    assert len(leaves) == 1
    assert leaves[0]['employee_id'] == emp.id
    assert leaves[0]['event_timestamp'] == event_ts
    
    # Check employee state log
    history = manager.get_employee_state_history(emp.id)
    # History should have INITIAL, SCHEDULE_PUBLISH, and LEAVE_TAKEN
    change_types = [h['change_type'] for h in history]
    assert "LEAVE_TAKEN" in change_types
    
    # 5. Archive
    manager.archive_schedule_version(draft_id)
    archived = manager.get_schedule_version_history(company_id, schedule_type="ARCHIVED")
    assert any(v['id'] == draft_id for v in archived)

def test_repository_independence(manager):
    """Ensure repositories are correctly initialized and reachable."""
    assert manager.company_repo is not None
    assert manager.employee_repo is not None
    assert manager.schedule_repo is not None
    assert manager.leave_repo is not None
