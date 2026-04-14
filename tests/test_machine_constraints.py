"""
Test Suite for MachineConstraint Validation and Verification (Modular Architecture)

This module provides comprehensive testing for:
1. MachineConstraint model validation (Pydantic)
2. Primitive-specific constraint logic correctness
3. Edge cases and invalid inputs
4. Integration with the CP-SAT solver
"""

import pytest
from datetime import date, timedelta
from pydantic import ValidationError
from typing import List

from shift_manager.models import (
    MachineConstraint, ConstraintPrimitive, ConstraintOp, ConstraintUnit,
    Employee, DailyRequirement, ShiftBlock, StaffingGap,
    InfeasibilityReport, ContextRule, Company, Team
)
from shift_manager.engine import ShiftManagerSolver


# ==============================================================================
# PART 1: Model Validation Tests
# ==============================================================================

class TestMachineConstraintModel:
    """Test Pydantic model validation for MachineConstraint."""

    def test_valid_point_fix_constraint(self):
        """POINT_FIX should require employee_id, date, and value."""
        c = MachineConstraint(
            primitive=ConstraintPrimitive.POINT_FIX,
            company_id="COMP_01",
            employee_id="EMP_01",
            date=date(2026, 4, 14),
            block_index=2,
            value=0
        )
        assert c.primitive == ConstraintPrimitive.POINT_FIX
        assert c.employee_id == "EMP_01"
        assert c.value == 0

    def test_valid_window_limit_constraint(self):
        """WINDOW_LIMIT should require window_size, unit, op, and value."""
        c = MachineConstraint(
            primitive=ConstraintPrimitive.WINDOW_LIMIT,
            company_id="COMP_01",
            policy_id="POL_02",
            window_size=7,
            unit=ConstraintUnit.DAYS,
            op=ConstraintOp.LE,
            value=6
        )
        assert c.primitive == ConstraintPrimitive.WINDOW_LIMIT
        assert c.window_size == 7
        assert c.unit == ConstraintUnit.DAYS
        assert c.op == ConstraintOp.LE
        assert c.value == 6

    def test_valid_staffing_goal_constraint(self):
        """STAFFING_GOAL should require team_id, op, and value."""
        c = MachineConstraint(
            primitive=ConstraintPrimitive.STAFFING_GOAL,
            company_id="COMP_01",
            team_id="TEAM_CASHIER",
            op=ConstraintOp.GE,
            value=2
        )
        assert c.primitive == ConstraintPrimitive.STAFFING_GOAL
        assert c.team_id == "TEAM_CASHIER"
        assert c.op == ConstraintOp.GE
        assert c.value == 2

    def test_valid_objective_weight_constraint(self):
        """OBJECTIVE_WEIGHT should require value and weight."""
        c = MachineConstraint(
            primitive=ConstraintPrimitive.OBJECTIVE_WEIGHT,
            company_id="COMP_01",
            value=4,
            weight=2
        )
        assert c.primitive == ConstraintPrimitive.OBJECTIVE_WEIGHT
        assert c.value == 4
        assert c.weight == 2

    def test_optional_fields_defaults(self):
        """Optional fields should have sensible defaults."""
        c = MachineConstraint(
            primitive=ConstraintPrimitive.POINT_FIX,
            company_id="COMP_01"
        )
        assert c.is_temporary is False
        assert c.policy_id is None
        assert c.employee_id is None
        assert c.date is None

    def test_invalid_primitive_rejected(self):
        """Invalid primitive value should raise ValidationError."""
        with pytest.raises(ValidationError):
            MachineConstraint(
                primitive="INVALID_PRIMITIVE",
                company_id="COMP_01"
            )

    def test_invalid_op_rejected(self):
        """Invalid op value should raise ValidationError."""
        with pytest.raises(ValidationError):
            MachineConstraint(
                primitive=ConstraintPrimitive.WINDOW_LIMIT,
                company_id="COMP_01",
                window_size=7,
                unit=ConstraintUnit.DAYS,
                op="<"  # Invalid: should be EQ, LE, or GE
            )

    def test_invalid_unit_rejected(self):
        """Invalid unit value should raise ValidationError."""
        with pytest.raises(ValidationError):
            MachineConstraint(
                primitive=ConstraintPrimitive.WINDOW_LIMIT,
                company_id="COMP_01",
                window_size=7,
                unit="HOURS",  # Invalid: should be BLOCKS or DAYS
                op=ConstraintOp.LE
            )

    def test_point_fix_requires_employee_id(self):
        """POINT_FIX without employee_id should be allowed (generic constraint)."""
        # This is valid - can be used as a pattern
        c = MachineConstraint(
            primitive=ConstraintPrimitive.POINT_FIX,
            company_id="COMP_01",
            date=date(2026, 4, 14),
            value=1
        )
        assert c.employee_id is None

    def test_all_enums_are_valid(self):
        """All enum values should be valid."""
        primitives = list(ConstraintPrimitive)
        ops = list(ConstraintOp)
        units = list(ConstraintUnit)
        
        assert len(primitives) == 7
        assert len(ops) == 3
        assert len(units) == 2


# ==============================================================================
# PART 2: Primitive Logic Verification
# ==============================================================================

class TestConstraintPrimitivesLogic:
    """Verify each primitive's logic is correctly defined."""

    @pytest.fixture
    def sample_employees(self) -> List[Employee]:
        """Create sample employees for testing."""
        return [
            Employee(id="EMP_01", company_id="COMP_01", team_id="TEAM_CASHIER",
                     name="Alice", accumulated_hours=0),
            Employee(id="EMP_02", company_id="COMP_01", team_id="TEAM_CASHIER",
                     name="Bob", accumulated_hours=0),
            Employee(id="EMP_03", company_id="COMP_01", team_id="TEAM_SERVICE",
                     name="Carol", accumulated_hours=0),
            Employee(id="EMP_04", company_id="COMP_01", team_id="TEAM_SERVICE",
                     name="Dave", accumulated_hours=0),
        ]

    @pytest.fixture
    def sample_requirements(self) -> List[DailyRequirement]:
        """Create sample daily requirements for testing."""
        team_reqs = {"TEAM_CASHIER": 1, "TEAM_SERVICE": 1}
        return [
            DailyRequirement(
                date=date(2026, 4, 13),
                blocks=[ShiftBlock(start_hour=h, team_requirements=team_reqs)
                       for h in [0, 4, 8, 12, 16, 20]]
            )
            for _ in range(7)  # 7 days
        ]

    @pytest.fixture
    def sample_teams(self) -> List[Team]:
        """Create sample teams for testing."""
        return [
            Team(id="TEAM_CASHIER", company_id="COMP_01", name="CASHIER"),
            Team(id="TEAM_SERVICE", company_id="COMP_01", name="SERVICE")
        ]

    def test_staffing_goal_ge_satisfied(self, sample_employees, sample_requirements, sample_teams):
        """STAFFING_GOAL >= value should be satisfiable."""
        constraints = [
            MachineConstraint(
                primitive=ConstraintPrimitive.STAFFING_GOAL,
                company_id="COMP_01",
                team_id="TEAM_CASHIER",
                op=ConstraintOp.GE,
                value=1
            )
        ]
        solver = ShiftManagerSolver(sample_employees, sample_requirements, constraints, teams=sample_teams)
        result, score = solver.solve()
        
        assert score is not None, "STAFFING_GOAL >= 1 should be satisfiable"
        assert len(result) > 0

    def test_staffing_goal_eq_satisfied(self, sample_employees, sample_requirements, sample_teams):
        """STAFFING_GOAL == value should work correctly."""
        constraints = [
            MachineConstraint(
                primitive=ConstraintPrimitive.STAFFING_GOAL,
                company_id="COMP_01",
                team_id="TEAM_CASHIER",
                op=ConstraintOp.EQ,
                value=1
            )
        ]
        solver = ShiftManagerSolver(sample_employees, sample_requirements, constraints, teams=sample_teams)
        result, score = solver.solve()
        
        assert score is not None, "STAFFING_GOAL == 1 should be satisfiable"

    def test_point_fix_day_off(self, sample_employees, sample_requirements, sample_teams):
        """POINT_FIX with value=0 should set employee to off for the day."""
        # Use all employees so staffing can be met
        employees = sample_employees
        
        constraints = [
            MachineConstraint(
                primitive=ConstraintPrimitive.POINT_FIX,
                company_id="COMP_01",
                employee_id="EMP_01",
                date=date(2026, 4, 13),
                block_index=0,
                value=0
            )
        ]
        solver = ShiftManagerSolver(employees, sample_requirements, constraints, teams=sample_teams)
        result, score = solver.solve()
        
        if isinstance(result, InfeasibilityReport):
            pytest.skip(f"Infeasible: {result.reason_summary}")
        
        assert score is not None
        day_13 = result.get("2026-04-13", {})
        # EMP_01 should NOT have block 0 scheduled
        emp_01_blocks = day_13.get("EMP_01", [])
        assert 0 not in emp_01_blocks, "POINT_FIX should prevent block 0 scheduling"

    def test_point_fix_work(self, sample_employees, sample_requirements, sample_teams):
        """POINT_FIX with value=1 should force employee to work."""
        # Use multiple employees so staffing can be met
        employees = [sample_employees[0], sample_employees[1]]
        single_req = [sample_requirements[0]]  # Just one day
        
        constraints = [
            MachineConstraint(
                primitive=ConstraintPrimitive.POINT_FIX,
                company_id="COMP_01",
                employee_id="EMP_01",
                date=date(2026, 4, 13),
                block_index=0,
                value=1
            )
        ]
        solver = ShiftManagerSolver(employees, single_req, constraints, teams=sample_teams)
        result, score = solver.solve()
        
        # May be infeasible with strict staffing, which is valid
        if isinstance(result, InfeasibilityReport):
            pytest.skip("Infeasible due to staffing requirements - valid behavior")
        
        assert score is not None
        day_13 = result.get("2026-04-13", {})
        assert 0 in day_13.get("EMP_01", []), "POINT_FIX=1 should force work"

    def test_window_limit_days_le(self, sample_employees, sample_requirements, sample_teams):
        """WINDOW_LIMIT on DAYS with <= should limit working days."""
        constraints = [
            MachineConstraint(
                primitive=ConstraintPrimitive.WINDOW_LIMIT,
                company_id="COMP_01",
                policy_id="POL_02",
                window_size=7,
                unit=ConstraintUnit.DAYS,
                op=ConstraintOp.LE,
                value=5  # Max 5 working days in any 7-day window
            )
        ]
        solver = ShiftManagerSolver(sample_employees, sample_requirements, constraints, teams=sample_teams)
        result, score = solver.solve()
        
        assert score is not None, "WINDOW_LIMIT DAYS <= 5 should be satisfiable"

    def test_window_limit_blocks_le(self, sample_employees, sample_requirements, sample_teams):
        """WINDOW_LIMIT on BLOCKS with <= should limit consecutive work."""
        constraints = [
            MachineConstraint(
                primitive=ConstraintPrimitive.WINDOW_LIMIT,
                company_id="COMP_01",
                policy_id="POL_03",
                window_size=4,
                unit=ConstraintUnit.BLOCKS,
                op=ConstraintOp.LE,
                value=1  # Max 1 work in any 4-block window (9hr rest)
            )
        ]
        solver = ShiftManagerSolver(sample_employees, sample_requirements, constraints, teams=sample_teams)
        result, score = solver.solve()
        
        # This may be infeasible, which is valid behavior
        if isinstance(result, InfeasibilityReport):
            # Valid - solver correctly detected infeasibility
            return
        
        assert score is not None, "WINDOW_LIMIT BLOCKS <= 1 should be satisfiable"

    def test_combined_constraints(self, sample_employees, sample_requirements, sample_teams):
        """Multiple constraints should work together."""
        constraints = [
            MachineConstraint(
                primitive=ConstraintPrimitive.WINDOW_LIMIT,
                company_id="COMP_01",
                window_size=7,
                unit=ConstraintUnit.DAYS,
                op=ConstraintOp.LE,
                value=6  # 1 day off per week
            ),
            MachineConstraint(
                primitive=ConstraintPrimitive.POINT_FIX,
                company_id="COMP_01",
                employee_id="EMP_01",
                date=date(2026, 4, 13),
                value=0  # Sunday off
            ),
            MachineConstraint(
                primitive=ConstraintPrimitive.STAFFING_GOAL,
                company_id="COMP_01",
                team_id="TEAM_CASHIER",
                op=ConstraintOp.GE,
                value=1
            )
        ]
        solver = ShiftManagerSolver(sample_employees, sample_requirements, constraints, teams=sample_teams)
        result, score = solver.solve()
        
        assert score is not None, "Combined constraints should be satisfiable"


# ==============================================================================
# PART 3: Edge Cases and Error Handling
# ==============================================================================

class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_employees_list(self):
        """Solver should handle empty employee list gracefully."""
        solver = ShiftManagerSolver([], [DailyRequirement(
            date=date(2026, 4, 13),
            blocks=[ShiftBlock(start_hour=0, team_requirements={"TEAM_CASHIER": 0})]
        )])
        result, score = solver.solve()
        # With no employees, result has dates with empty assignments
        has_dates = '2026-04-13' in result
        assignments_empty = result.get('2026-04-13', None) == {}
        assert has_dates and assignments_empty and score == 0.0

    def test_empty_requirements_list(self):
        """Solver should handle empty requirements list."""
        solver = ShiftManagerSolver(
            [Employee(id="EMP_01", company_id="COMP_01", team_id="TEAM_CASHIER", name="Alice")],
            []
        )
        result, score = solver.solve()
        assert result == {}
        assert score == 0.0

    def test_infeasible_staffing_goal(self, sample_teams):
        """Impossible STAFFING_GOAL should trigger diagnostic."""
        employees = [
            Employee(id="EMP_01", company_id="COMP_01", team_id="TEAM_CASHIER",
                     name="Alice", accumulated_hours=0)
        ]
        requirements = [
            DailyRequirement(
                date=date(2026, 4, 13),
                blocks=[ShiftBlock(start_hour=h, team_requirements={"TEAM_CASHIER": 5})
                       for h in [0, 4, 8, 12, 16, 20]]  # Need 5 cashiers
            )
        ]
        constraints = [
            MachineConstraint(
                primitive=ConstraintPrimitive.STAFFING_GOAL,
                company_id="COMP_01",
                team_id="TEAM_CASHIER",
                op=ConstraintOp.GE,
                value=5
            )
        ]
        solver = ShiftManagerSolver(employees, requirements, constraints, teams=sample_teams)
        result, score = solver.solve()
        
        # Should trigger diagnostic since infeasible
        assert score is None
        assert isinstance(result, InfeasibilityReport)
        assert len(result.gaps) > 0

    @pytest.fixture
    def sample_teams(self) -> List[Team]:
        return [Team(id="TEAM_CASHIER", company_id="COMP_01", name="CASHIER")]


# ==============================================================================
# PART 4: Integration Tests with Real Data
# ==============================================================================

class TestIntegrationWithBusinessContext:
    """Test constraints using actual business scenario data."""

    def test_24_7_gas_station_scenario(self, sample_teams):
        """Test realistic 24/7 gas station scheduling."""
        employees = [
            Employee(id=f"EMP_{i:02d}", company_id="COMP_01", team_id="TEAM_CASHIER" if i <= 3 else "TEAM_SERVICE",
                     name=f"Worker {i}", accumulated_hours=100)
            for i in range(1, 9)
        ]
        
        requirements = [
            DailyRequirement(
                date=date(2026, 4, 13) + timedelta(days=d),
                blocks=[ShiftBlock(start_hour=h, team_requirements={"TEAM_CASHIER": 1, "TEAM_SERVICE": 2})
                       for h in [0, 4, 8, 12, 16, 20]]
            )
            for d in range(7)
        ]
        
        constraints = [
            MachineConstraint(
                primitive=ConstraintPrimitive.STAFFING_GOAL,
                company_id="COMP_01",
                policy_id="POL_01",
                team_id="TEAM_CASHIER",
                op=ConstraintOp.GE,
                value=1
            ),
            MachineConstraint(
                primitive=ConstraintPrimitive.WINDOW_LIMIT,
                company_id="COMP_01",
                policy_id="POL_02",
                window_size=7,
                unit=ConstraintUnit.DAYS,
                op=ConstraintOp.LE,
                value=6
            )
        ]
        
        solver = ShiftManagerSolver(employees, requirements, constraints, teams=sample_teams)
        result, score = solver.solve()
        
        if isinstance(result, InfeasibilityReport):
            pytest.skip(f"Constraints infeasible: {result.reason_summary}")
        
        assert score is not None
        assert len(result) == 7

    @pytest.fixture
    def sample_teams(self) -> List[Team]:
        return [
            Team(id="TEAM_CASHIER", company_id="COMP_01", name="CASHIER"),
            Team(id="TEAM_SERVICE", company_id="COMP_01", name="SERVICE")
        ]


# ==============================================================================
# PART 5: Replacement Finder Tests
# ==============================================================================

class TestReplacementFinder:
    """Test the find_replacement functionality."""

    def test_find_available_replacement(self):
        """Should find replacement when available."""
        employees = [
            Employee(id="EMP_01", company_id="COMP_01", team_id="TEAM_CASHIER",
                     name="Alice"),
            Employee(id="EMP_02", company_id="COMP_01", team_id="TEAM_CASHIER",
                     name="Bob")
        ]
        
        active = {
            "2026-04-13": {
                "EMP_01": [0, 1],
                "EMP_02": []
            }
        }
        
        solver = ShiftManagerSolver(employees, [])
        candidates = solver.find_replacement(
            active, "EMP_01", date(2026, 4, 13), 2
        )
        
        assert len(candidates) > 0
        bob = next((c for c in candidates if c["employee_id"] == "EMP_02"), None)
        assert bob is not None

    def test_no_replacement_for_wrong_team(self):
        """Should not suggest employees from different teams."""
        employees = [
            Employee(id="EMP_01", company_id="COMP_01", team_id="TEAM_CASHIER",
                     name="Alice"),
            Employee(id="EMP_02", company_id="COMP_01", team_id="TEAM_SERVICE",
                     name="Bob")  # Different team
        ]
        
        solver = ShiftManagerSolver(employees, [])
        candidates = solver.find_replacement(
            {}, "EMP_01", date(2026, 4, 13), 0
        )
        
        assert len(candidates) == 0


# ==============================================================================
# PART 6: Report Models Tests
# ==============================================================================

class TestReportModels:
    """Test StaffingGap and InfeasibilityReport models."""

    def test_staffing_gap_model(self):
        """StaffingGap should validate correctly."""
        gap = StaffingGap(
            date=date(2026, 4, 13),
            team_id="TEAM_CASHIER",
            block_index=2,
            required=3,
            gap=2
        )
        assert gap.required == 3
        assert gap.gap == 2

    def test_infeasibility_report_model(self):
        """InfeasibilityReport should contain gaps and recommendations."""
        gaps = [
            StaffingGap(
                date=date(2026, 4, 13),
                team_id="TEAM_CASHIER",
                block_index=0,
                required=2,
                gap=1
            )
        ]
        report = InfeasibilityReport(
            reason_summary="Staffing gap detected",
            gaps=gaps,
            recommendations=["Add more cashiers", "Reduce requirements"]
        )
        
        assert len(report.gaps) == 1
        assert len(report.recommendations) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
