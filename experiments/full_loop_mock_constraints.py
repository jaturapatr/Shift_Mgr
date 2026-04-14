import os
import json
from datetime import date, timedelta
from shift_manager.engine import ShiftManagerSolver
from shift_manager.models import (
    Employee, Team, DailyRequirement, ShiftBlock, MachineConstraint,
    ConstraintPrimitive, ConstraintTargetType, ConstraintOp, ConstraintUnit
)

def run_mock_full_chain_test():
    print("🚀 STARTING MOCK FULL-LOOP TEST (PRE-TRANSLATED LOGIC)")
    print("=" * 60)
    
    company_id = "COMP_01"
    
    # 1. SETUP CONTEXT (Same as original test)
    employees = [
        Employee(id="UUID-ALICE", company_id=company_id, team_id="TEAM-CASHIER", name="Alice"),
        Employee(id="UUID-BOB", company_id=company_id, team_id="TEAM-CASHIER", name="Bob"),
        Employee(id="UUID-SA", company_id=company_id, team_id="TEAM-SERVICE", name="Service A"),
        Employee(id="UUID-SF", company_id=company_id, team_id="TEAM-SERVICE", name="Service F"),
    ]
    teams = [
        Team(id="TEAM-CASHIER", company_id=company_id, name="CASHIER"),
        Team(id="TEAM-SERVICE", company_id=company_id, name="SERVICE"),
    ]
    
    # 2. MOCK TRANSLATION OUTPUT
    # Instead of calling LLM, we provide what the LLM SHOULD have returned
    all_translated_constraints = [
        # "Alice needs next Tuesday (2026-04-14) off"
        MachineConstraint(
            primitive=ConstraintPrimitive.POINT_FIX,
            target_type=ConstraintTargetType.EMPLOYEE,
            company_id=company_id,
            employee_id="UUID-ALICE",
            date=date(2026, 4, 14),
            value=0,
            explanation="Alice requested Tuesday off."
        ),
        # "Service A and Service F cannot work together"
        MachineConstraint(
            primitive=ConstraintPrimitive.PREFERENCE,
            target_type=ConstraintTargetType.EMPLOYEE,
            company_id=company_id,
            employee_id="UUID-SA",
            related_employee_id="UUID-SF",
            preference_type="AVOID_TOGETHER",
            explanation="Service A and F cannot work together."
        ),
        # "We need 1 cashier for every shift block"
        MachineConstraint(
            primitive=ConstraintPrimitive.STAFFING_GOAL,
            target_type=ConstraintTargetType.TEAM,
            company_id=company_id,
            team_id="TEAM-CASHIER",
            value=1,
            op=ConstraintOp.EQ,
            explanation="Require 1 cashier per block."
        ),
        # "Bob can only work 3 days a week"
        MachineConstraint(
            primitive=ConstraintPrimitive.WINDOW_LIMIT,
            target_type=ConstraintTargetType.EMPLOYEE,
            company_id=company_id,
            employee_id="UUID-BOB",
            window_size=7,
            unit=ConstraintUnit.DAYS,
            op=ConstraintOp.LE,
            value=3,
            explanation="Bob limited to 3 days per week."
        )
    ]

    print(f"\n[SUMMARY] Total Mocked Constraints: {len(all_translated_constraints)}")
    for i, c in enumerate(all_translated_constraints):
        print(f" {i}. {c.primitive.value} | Target: {c.target_type} | ID: {c.employee_id or c.team_id} | Value: {c.value} | Explanation: {c.explanation}")

    # 3. SETUP ENGINE
    # 7 day week starting Monday April 13, 2026
    start_date = date(2026, 4, 13)
    requirements = []
    for i in range(7):
        curr_date = start_date + timedelta(days=i)
        # 6 blocks per day (4 hours each)
        # We need at least one cashier (TEAM-CASHIER) per block to satisfy the staffing goal
        # and at least one SERVICE for blocks if we want them to work too.
        blocks = [ShiftBlock(start_hour=h*4, team_requirements={"TEAM-CASHIER": 1, "TEAM-SERVICE": 1}) for h in range(6)]
        requirements.append(DailyRequirement(date=curr_date, blocks=blocks))

    print("\n[PHASE 2] Running OR-Tools Solver with Mocked Logic...")
    solver = ShiftManagerSolver(employees, requirements, all_translated_constraints, teams)
    
    assignments, score = solver.solve()
    
    from shift_manager.models import InfeasibilityReport

    if score is not None:
        print(f"\n✨ SUCCESS! Schedule generated. Score: {score}")
        print("-" * 30)
        # Verify a few specific days
        for d_str, day_data in sorted(assignments.items()):
            print(f"\n📅 Date: {d_str}")
            for eid, blocks in day_data.items():
                name = next(e.name for e in employees if e.id == eid)
                if blocks: # Only show working employees
                    print(f"  - {name}: Blocks {blocks}")
                
        # --- VERIFICATION CHECKS ---
        print("\n[PHASE 3] Validation Report:")
        
        # Check 1: Alice Off on Tuesday
        tuesday = "2026-04-14"
        alice_tuesday = assignments.get(tuesday, {}).get("UUID-ALICE", [])
        print(f" - Alice on Tuesday: {alice_tuesday} {'✅ (Correctly Off)' if not alice_tuesday else '❌ (FAILED)'}")
        
        # Check 2: Service A and F separation
        separation_violation = False
        for d_str, day_data in assignments.items():
            if "UUID-SA" in day_data and "UUID-SF" in day_data:
                # Check overlapping blocks
                overlap = set(day_data["UUID-SA"]) & set(day_data["UUID-SF"])
                if overlap: separation_violation = True
        print(f" - SA/SF Separation: {'✅ (Strictly Separated)' if not separation_violation else '❌ (FAILED)'}")
        
        # Check 3: Bob 3-day limit
        bob_days = sum(1 for d in assignments.values() if "UUID-BOB" in d and d["UUID-BOB"])
        print(f" - Bob's Work Days: {bob_days} {'✅ (Limit Respected: ' + str(bob_days) + ')' if bob_days <= 3 else '❌ (FAILED: ' + str(bob_days) + ')'}")

    else:
        print("\n❌ SOLVER FAILED: The constraints were too strict or conflicted.")
        if isinstance(assignments, InfeasibilityReport):
            print(f"Reason: {assignments.reason_summary}")
            for gap in assignments.gaps:
                print(f"  - Gap: {gap.date} {gap.team_id} block {gap.block_index}")

if __name__ == "__main__":
    run_mock_full_chain_test()
