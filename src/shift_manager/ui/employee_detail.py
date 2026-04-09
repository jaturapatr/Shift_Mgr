import streamlit as st
import pandas as pd
from typing import List
from shift_manager.manager import BusinessManager

def render_employee_detail(mgr: BusinessManager, employee_id: str, employees: List, teams: List):
    """Render detailed view of an employee's history."""
    emp = next((e for e in employees if e.id == employee_id), None)
    if not emp:
        st.error("Employee not found")
        return
    
    emp_team = next((t.name for t in teams if t.id == emp.team_id), "Unknown")
    
    st.subheader(f"👤 {emp.name}")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Team", emp_team)
    col2.metric("Total Hours", f"{emp.accumulated_hours:.0f}h")
    col3.metric("Used Leave", f"{emp.used_leave_quota}")
    col4.metric("Used Day-Off", f"{emp.used_dayoff_quota}")
    
    st.divider()
    st.subheader("📜 State History")
    
    history = mgr.get_employee_state_history(employee_id)
    
    if history:
        hist_data = []
        for h in history:
            hist_data.append({
                "Time": h['recorded_at'][:19],
                "Type": h['change_type'],
                "Hours": f"{h['accumulated_hours']:.0f}h",
                "Δ Hours": f"{h['hours_change']:+.0f}" if h['hours_change'] else "-",
                "Reason": h['change_reason'] or "-",
                "Replacement For": h['replacement_for_id'] or "-"
            })
        st.dataframe(pd.DataFrame(hist_data), width="stretch", hide_index=True)
    else:
        st.info("No history records.")
