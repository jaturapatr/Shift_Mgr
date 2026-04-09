from ortools.sat.python import cp_model
from typing import List, Dict, Optional
from datetime import date, timedelta
import json
from shift_manager.models import (
    Employee, DailyRequirement, ShiftBlock, MachineConstraint, ConstraintPrimitive, 
    ConstraintOp, ConstraintUnit, StaffingGap, InfeasibilityReport
)

# Shared helper for shift string formatting
def get_shift_string(blocks: List[int]) -> str:
    if not blocks: return "Day-Off"
    blocks = sorted(blocks)
    res_parts = []
    if not blocks: return ""
    
    current_shift = [blocks[0]]
    for i in range(1, len(blocks)):
        if blocks[i] == blocks[i-1] + 1:
            current_shift.append(blocks[i])
        else:
            start_h = current_shift[0] * 4
            end_h = (current_shift[-1] + 1) * 4
            res_parts.append(f"{start_h:02d}:00-{end_h:02d}:00")
            current_shift = [blocks[i]]
    
    start_h = current_shift[0] * 4
    end_h = (current_shift[-1] + 1) * 4
    res_parts.append(f"{start_h:02d}:00-{end_h:02d}:00")
    
    return ", ".join(res_parts)

class ShiftManagerSolver:
    def __init__(self, employees: List[Employee], requirements: List[DailyRequirement], 
                 constraints: List[MachineConstraint] = None, teams: List = None):
        self.employees = employees
        self.requirements = requirements
        self.constraints = constraints or []
        self.teams = teams or []
        self.model = cp_model.CpModel()
        self.work = {} # (employee_id, day_idx, block_idx)
        self.days_count = len(requirements)
        self.blocks_per_day = 6 # 4-hour blocks
        self.slacks = {} # (d_idx, b_idx, team_id) -> (slack_var, required)
        
        # Initialize Variables
        for e in self.employees:
            for d in range(self.days_count):
                for b in range(self.blocks_per_day):
                    self.work[e.id, d, b] = self.model.NewBoolVar(f'work_{e.id}_{d}_{b}')

    def _get_day_index(self, target_date: date) -> int:
        for i, r in enumerate(self.requirements):
            if r.date == target_date: return i
        return -1

    # --- Primitive Handlers ---

    def _apply_staffing_goal(self, relaxed: bool = False):
        """Primitive: STAFFING_GOAL. Logic: team_count OP value."""
        for d_idx, req in enumerate(self.requirements):
            for b_idx in range(self.blocks_per_day):
                team_reqs = req.blocks[b_idx].team_requirements if b_idx < len(req.blocks) else {}
                for team in self.teams:
                    target_val = team_reqs.get(team.id, 0)
                    op = ConstraintOp.GE 
                    for c in self.constraints:
                        if c.primitive == ConstraintPrimitive.STAFFING_GOAL and c.team_id == team.id:
                            if c.date == req.date and c.block_index == b_idx:
                                target_val = c.value; op = c.op or ConstraintOp.GE; break
                            elif c.date is None and c.block_index == b_idx:
                                target_val = c.value; op = c.op or ConstraintOp.GE
                            elif c.date is None and c.block_index is None:
                                target_val = c.value; op = c.op or ConstraintOp.GE

                    count = sum(self.work[e.id, d_idx, b_idx] for e in self.employees if e.team_id == team.id)
                    if relaxed:
                        slack = self.model.NewIntVar(0, 100, f'slack_{team.id}_{d_idx}_{b_idx}')
                        self.model.Add(count + slack >= target_val)
                        self.slacks[d_idx, b_idx, team.id] = (slack, target_val)
                    else:
                        if op == ConstraintOp.EQ: self.model.Add(count == target_val)
                        elif op == ConstraintOp.LE: self.model.Add(count <= target_val)
                        elif op == ConstraintOp.GE: self.model.Add(count >= target_val)

    def _apply_point_fix(self):
        """Primitive: POINT_FIX. Logic: work[e, d, b] == value."""
        for c in self.constraints:
            if c.primitive == ConstraintPrimitive.POINT_FIX:
                d_idx = self._get_day_index(c.date)
                if d_idx != -1 and c.employee_id:
                    if (c.employee_id, d_idx, 0) not in self.work: continue
                    if c.block_index is not None:
                        self.model.Add(self.work[c.employee_id, d_idx, c.block_index] == c.value)
                    else:
                        for b in range(self.blocks_per_day):
                            self.model.Add(self.work[c.employee_id, d_idx, b] == c.value)

    def _apply_window_limit(self):
        for c in self.constraints:
            if c.primitive == ConstraintPrimitive.WINDOW_LIMIT:
                for e in self.employees:
                    if c.unit == ConstraintUnit.BLOCKS:
                        total_blocks = self.days_count * self.blocks_per_day
                        for start in range(total_blocks - c.window_size + 1):
                            window_vars = []
                            for offset in range(c.window_size):
                                block_idx = start + offset
                                day_idx = block_idx // self.blocks_per_day
                                within_day = block_idx % self.blocks_per_day
                                window_vars.append(self.work[e.id, day_idx, within_day])
                            if c.op == ConstraintOp.LE: self.model.Add(sum(window_vars) <= c.value)
                            elif c.op == ConstraintOp.GE: self.model.Add(sum(window_vars) >= c.value)
                            elif c.op == ConstraintOp.EQ: self.model.Add(sum(window_vars) == c.value)
                    elif c.unit == ConstraintUnit.DAYS:
                        for start_day in range(self.days_count - c.window_size + 1):
                            working_days_vars = []
                            for d in range(start_day, start_day + c.window_size):
                                day_worked = self.model.NewBoolVar(f'wd_{e.id}_{d}_{c.policy_id}')
                                day_sum = sum(self.work[e.id, d, b] for b in range(self.blocks_per_day))
                                self.model.Add(day_sum >= 1).OnlyEnforceIf(day_worked)
                                self.model.Add(day_sum == 0).OnlyEnforceIf(day_worked.Not())
                                working_days_vars.append(day_worked)
                            if c.op == ConstraintOp.LE: self.model.Add(sum(working_days_vars) <= c.value)
                            elif c.op == ConstraintOp.GE: self.model.Add(sum(working_days_vars) >= c.value)
                            elif c.op == ConstraintOp.EQ: self.model.Add(sum(working_days_vars) == c.value)

    def _apply_minimum_rest_between_days(self):
        for e in self.employees:
            for d in range(self.days_count - 1):
                self.model.Add(self.work[e.id, d, 5] + self.work[e.id, d + 1, 0] <= 1)
                self.model.Add(self.work[e.id, d, 5] + self.work[e.id, d + 1, 1] <= 1)
                self.model.Add(self.work[e.id, d, 4] + self.work[e.id, d + 1, 0] <= 1)

    def _get_objective_terms(self):
        balancing_costs = []
        for team in self.teams:
            team_employees = [e for e in self.employees if e.team_id == team.id]
            if not team_employees: continue
            totals = []
            for e in team_employees:
                cur = sum(self.work[e.id, d, b] * 4 for d in range(self.days_count) for b in range(self.blocks_per_day))
                totals.append(cur + int(e.accumulated_hours))
            mi, ma = self.model.NewIntVar(0, 10000, f'mi_{team.id}'), self.model.NewIntVar(0, 10000, f'ma_{team.id}')
            for t in totals:
                self.model.Add(t >= mi)
                self.model.Add(t <= ma)
            balancing_costs.append(ma - mi)

        overtime_penalty = 0
        shift_length_penalty = 0
        for c in self.constraints:
            if c.primitive == ConstraintPrimitive.OBJECTIVE_WEIGHT:
                if c.value == 4: # OT
                    overtime_penalty += sum(self.work[e.id, d, b] for e in self.employees for d in range(self.days_count) for b in range(self.blocks_per_day)) * (c.weight or 2)
                elif c.value == 1: # 4hr shift
                    for e in self.employees:
                        for d in range(self.days_count):
                            day_blocks = sum(self.work[e.id, d, b] for b in range(self.blocks_per_day))
                            is_single = self.model.NewBoolVar(f'is_single_{e.id}_{d}')
                            self.model.Add(day_blocks == 1).OnlyEnforceIf(is_single)
                            self.model.Add(day_blocks != 1).OnlyEnforceIf(is_single.Not())
                            shift_length_penalty += is_single * (c.weight or 25)
                elif c.value == 2: # 12hr+ shift
                    for e in self.employees:
                        for d in range(self.days_count):
                            day_blocks = sum(self.work[e.id, d, b] for b in range(self.blocks_per_day))
                            is_long = self.model.NewBoolVar(f'is_long_{e.id}_{d}')
                            self.model.Add(day_blocks >= 3).OnlyEnforceIf(is_long)
                            self.model.Add(day_blocks < 3).OnlyEnforceIf(is_long.Not())
                            shift_length_penalty += is_long * (c.weight or 50)
                elif c.value == 5:  # Split shift penalty
                    for e in self.employees:
                        for d in range(self.days_count):
                            starts = []
                            is_start_0 = self.model.NewBoolVar(f's_{e.id}_{d}_0')
                            self.model.Add(is_start_0 == self.work[e.id, d, 0])
                            starts.append(is_start_0)
                            for b in range(1, self.blocks_per_day):
                                is_start = self.model.NewBoolVar(f's_{e.id}_{d}_{b}')
                                self.model.Add(is_start >= self.work[e.id, d, b] - self.work[e.id, d, b-1])
                                starts.append(is_start)
                            is_split = self.model.NewBoolVar(f'split_{e.id}_{d}')
                            self.model.Add(sum(starts) >= 2).OnlyEnforceIf(is_split)
                            self.model.Add(sum(starts) < 2).OnlyEnforceIf(is_split.Not())
                            shift_length_penalty += is_split * (c.weight or 100)
                elif c.value == 6:  # Under-staffing penalty (per team)
                    target_team_id = c.team_id
                    if target_team_id:
                        for d in range(self.days_count):
                            for b in range(self.blocks_per_day):
                                count = sum(self.work[e.id, d, b] for e in self.employees if e.team_id == target_team_id)
                                is_two = self.model.NewBoolVar(f'is_two_{target_team_id}_{d}_{b}')
                                self.model.Add(count == 2).OnlyEnforceIf(is_two)
                                self.model.Add(count != 2).OnlyEnforceIf(is_two.Not())
                                shift_length_penalty += is_two * (c.weight or 40)

        consecutive_rewards = []
        for e in self.employees:
            for d in range(self.days_count):
                for b in range(self.blocks_per_day - 1):
                    is_con = self.model.NewBoolVar(f'c_{e.id}_{d}_{b}')
                    self.model.AddBoolAnd([self.work[e.id, d, b], self.work[e.id, d, b+1]]).OnlyEnforceIf(is_con)
                    self.model.AddBoolOr([self.work[e.id, d, b].Not(), self.work[e.id, d, b+1].Not()]).OnlyEnforceIf(is_con.Not())
                    consecutive_rewards.append(is_con)
        
        crossday_rewards = []
        for e in self.employees:
            for d in range(self.days_count - 1):
                for b_today in [4, 5]:
                    for b_tomorrow in [0, 1]:
                        is_con = self.model.NewBoolVar(f'cross_{e.id}_{d}_{b_today}_{b_tomorrow}')
                        self.model.AddBoolAnd([self.work[e.id, d, b_today], self.work[e.id, d+1, b_tomorrow]]).OnlyEnforceIf(is_con)
                        self.model.AddBoolOr([self.work[e.id, d, b_today].Not(), self.work[e.id, d+1, b_tomorrow].Not()]).OnlyEnforceIf(is_con.Not())
                        crossday_rewards.append(is_con)

        return 10 * sum(balancing_costs) + overtime_penalty + shift_length_penalty - sum(consecutive_rewards) - sum(crossday_rewards)

    def _apply_no_repeated_shift(self):
        active_policy = any(c.primitive == ConstraintPrimitive.NO_REPEATED_SHIFT for c in self.constraints)
        if not active_policy: return
        for e in self.employees:
            for d in range(self.days_count - 1):
                worked_d = self.model.NewBoolVar(f'worked_{e.id}_{d}')
                worked_d_next = self.model.NewBoolVar(f'worked_{e.id}_{d+1}')
                self.model.Add(sum(self.work[e.id, d, b] for b in range(self.blocks_per_day)) >= 1).OnlyEnforceIf(worked_d)
                self.model.Add(sum(self.work[e.id, d, b] for b in range(self.blocks_per_day)) == 0).OnlyEnforceIf(worked_d.Not())
                self.model.Add(sum(self.work[e.id, d+1, b] for b in range(self.blocks_per_day)) >= 1).OnlyEnforceIf(worked_d_next)
                self.model.Add(sum(self.work[e.id, d+1, b] for b in range(self.blocks_per_day)) == 0).OnlyEnforceIf(worked_d_next.Not())
                diffs = []
                for b in range(self.blocks_per_day):
                    is_diff = self.model.NewBoolVar(f'diff_{e.id}_{d}_{b}')
                    self.model.Add(self.work[e.id, d, b] != self.work[e.id, d+1, b]).OnlyEnforceIf(is_diff)
                    self.model.Add(self.work[e.id, d, b] == self.work[e.id, d+1, b]).OnlyEnforceIf(is_diff.Not())
                    diffs.append(is_diff)
                self.model.Add(sum(diffs) >= 1).OnlyEnforceIf([worked_d, worked_d_next])

    def solve(self):
        if not self.requirements: return {}, 0.0
        self._apply_staffing_goal()
        self._apply_point_fix()
        self._apply_window_limit()
        self._apply_minimum_rest_between_days()
        self._apply_no_repeated_shift()
        obj = self._get_objective_terms()
        self.model.Minimize(obj)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 15.0
        status = solver.Solve(self.model)
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            res = {}
            for d_idx, req in enumerate(self.requirements):
                d_str = str(req.date)
                res[d_str] = {e.id: [b for b in range(self.blocks_per_day) if solver.Value(self.work[e.id, d_idx, b]) == 1] for e in self.employees}
                res[d_str] = {k: v for k, v in res[d_str].items() if v}
            return res, solver.ObjectiveValue()
        else:
            return self.diagnostic_solve(), None

    def diagnostic_solve(self) -> InfeasibilityReport:
        self.model = cp_model.CpModel()
        self.work = {}
        for e in self.employees:
            for d in range(self.days_count):
                for b in range(self.blocks_per_day):
                    self.work[e.id, d, b] = self.model.NewBoolVar(f'work_{e.id}_{d}_{b}')
        self._apply_staffing_goal(relaxed=True)
        self._apply_point_fix()
        self._apply_window_limit()
        self.model.Minimize(sum(s for s, req in self.slacks.values()))
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 10.0
        status = solver.Solve(self.model)
        gaps = []
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            for (d_idx, b_idx, team_id), (slack_var, required) in self.slacks.items():
                v = solver.Value(slack_var)
                if v > 0: gaps.append(StaffingGap(date=self.requirements[d_idx].date, team_id=team_id, block_index=b_idx, required=required, gap=v))
            return InfeasibilityReport(reason_summary=f"Staffing gaps: {len(gaps)}", gaps=gaps, recommendations=[f"Missing {g.gap} {g.team_id} on {g.date}" for g in gaps])
        return InfeasibilityReport(reason_summary="Extreme Infeasibility", gaps=[], recommendations=["Check for logic conflicts."])

    def find_replacement(self, active_assignments: Dict, emp_to_replace_id: str, target_date: date, block_idx: int) -> List[Dict]:
        target_emp = next((e for e in self.employees if e.id == emp_to_replace_id), None)
        if not target_emp: return []
        d_str = str(target_date)
        candidates = []
        for cand in [e for e in self.employees if e.team_id == target_emp.team_id and e.id != emp_to_replace_id]:
            existing_blocks = active_assignments.get(d_str, {}).get(cand.id, [])
            if block_idx in existing_blocks: continue
            violates = False; violation_reasons = []
            if len(existing_blocks) + 1 > 3:
                violates = True; violation_reasons.append("Exceeds Max 12h/day limit")
            is_adjacent = any(abs(b - block_idx) == 1 for b in existing_blocks)
            for b in existing_blocks:
                if abs(b - block_idx) == 2 and not is_adjacent:
                    violates = True; violation_reasons.append("Rest period violation (<8h split)"); break
            is_working_that_day = len(existing_blocks) > 0
            if not is_working_that_day:
                days_worked = 0
                for d_key, emps in active_assignments.items():
                    if cand.id in emps and len(emps[cand.id]) > 0: days_worked += 1
                if days_worked + 1 > 6:
                    violates = True; violation_reasons.append("Exceeds 6 working days/week")
            if violates: rec = f"NOT RECOMMENDED: {', '.join(violation_reasons)}"
            elif is_adjacent: rec = "Shift Extension (+4hr OT)"
            elif is_working_that_day: rec = "Standard Shift Swap (Non-adjacent)"
            else: rec = "Off-Duty Replacement (Full Shift)"
            if not violates and cand.accumulated_hours > 160: rec += " - High OT Hours"
            candidates.append({
                "employee_id": cand.id, "name": cand.name, 
                "penalty": (5000 if violates else (0 if is_adjacent else 100)) + (cand.accumulated_hours/10.0), 
                "is_rest_violation": violates, "recommendation": rec
            })
        return sorted(candidates, key=lambda x: x["penalty"])

    def rebalance_intra_day(self, active_assignments: Dict, team_id: str, target_date: date, leaver_id: str) -> List[Dict]:
        """Intra-day rebalancing logic for covering sudden gaps."""
        d_str = str(target_date)
        day_data = active_assignments.get(d_str, {})
        leaver_blocks = day_data.get(leaver_id, [])
        if not leaver_blocks: return []
        strategies = []

        # --- Strategy: Localized OT Extension ---
        p1_assignments = {k: list(v) for k, v in day_data.items()}
        if leaver_id in p1_assignments: del p1_assignments[leaver_id]
        p1_covered = []; p1_details = []; p1_map = {}
        for b in leaver_blocks:
            cands = self.find_replacement(active_assignments, leaver_id, target_date, b)
            extensions = [c for c in cands if "Shift Extension" in c['recommendation'] and not c['is_rest_violation']]
            if extensions:
                best = extensions[0]
                if best['employee_id'] not in p1_assignments: p1_assignments[best['employee_id']] = []
                p1_assignments[best['employee_id']].append(b); p1_covered.append(b)
                p1_map[b] = best['employee_id']
                p1_details.append(f"Block {b*4:02d}:00 covered by {best['name']} (OT)")
        if p1_covered:
            strategies.append({"id": "LOCAL_OT", "name": "Localized OT Coverage", "description": "Rapid gap coverage via overtime for adjacent shifts.", 
                               "assignments": p1_assignments, "details": p1_details, "coverage_map": p1_map,
                               "uncovered": [b for b in leaver_blocks if b not in p1_covered]})

        # --- Strategy: Global Team Re-solve ---
        p2_data = self.rebalance_team_day(active_assignments, team_id, target_date, exclude_id=leaver_id)
        if p2_data:
            changes = []
            for eid, blocks in p2_data.items():
                old = day_data.get(eid, [])
                if sorted(old) != sorted(blocks):
                    emp_name = next((e.name for e in self.employees if e.id == eid), eid)
                    changes.append(f"{emp_name}: {get_shift_string(old)} -> {get_shift_string(blocks)}")
            strategies.append({"id": "TEAM_REBALANCE", "name": "Optimized Team Rebalance", "description": "Mathematical redistribution of all team shifts to ensure safety and coverage.", 
                               "assignments": p2_data, "details": changes, "uncovered": []})
        return strategies

    def rebalance_team_day(self, active_assignments: Dict, team_id: str, target_date: date, exclude_id: str = None) -> Optional[Dict]:
        """Sub-problem solver for optimized rebalancing."""
        sub_model = cp_model.CpModel()
        team_emps = [e for e in self.employees if e.team_id == team_id and e.id != exclude_id]
        if not team_emps: return None
        vars = {}
        for e in team_emps:
            for b in range(self.blocks_per_day): vars[e.id, b] = sub_model.NewBoolVar(f'rebal_{e.id}_{b}')
        for e in team_emps:
            sub_model.Add(sum(vars[e.id, b] for b in range(self.blocks_per_day)) <= 3)
            for b in range(self.blocks_per_day - 2):
                sub_model.Add(vars[e.id, b] + vars[e.id, b+2] <= 1).OnlyEnforceIf(vars[e.id, b+1].Not())
        is_cashier = "CASHIER" in team_id.upper(); target = 1 if is_cashier else 3; d_str = str(target_date)
        penalties = []
        for b in range(self.blocks_per_day):
            count = sum(vars[e.id, b] for e in team_emps)
            slack = sub_model.NewIntVar(0, target, f'slack_{b}')
            sub_model.Add(count + slack >= target)
            penalties.append(slack * 5000)
            for e in team_emps:
                was_working = 1 if b in active_assignments.get(d_str, {}).get(e.id, []) else 0
                is_working = vars[e.id, b]; diff = sub_model.NewBoolVar(f'diff_{e.id}_{b}')
                sub_model.Add(is_working != was_working).OnlyEnforceIf(diff)
                sub_model.Add(is_working == was_working).OnlyEnforceIf(diff.Not())
                penalties.append(diff * 10)
        sub_model.Minimize(sum(penalties))
        solver = cp_model.CpSolver(); solver.parameters.max_time_in_seconds = 5.0; status = solver.Solve(sub_model)
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            res = {eid: list(v) for eid, v in active_assignments.get(d_str, {}).items() if eid != exclude_id}
            for e in team_emps: res[e.id] = [b for b in range(self.blocks_per_day) if solver.Value(vars[e.id, b]) == 1]
            return res
        return None
