import datetime
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from enum import Enum

class RequestType(str, Enum):
    DAY_OFF = "DAY_OFF"
    LEAVE = "LEAVE"

class ConstraintPrimitive(str, Enum):
    POINT_FIX = "POINT_FIX"
    WINDOW_LIMIT = "WINDOW_LIMIT"
    STAFFING_GOAL = "STAFFING_GOAL"
    GROUP_BALANCING = "GROUP_BALANCING"
    OBJECTIVE_WEIGHT = "OBJECTIVE_WEIGHT"
    NO_REPEATED_SHIFT = "NO_REPEATED_SHIFT"
    PREFERENCE = "PREFERENCE"

class ConstraintOp(str, Enum):
    EQ = "=="
    LE = "<="
    GE = ">="

class ConstraintUnit(str, Enum):
    BLOCKS = "BLOCKS"
    DAYS = "DAYS"

class ConstraintTargetType(str, Enum):
    EMPLOYEE = "EMPLOYEE"
    TEAM = "TEAM"
    GLOBAL = "GLOBAL"

class Company(BaseModel):
    id: str
    name: str
    natural_language_context: Optional[str] = None

class Team(BaseModel):
    id: str
    company_id: str
    name: str

class ContextRule(BaseModel):
    id: str
    company_id: str
    natural_language: str
    is_active: bool = True

class MachineConstraint(BaseModel):
    primitive: ConstraintPrimitive
    target_type: ConstraintTargetType = ConstraintTargetType.GLOBAL
    company_id: str
    policy_id: Optional[str] = None
    is_temporary: bool = False
    explanation: Optional[str] = None
    
    # Primitive-specific params
    employee_id: Optional[str] = None
    date: Optional[datetime.date] = None
    team_id: Optional[str] = None # Link to dynamic Team
    block_index: Optional[int] = None
    
    window_size: Optional[int] = None
    unit: Optional[ConstraintUnit] = None
    op: Optional[ConstraintOp] = None
    value: Optional[int] = None
    weight: Optional[int] = None 
    
    # Preference / Relational fields
    related_employee_id: Optional[str] = None
    preference_type: Optional[str] = None # e.g. "AVOID_TOGETHER", "MUST_TOGETHER", "AVOID_SHIFT"

class Employee(BaseModel):
    id: str
    company_id: str
    team_id: str
    name: str
    # These are now tracked via quota_usage table, kept here for convenience
    accumulated_hours: float = 0.0
    used_dayoff_quota: int = 0
    used_leave_quota: int = 0
    max_dayoff_quota: int = 52
    max_leave_quota: int = 13

class QuotaUsage(BaseModel):
    company_id: str
    employee_id: str
    year: int
    quarter: Optional[int] = None
    dayoff_used: int = 0
    dayoff_max: int = 52
    leave_used: int = 0
    leave_max: int = 13
    last_updated: str

class EmployeeStateLog(BaseModel):
    id: Optional[int] = None
    company_id: str
    employee_id: str
    schedule_version_id: Optional[int] = None
    accumulated_hours: float
    used_dayoff_quota: int
    used_leave_quota: int
    change_type: str
    change_reason: Optional[str] = None
    change_blocks: Optional[List[int]] = None
    hours_change: float = 0.0
    replacement_for_id: Optional[str] = None
    recorded_at: str

class ScheduleVersion(BaseModel):
    id: Optional[int] = None
    company_id: str
    schedule_type: str  # 'DRAFT', 'ACTIVE', 'ARCHIVED'
    start_date: str
    end_date: str
    assignments_json: str
    constraints_json: Optional[str] = None
    score: Optional[float] = None
    parent_version_id: Optional[int] = None
    created_at: str
    created_by: str = "SYSTEM"
    metadata_json: Optional[str] = None

class ShiftBlock(BaseModel):
    start_hour: int
    duration: int = 4
    # Dynamic requirements: team_id -> count
    team_requirements: Dict[str, int] = {}

class DailyRequirement(BaseModel):
    date: datetime.date
    blocks: List[ShiftBlock]

class ScheduleSolution(BaseModel):
    assignments: Dict[str, Dict[str, List[int]]]
    fairness_score: float

class StaffingGap(BaseModel):
    date: datetime.date
    team_id: str
    block_index: int
    required: int
    gap: int

class InfeasibilityReport(BaseModel):
    reason_summary: str
    gaps: List[StaffingGap]
    recommendations: List[str]
