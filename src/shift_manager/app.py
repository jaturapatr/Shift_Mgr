import streamlit as st
import pandas as pd
from datetime import date, timedelta, datetime
import json
from typing import List

from shift_manager.manager import BusinessManager
from shift_manager.ui.active_roster import render_active_roster
from shift_manager.ui.preparation import render_interactive_roster_lab
from shift_manager.ui.constraints import render_constraint_management
from shift_manager.ui.history import render_archive
from shift_manager.ui.management import render_system_management
from shift_manager.ui.employee_detail import render_employee_detail

def main():
    st.set_page_config(page_title="Shift Manager", layout="wide")
    
    mgr = BusinessManager()
    
    # Sidebar
    with st.sidebar:
        st.title("⛽ Shift Manager")
        st.header("🏢 Context")
        
        companies = mgr.get_companies()
        if not companies:
            st.error("No companies found.")
            return
        
        company_names = [c.name for c in companies]
        selected_company_name = st.selectbox("Company", company_names)
        selected_company = next(c for c in companies if c.name == selected_company_name)
        company_id = selected_company.id
        
        st.divider()
        st.header("🧭 Navigation")
        nav_selection = st.radio(
            "Go to",
            ["Active Roster", "Roster Preparation", "Constraint Management", "Archive & History", "System Management"],
            label_visibility="collapsed"
        )
        
        st.divider()
        st.header("👥 Staff Status")
        
        teams = mgr.get_teams(company_id)
        employees = mgr.load_employees(company_id)
        
        team_filter_sidebar = st.selectbox("Filter", ["All"] + [t.name for t in teams])
        target_team_id = None if team_filter_sidebar == "All" else next(t.id for t in teams if t.name == team_filter_sidebar)
        
        filtered_employees = [e for e in employees if target_team_id is None or e.team_id == target_team_id]
        
        for e in filtered_employees:
            t_name = next((t.name for t in teams if t.id == e.team_id), "??")
            if st.button(f"[{t_name[:1]}] {e.name}: {e.accumulated_hours:.0f}h", key=f"emp_{e.id}"):
                st.session_state.selected_employee = e.id
                st.rerun()

    # Main content
    context = mgr.load_context(company_id)
    all_constraints = mgr.load_constraints(company_id)
    
    # Show employee detail if selected
    if "selected_employee" in st.session_state:
        render_employee_detail(mgr, st.session_state.selected_employee, employees, teams)
        if st.button("← Back"):
            del st.session_state.selected_employee
            st.rerun()
        return
    
    if nav_selection == "Active Roster":
        render_active_roster(mgr, company_id, employees, teams)
    elif nav_selection == "Roster Preparation":
        render_interactive_roster_lab(mgr, company_id, employees, all_constraints, teams)
    elif nav_selection == "Constraint Management":
        render_constraint_management(mgr, company_id, context, all_constraints)
    elif nav_selection == "Archive & History":
        render_archive(mgr, company_id)
    elif nav_selection == "System Management":
        render_system_management(mgr, company_id)


if __name__ == "__main__":
    main()
