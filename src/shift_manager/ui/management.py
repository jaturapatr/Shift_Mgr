import streamlit as st
import pandas as pd
from typing import List
from datetime import datetime
from shift_manager.manager import BusinessManager
from shift_manager.models import Employee

def render_system_management(mgr: BusinessManager, company_id: str):
    """Render System Management page with integrated backup/restore."""
    st.header("⚙️ System Management")
    tab1, tab2, tab3, tab4 = st.tabs(["🏢 Companies", "👥 Teams", "👤 Employees", "💾 Backup & Restore"])

    with tab1:
        st.subheader("Manage Companies")
        companies = mgr.get_companies()
        df_comp = pd.DataFrame([{"ID": c.id, "Name": c.name, "Context": c.natural_language_context} for c in companies])
        st.dataframe(df_comp, width="stretch", hide_index=True)

        with st.expander("➕ Add New Company"):
            with st.form("add_company_form"):
                new_name = st.text_input("Company Name")
                new_context = st.text_area("Business Context", "Operate 24/7")
                if st.form_submit_button("Create Company"):
                    if new_name:
                        mgr.create_company(new_name, new_context)
                        st.success(f"Company '{new_name}' created!")
                        st.rerun()
                    else:
                        st.error("Name is required.")

    with tab2:
        st.subheader("Manage Teams")
        companies = mgr.get_companies()
        selected_comp_name = st.selectbox("Select Company", [c.name for c in companies], key="team_comp_sel")
        selected_comp = next(c for c in companies if c.name == selected_comp_name)
        
        teams = mgr.get_teams(selected_comp.id)
        if teams:
            df_teams = pd.DataFrame([{"ID": t.id, "Name": t.name, "Company": t.company_id} for t in teams])
            st.dataframe(df_teams, width="stretch", hide_index=True)
        else:
            st.info("No teams found.")

        with st.expander("➕ Add New Team"):
            with st.form("add_team_form"):
                team_name = st.text_input("Team Name")
                if st.form_submit_button("Create Team"):
                    if team_name:
                        mgr.create_team(selected_comp.id, team_name)
                        st.success(f"Team '{team_name}' created!")
                        st.rerun()

        if teams:
            st.divider()
            st.subheader("🗑️ Remove Team")
            team_to_del = st.selectbox("Select Team to Remove", [t.name for t in teams])
            if st.button("Delete Team", type="secondary"):
                target = next((t for t in teams if t.name == team_to_del), None)
                if target:
                    mgr.delete_team(target.id)
                    st.success(f"Team {team_to_del} removed.")
                    st.rerun()

    with tab3:
        st.subheader("Manage Employees")
        companies = mgr.get_companies()
        selected_comp_name = st.selectbox("Select Company", [c.name for c in companies], key="emp_comp_sel")
        selected_comp = next(c for c in companies if c.name == selected_comp_name)
        
        teams = mgr.get_teams(selected_comp.id)
        employees = mgr.load_employees(selected_comp.id)
        
        if not teams:
            st.warning("Please create a team first.")
        else:
            team_filter = st.selectbox("Filter by Team", ["All"] + [t.name for t in teams], key="emp_list_filter")
            target_team_id = None if team_filter == "All" else next(t.id for t in teams if t.name == team_filter)
            
            display_emps = [e for e in employees if target_team_id is None or e.team_id == target_team_id]
            
            if display_emps:
                df_emps = []
                for e in display_emps:
                    t_name = next((t.name for t in teams if t.id == e.team_id), "Unknown")
                    df_emps.append({
                        "ID": e.id,
                        "Name": e.name,
                        "Team": t_name,
                        "Hours": e.accumulated_hours,
                        "Used Leave": e.used_leave_quota
                    })
                st.dataframe(pd.DataFrame(df_emps), width="stretch", hide_index=True)
            
            with st.expander("➕ Add New Employee"):
                with st.form("add_emp_form"):
                    emp_name = st.text_input("Employee Name")
                    emp_team_choice = st.selectbox("Team", [t.name for t in teams])
                    target_team = next(t for t in teams if t.name == emp_team_choice)
                    initial_hours = st.number_input("Initial Hours", value=120.0)
                    
                    if st.form_submit_button("Add Employee"):
                        if emp_name:
                            new_emp = Employee(
                                id=f"EMP_{selected_comp.id}_{len(employees) + 1:02d}",
                                company_id=selected_comp.id,
                                team_id=target_team.id,
                                name=emp_name,
                                accumulated_hours=initial_hours
                            )
                            mgr.employee_repo.create_employee(new_emp)
                            st.success(f"Employee '{emp_name}' added!")
                            st.rerun()

            if display_emps:
                st.divider()
                st.subheader("🗑️ Danger Zone")
                emp_to_del = st.selectbox("Select Employee", [e.name for e in display_emps])
                if st.button("Remove Employee", type="secondary"):
                    target = next((e for e in display_emps if e.name == emp_to_del), None)
                    if target:
                        mgr.remove_employee(target.id)
                        st.success(f"Employee {emp_to_del} removed.")
                        st.rerun()

    with tab4:
        st.subheader("💾 System Backup & Restore")
        st.write("Maintain full portability of your company's master and operational data.")
        
        col_exp, col_imp = st.columns(2)
        
        with col_exp:
            st.info("**📤 Export/Backup**\n\nGenerate a complete snapshot of the current company state.")
            try:
                full_backup_json = mgr.export_operational_data(company_id)
                st.download_button(
                    label="📥 Download Full System Backup",
                    data=full_backup_json,
                    file_name=f"full_system_backup_{company_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                    mime="application/json",
                    use_container_width=True,
                    type="primary"
                )
                st.caption("Snapshot includes: Teams, Employees, Quotas, Rosters, and Audit Logs.")
            except Exception as e:
                st.error(f"Export failed: {e}")

        with col_imp:
            st.warning("**📥 Import/Restore**\n\nWarning: This will surgically replace ALL current data for this company with the backup content.")
            uploaded_file = st.file_uploader("Select Backup JSON file", type=["json"], label_visibility="collapsed")
            if uploaded_file:
                if st.button("🚀 EXECUTE RESTORE", type="primary", use_container_width=True):
                    try:
                        content = uploaded_file.getvalue().decode("utf-8")
                        mgr.import_operational_data(company_id, content)
                        st.success("System data restored successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Restore failed: {e}")

        st.divider()
        st.subheader("🛠️ System Maintenance")
        with st.expander("🚨 Emergency: Reset System to Defaults"):
            st.error("DANGER: This restores basic constraints from backup and WIPES ALL operational data (Rosters, Logs, Quotas).")
            if st.button("Execute Hard Reset", use_container_width=True):
                with st.spinner("Resetting..."):
                    mgr.reset_to_defaults()
                    st.success("Hard reset complete.")
                    st.rerun()
