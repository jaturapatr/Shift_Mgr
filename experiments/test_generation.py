import sys
import os
from datetime import date, timedelta

# Add src to path
sys.path.append(os.path.join(os.getcwd(), "src"))

from shift_manager.manager import BusinessManager
from shift_manager.models import DailyRequirement, ShiftBlock
from shift_manager.engine import ShiftManagerSolver

def test_generation():
    print("--- Testing Roster Generation with Current Constraints ---")
    mgr = BusinessManager()
    company_id = "COMP_01"
    
    # 1. Load Data
    employees = mgr.load_employees(company_id)
    constraints = mgr.load_constraints(company_id)
    teams = mgr.get_teams(company_id)
    
    print(f"Loaded {len(employees)} employees, {len(constraints)} constraints, and {len(teams)} teams.")
    
    # 2. Setup Requirements (Standard 1 cashier, 3 service)
    # Map team names to IDs
    team_map = {t.name.upper(): t.id for t in teams}
    cashier_id = team_map.get("CASHIER")
    service_id = team_map.get("SERVICE")
    
    def_reqs = {}
    if cashier_id: def_reqs[cashier_id] = 1
    if service_id: def_reqs[service_id] = 3

    start_date = date(2026, 4, 13)
    reqs = []
    for d in range(7):
        current_date = start_date + timedelta(days=d)
        reqs.append(DailyRequirement(
            date=current_date, 
            blocks=[ShiftBlock(start_hour=h, team_requirements=def_reqs) for h in [0, 4, 8, 12, 16, 20]]
        ))
    
    # 3. Solve
    solver = ShiftManagerSolver(employees, reqs, constraints, teams=teams)
    result, score = solver.solve()
    
    if score is not None:
        print(f"✅ SUCCESS: Generation is FEASIBLE.")
        print(f"Optimization Score: {score:.2f}")
        
        # Verify no repeated shifts for one employee
        if len(employees) > 0:
            target_emp = employees[0]
            print(f"\nShift Pattern for {target_emp.name}:")
            for d in range(7):
                d_str = str(start_date + timedelta(days=d))
                blocks = result.get(d_str, {}).get(target_emp.id, [])
                print(f"  - {d_str}: {blocks}")
    else:
        print("❌ FAILED: Generation is INFEASIBLE.")
        if hasattr(result, 'reason_summary'):
            print(f"Summary: {result.reason_summary}")
        else:
            print("Unknown infeasibility reason.")

if __name__ == "__main__":
    test_generation()
