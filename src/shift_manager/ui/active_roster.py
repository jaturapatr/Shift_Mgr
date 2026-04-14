import streamlit as st
import pandas as pd
from datetime import date, timedelta, datetime
import json
from typing import List

from shift_manager.models import (
    DailyRequirement, ShiftBlock, ConstraintPrimitive, MachineConstraint,
    Company, Employee, Team
)
from shift_manager.engine import ShiftManagerSolver
from shift_manager.manager import BusinessManager
from shift_manager.ui.utils import get_shift_string, generate_roster_html

def render_active_roster(mgr: BusinessManager, company_id: str, employees: List, teams: List):
    """Render the Active Roster page with leave management."""
    st.header("🗓️ Active Roster")
    
    # Get active schedule version
    active = mgr.get_active_schedule_version(company_id)

    if not active:
        st.info("No active schedule found. Go to 'Roster Preparation' to create and publish one.")
        return

    start_date_str = active['start_date']
    assignments = json.loads(active['assignments_json'])

    # Fetch leave records for the period
    start_dt = date.fromisoformat(start_date_str)
    end_dt = start_dt + timedelta(days=6)
    leave_records = mgr.get_leave_records(company_id, start_dt, end_dt)
    leave_lookup = {(r['employee_id'], r['date']) for r in leave_records}
    
    # To get leaver name for the replacer:
    direct_rep_to_leaver = {
        (r['replacement_id'], r['date']): next((e.name for e in employees if e.id == r['employee_id']), "Staff")
        for r in leave_records if r.get('replacement_id') and r['replacement_id'] != "REBALANCE"
    }
    # Rebalance flag for the day
    rebalanced_days = {r['date'] for r in leave_records if r.get('replacement_id') == "REBALANCE"}

    # Header info
    col_info, col_export = st.columns([3, 1])
    with col_info:
        st.info(f"Schedule Version #{active['id']} | Period: {start_date_str}")

    with col_export:
        companies = mgr.get_companies()
        match = next((c.name for c in companies if c.id == company_id), "Shift Manager")
        report_html = generate_roster_html(match, start_date_str, employees, assignments, teams, leave_records=leave_records)
        st.download_button(
            label="📥 Export",
            data=report_html,
            file_name=f"roster_{company_id}_{start_date_str}.html",
            mime="text/html",
            width="stretch"
        )

    # --- Interactive Roster Grid ---
    st.subheader("📊 Roster Grid (Click shift to request leave)")

    dates = sorted(list(assignments.keys()))
    short_headers = {d_str: date.fromisoformat(d_str).strftime("%a %d") for d_str in dates}

    cols = st.columns([2] + [1]*7)
    cols[0].write("**Employee**")
    for i, d_str in enumerate(dates):
        cols[i+1].write(f"**{short_headers[d_str]}**")

    sorted_employees = sorted(employees, key=lambda x: (x.team_id, x.name))

    for emp in sorted_employees:
        cols = st.columns([2] + [1]*7)
        emp_team = next((t.name for t in teams if t.id == emp.team_id), "Unknown")
        cols[0].write(f"{emp.name} ({emp_team[:1]})")

        for i, d_str in enumerate(dates):
            blocks = assignments.get(d_str, {}).get(emp.id, [])
            if blocks:
                shift_str = get_shift_string(blocks)
                leaver_name = direct_rep_to_leaver.get((emp.id, d_str))
                is_rebalanced = d_str in rebalanced_days
                
                # --- HIGHLIGHT LOGIC ---
                is_target = False
                is_overlapping = False
                btn_type = "secondary"
                
                if leaver_name:
                    label = f"🔄 {shift_str}"
                elif is_rebalanced:
                    label = f"⚙️ {shift_str}"
                else:
                    label = shift_str
                
                if "target_shift" in st.session_state:
                    ts = st.session_state.target_shift
                    if ts["date_str"] == d_str:
                        if ts["emp_id"] == emp.id:
                            is_target = True
                            btn_type = "primary"
                            label = f"🎯 {shift_str}"
                        else:
                            overlap = set(blocks).intersection(set(ts["all_blocks"]))
                            if overlap:
                                is_overlapping = True
                                label = f"👥 {shift_str}"

                if cols[i+1].button(label, key=f"sel_{emp.id}_{d_str}", width="stretch", type=btn_type):
                    st.session_state.target_shift = {
                        "emp_id": emp.id,
                        "emp_name": emp.name,
                        "date_str": d_str,
                        "all_blocks": blocks
                    }
                    if "replacement_candidates" in st.session_state:
                        del st.session_state.replacement_candidates
                    st.rerun()
            elif (emp.id, d_str) in leave_lookup:
                cols[i+1].markdown("<span style='color:orange; font-weight:bold;'>Leaved</span>", unsafe_allow_html=True)
            else:
                cols[i+1].write("Day-Off")
    st.divider()

    # --- Leave Request Section ---
    if "target_shift" in st.session_state:
        ts = st.session_state.target_shift
        
        # Current data for the leaver
        current_day_data = assignments.get(ts["date_str"], {})
        remaining_blocks = sorted(current_day_data.get(ts["emp_id"], []))
        
        if not remaining_blocks:
            st.success(f"✅ Leave processing complete for {ts['emp_name']}.")
            del st.session_state.target_shift
            if "replacement_candidates" in st.session_state:
                del st.session_state.replacement_candidates
            st.rerun()

        st.subheader(f"🔄 Leave Request: {ts['emp_name']}")
        st.markdown(f"**Date:** {ts['date_str']} | **Remaining Shift:** {get_shift_string(remaining_blocks)}")
        
        leaver_emp = next(e for e in employees if e.id == ts['emp_id'])
        leaver_team_name = next((t.name for t in teams if t.id == leaver_emp.team_id), "").upper()
        
        # Calculate staffing for first/last blocks
        start_b, end_b = remaining_blocks[0], remaining_blocks[-1]
        
        # --- DYNAMIC STAFFING REQUIREMENTS ---
        # Fetch base constraints (STAFFING_GOAL) to determine the actual target
        base_constraints = mgr.load_constraints(company_id)
        target_date_obj = date.fromisoformat(ts['date_str'])
        
        def get_required_count(b_idx):
            target_val = 0
            for c in base_constraints:
                if c.primitive == ConstraintPrimitive.STAFFING_GOAL and c.team_id == leaver_emp.team_id:
                    if c.date == target_date_obj and c.block_index == b_idx:
                        target_val = c.value; break
                    elif c.date == target_date_obj and c.block_index is None:
                        target_val = c.value
                    elif c.date is None and c.block_index == b_idx:
                        target_val = c.value
                    elif c.date is None and c.block_index is None:
                        target_val = c.value
            if target_val == 0:
                target_val = 1 if "CASHIER" in leaver_team_name else 2
            return target_val

        def get_staff_count(b_idx):
            ids = [eid for eid, blks in current_day_data.items() if b_idx in blks]
            return len([e for e in employees if e.id in ids and e.team_id == leaver_emp.team_id])

        # ---------------------------------------------------------
        # OPTION 1: Leave without Replacement
        # ---------------------------------------------------------
        st.write("### 1️⃣ Option 1: Leave without Replacement")
        
        # Check impact across all leaver blocks
        min_staff_after = 999
        min_req = 0
        for b in remaining_blocks:
            after = get_staff_count(b) - 1
            req = get_required_count(b)
            if after < min_staff_after:
                min_staff_after = after
                min_req = req
            
        if min_staff_after < 1:
            st.warning(f"⚠️ **CRITICAL**: Staffing will drop to ZERO in some blocks!")
        elif min_staff_after < min_req:
            st.info(f"💡 Low staffing warning: {min_staff_after} remaining (Required: {min_req})")
            
        if st.button("✅ Approve (No Cover)", key="opt1_btn", width="stretch"):
            try:
                event_ts = datetime.now().isoformat()
                mgr.record_leave_without_replacement(
                    assignments=assignments, date_str=ts['date_str'],
                    all_blocks=remaining_blocks, emp_id=ts['emp_id'], 
                    company_id=company_id, external_timestamp=event_ts
                )
                st.success("Approved without replacement.")
                st.rerun()
            except Exception as e: st.error(f"Error: {e}")

        st.divider()

        # ---------------------------------------------------------
        # OPTION 2: Localized OT Coverage
        # ---------------------------------------------------------
        st.write("### 2️⃣ Option 2: Localized OT Coverage")
        solver = ShiftManagerSolver(employees, [], teams=teams)
        strategies = solver.rebalance_intra_day(assignments, leaver_emp.team_id, date.fromisoformat(ts['date_str']), ts['emp_id'])
        
        s_ot = next((s for s in strategies if s['id'] == 'LOCAL_OT'), None)
        if s_ot:
            with st.expander(f"🩹 View {s_ot['name']}"):
                st.info(s_ot['description'])
                for detail in s_ot['details']: st.write(f"- {detail}")
                if s_ot['uncovered']: st.warning(f"Note: Blocks {get_shift_string(s_ot['uncovered'])} remain uncovered.")
                if st.button(f"Apply {s_ot['name']}", key="apply_local_ot"):
                    temp_assignments = json.loads(active['assignments_json'])
                    event_ts = datetime.now().isoformat()
                    for b_idx, rep_id in s_ot['coverage_map'].items():
                        mgr.swap_employee_assignment(
                            assignments=temp_assignments,
                            date_str=ts['date_str'],
                            target_blocks=[b_idx],
                            original_emp_id=ts['emp_id'],
                            replacement_emp_id=rep_id,
                            company_id=company_id,
                            external_timestamp=event_ts
                        )
                    still_remaining = s_ot['uncovered']
                    if still_remaining:
                        mgr.record_leave_without_replacement(
                            temp_assignments, ts['date_str'], still_remaining, ts['emp_id'], 
                            company_id, external_timestamp=event_ts
                        )
                    st.success("Localized OT coverage applied and recorded.")
                    st.rerun()
        else:
            st.caption("No localized OT candidates found.")

        st.divider()

        # ---------------------------------------------------------
        # OPTION 3: Optimized Team Rebalance
        # ---------------------------------------------------------
        st.write("### 3️⃣ Option 3: Optimized Team Rebalance")
        s_reb = next((s for s in strategies if s['id'] == 'TEAM_REBALANCE'), None)
        if s_reb:
            with st.expander(f"🧠 View {s_reb['name']}"):
                st.info(s_reb['description'])
                for detail in s_reb['details']: st.write(f"- {detail}")
                if st.button(f"Apply {s_reb['name']}", key="apply_team_reb", type="primary"):
                    temp_assignments = json.loads(active['assignments_json'])
                    event_ts = datetime.now().isoformat()
                    temp_assignments[ts['date_str']] = s_reb['assignments']
                    mgr.db.update_schedule_assignments(active['id'], temp_assignments, timestamp=event_ts)
                    mgr.db.save_leave_record(
                        company_id=company_id,
                        schedule_version_id=active['id'],
                        employee_id=ts['emp_id'],
                        date_obj=date.fromisoformat(ts['date_str']),
                        shift_blocks=remaining_blocks,
                        hours_lost=len(remaining_blocks)*4.0,
                        replacement_id="REBALANCE",
                        replacement_name="Team Redistribution",
                        approved_by="SYSTEM",
                        event_timestamp=event_ts,
                        reason="Optimized Team Rebalance"
                    )
                    st.success("Team rebalance applied. All gaps covered by redistribution.")
                    st.rerun()
        else:
            st.warning("Could not find a mathematically safe rebalance for this team/day.")

        st.divider()

        # ---------------------------------------------------------
        # OPTION 4: Reject Leave
        # ---------------------------------------------------------
        if st.button("❌ Reject Leave Request / Cancel", key="opt4_btn", type="secondary", width="stretch"):
            del st.session_state.target_shift
            if "replacement_candidates" in st.session_state:
                del st.session_state.replacement_candidates
            st.rerun()

    # --- Leave Records Log ---
    st.divider()
    st.subheader("📜 Approved Leave Records")
    
    # Get date range from active schedule
    start_dt = date.fromisoformat(start_date_str)
    end_dt = start_dt + timedelta(days=6)
    
    leave_records = mgr.get_leave_records(company_id, start_dt, end_dt)
    
    if leave_records:
        # Group by (employee_id, date, event_timestamp)
        grouped_records = {}
        for r in leave_records:
            key = (r["employee_id"], r["date"], r.get("event_timestamp") or r["approved_at"])
            if key not in grouped_records:
                grouped_records[key] = []
            grouped_records[key].append(r)

        log_data = []
        for key, records in grouped_records.items():
            eid, r_date, r_ts = key
            emp = next((e for e in employees if e.id == eid), None)
            if not emp: continue
            
            emp_team = next((t.name for t in teams if t.id == emp.team_id), "??")
            
            # Aggregate blocks and replacements
            all_blocks = []
            rep_names = []
            total_hours = 0
            is_approved = True
            is_reb_event = False
            
            for r in records:
                blocks = r["shift_blocks"] if isinstance(r["shift_blocks"], list) else []
                all_blocks.extend(blocks)
                total_hours += r["hours_lost"]
                if r.get("replacement_id") == "REBALANCE":
                    is_reb_event = True
                elif r.get("replacement_name"):
                    rep_names.append(r["replacement_name"])
                
                if r["status"] != "APPROVED":
                    is_approved = False
            
            all_blocks = sorted(list(set(all_blocks)))
            rep_names = sorted(list(set(rep_names)))
            
            # Formatting
            shift_info = get_shift_string(all_blocks) if all_blocks else "Full Day"
            if is_reb_event:
                replacement_display = "Team Redistribution ⚙️"
            elif not rep_names:
                replacement_display = "—"
            else:
                replacement_display = ", ".join(rep_names) + " 🔄"
            
            # Format Date
            display_date = r_date
            if isinstance(display_date, str):
                try:
                    display_date = date.fromisoformat(display_date.split()[0] if " " in display_date else display_date).strftime("%d/%m")
                except:
                    pass

            log_data.append({
                "Employee": emp.name,
                "Team": emp_team[:1],
                "Date": display_date,
                "Shift Lost": shift_info,
                "Hours": f"-{total_hours:.0f}h",
                "Replacement": replacement_display,
                "Status": "✅" if is_approved else "❌"
            })
        
        # Sort log_data by date desc
        log_data.sort(key=lambda x: x["Date"], reverse=True)
        st.dataframe(pd.DataFrame(log_data), width="stretch", hide_index=True)
        
        # Summary
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total", len(leave_records))
        col2.metric("Hours Lost", f"{sum(r['hours_lost'] for r in leave_records):.0f}h")
        col3.metric("Replaced", len([r for r in leave_records if r['replacement_id']]))
        col4.metric("No Cover", len([r for r in leave_records if not r['replacement_id']]))
    else:
        st.info("No leave records for this schedule period.")
