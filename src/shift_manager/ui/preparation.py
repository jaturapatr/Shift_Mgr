import streamlit as st
from datetime import date, timedelta
from typing import List
import json

from shift_manager.models import (
    DailyRequirement, ShiftBlock, ConstraintPrimitive, MachineConstraint
)
from shift_manager.engine import ShiftManagerSolver
from shift_manager.manager import BusinessManager
from shift_manager.ui.utils import get_shift_string

def render_interactive_roster_lab(mgr: BusinessManager, company_id: str, 
                                   employees: List, all_constraints: List, teams: List):
    """Render Roster Preparation page."""
    st.header("🛠️ Roster Preparation")
    
    start_date = date(2026, 4, 13)
    dates = [start_date + timedelta(days=i) for i in range(7)]
    end_date = dates[-1]
    
    st.markdown(f"**📅 Period: {start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}**")
    st.write("Toggle preferred Days-Off and click Generate to preview the roster.")
    
    date_headers = [d.strftime("%a %d") for d in dates]
    
    col_btn, _ = st.columns([1, 2])
    has_preview = "lab_roster" in st.session_state and st.session_state.lab_roster is not None
    
    with col_btn:
        if not has_preview:
            generate_btn = st.button("⚡ Generate & Preview", type="primary", width="stretch")
        else:
            if st.button("🔓 Edit Requests", width="stretch"):
                del st.session_state.lab_roster
                st.rerun()
            generate_btn = False
    
    # Get day-off preferences
    dayoff_prefs = mgr.get_dayoff_preferences(company_id, dates[0], dates[-1])
    req_set = {(r["employee_id"], r["date"]) for r in dayoff_prefs}

    if not has_preview and generate_btn:
        with st.spinner("Calculating optimal roster..."):
            req_constraints = []
            for pref in dayoff_prefs:
                pref_date = pref["date"]
                if isinstance(pref_date, str):
                    try:
                        pref_date = date.fromisoformat(pref_date.split()[0] if " " in pref_date else pref_date)
                    except:
                        continue
                req_constraints.append(MachineConstraint(
                    primitive=ConstraintPrimitive.POINT_FIX,
                    company_id=company_id,
                    explanation="Day-off preference",
                    employee_id=pref["employee_id"],
                    date=pref_date,
                    value=0,
                    is_temporary=True
                ))
            
            def_reqs = {}
            for t in teams:
                if "CASHIER" in t.name.upper():
                    def_reqs[t.id] = 1
                elif "SERVICE" in t.name.upper():
                    def_reqs[t.id] = 3
            
            reqs = [
                DailyRequirement(
                    date=d,
                    blocks=[ShiftBlock(start_hour=h, team_requirements=def_reqs) for h in [0, 4, 8, 12, 16, 20]]
                )
                for d in dates
            ]
            
            solver = ShiftManagerSolver(employees, reqs, all_constraints + req_constraints, teams=teams)
            result, score = solver.solve()
            
            if score is not None:
                # 1. Create a DRAFT version immediately for lifecycle persistence
                version_id = mgr.create_schedule_version(
                    company_id=company_id,
                    schedule_type="DRAFT",
                    start_date=dates[0],
                    end_date=dates[-1],
                    assignments=result,
                    constraints=all_constraints + req_constraints,
                    score=score
                )
                st.session_state.lab_version_id = version_id
                st.session_state.lab_roster = result
                st.session_state.lab_score = score
                st.success(f"Roster generated! Draft #{version_id} created.")
            else:
                st.error("Infeasible! Try removing some Day-Off requests.")
                st.session_state.lab_roster = None

    # Metrics
    if "lab_roster" in st.session_state and st.session_state.lab_roster:
        m1, m2, m3 = st.columns(3)
        total_h = sum(len(b) for d in st.session_state.lab_roster.values() for b in d.values()) * 4
        m1.metric("Score", f"{st.session_state.lab_score:.2f}")
        m2.metric("Hours", f"{total_h}h")
        m3.metric("Status", "DRAFT PREVIEW")

    # Grid Editor
    st.subheader("📝 Grid Editor")
    
    # Fetch leave records for the draft version if it exists
    leave_lookup = set()
    if "lab_version_id" in st.session_state:
        start_dt = dates[0]
        end_dt = dates[-1]
        lab_leaves = mgr.get_leave_records(company_id, start_dt, end_dt)
        # Filter leaves only for this draft version
        leave_lookup = {(r['employee_id'], r['date']) for r in lab_leaves if r.get('schedule_version_id') == st.session_state.lab_version_id}

    cols = st.columns([2] + [1]*7)
    cols[0].write("**Employee**")
    for i, h in enumerate(date_headers):
        cols[i+1].write(f"**{h}**")

    sorted_emps = sorted(employees, key=lambda x: (x.team_id, x.name))
    
    for emp in sorted_emps:
        cols = st.columns([2] + [1]*7)
        emp_team = next((t.name for t in teams if t.id == emp.team_id), "Unknown")
        cols[0].write(f"**{emp.name}** ({emp_team[:1]})")
        
        for i, d in enumerate(dates):
            d_str = d.isoformat()
            is_off = (emp.id, d_str) in req_set
            
            # --- INTERACTIVE BUTTON LOGIC ---
            if "lab_roster" in st.session_state and st.session_state.lab_roster:
                assigned_blocks = st.session_state.lab_roster.get(d_str, {}).get(emp.id, [])
                if assigned_blocks:
                    shift_str = get_shift_string(assigned_blocks)
                    # UI: Show leaver/overlap highlighting even in Draft
                    label = shift_str
                    btn_type = "secondary"
                    if "target_shift" in st.session_state:
                        ts = st.session_state.target_shift
                        if ts["date_str"] == d_str:
                            if ts["emp_id"] == emp.id:
                                btn_type = "primary"; label = f"🎯 {shift_str}"
                            elif set(assigned_blocks).intersection(set(ts["all_blocks"])):
                                label = f"👥 {shift_str}"

                    if cols[i+1].button(label, key=f"lab_btn_{emp.id}_{d_str}", width="stretch", type=btn_type):
                        st.session_state.target_shift = {
                            "emp_id": emp.id, "emp_name": emp.name,
                            "date_str": d_str, "all_blocks": assigned_blocks,
                            "is_draft": True # Flag to use draft logic
                        }
                        st.rerun()
                elif (emp.id, d_str) in leave_lookup:
                    cols[i+1].markdown("<span style='color:orange; font-weight:bold;'>Leaved</span>", unsafe_allow_html=True)
                elif is_off:
                    cols[i+1].caption(":red[OFF]")
                else:
                    cols[i+1].caption("-")
            else:
                # Before generation, use checkboxes for preferences
                new_off = cols[i+1].checkbox("OFF", value=is_off, key=f"lab_req_{emp.id}_{d_str}", label_visibility="collapsed")
                if new_off != is_off:
                    if new_off: mgr.save_dayoff_preference(company_id, emp.id, d)
                    else: mgr.remove_dayoff_preference(company_id, emp.id, d)
                    st.rerun()

    # ---------------------------------------------------------
    # DRAFT LEAVE REQUEST SECTION (Shared Logic)
    # ---------------------------------------------------------
    if "target_shift" in st.session_state and st.session_state.target_shift.get("is_draft"):
        ts = st.session_state.target_shift
        st.divider()
        st.subheader(f"🔄 [Draft] Leave Request: {ts['emp_name']}")
        
        curr_assignments = st.session_state.lab_roster
        rem_blocks = sorted(curr_assignments.get(ts["date_str"], {}).get(ts["emp_id"], []))
        
        if not rem_blocks:
            st.success("✅ Draft blocks covered.")
            del st.session_state.target_shift; st.rerun()

        start_b, end_b = rem_blocks[0], rem_blocks[-1]
        
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            if st.button("❌ Reject", key="dr_rej", width="stretch"):
                del st.session_state.target_shift; st.rerun()
        with c2:
            if st.button("✅ No Cover", key="dr_nc", width="stretch"):
                mgr.record_leave_without_replacement(curr_assignments, ts['date_str'], rem_blocks, ts['emp_id'], company_id)
                st.session_state.lab_roster = curr_assignments
                st.rerun()
        
        solver = ShiftManagerSolver(employees, [], teams=teams)
        with c3:
            p_cands = [c for c in solver.find_replacement(curr_assignments, ts['emp_id'], date.fromisoformat(ts['date_str']), start_b)
                       if "Shift Extension" in c['recommendation'] and not c['is_rest_violation']]
            if p_cands:
                if st.button(f"Ext Prior ({p_cands[0]['name']})", key="dr_ep"):
                    mgr.swap_employee_assignment(curr_assignments, ts['date_str'], [start_b], ts['emp_id'], p_cands[0]['employee_id'], company_id)
                    st.session_state.lab_roster = curr_assignments
                    st.rerun()
            else: st.button("Ext Prior", disabled=True)
        with c4:
            l_cands = [c for c in solver.find_replacement(curr_assignments, ts['emp_id'], date.fromisoformat(ts['date_str']), end_b)
                       if "Shift Extension" in c['recommendation'] and not c['is_rest_violation']]
            if l_cands:
                if st.button(f"Ext Later ({l_cands[0]['name']})", key="dr_el"):
                    mgr.swap_employee_assignment(curr_assignments, ts['date_str'], [end_b], ts['emp_id'], l_cands[0]['employee_id'], company_id)
                    st.session_state.lab_roster = curr_assignments
                    st.rerun()
            else: st.button("Ext Later", disabled=True)

    # Publish
    if "lab_roster" in st.session_state and st.session_state.lab_roster:
        st.divider()
        if st.button("🚀 Publish to Active Week", type="primary"):
            version_id = st.session_state.lab_version_id
            mgr.publish_draft_version(version_id)
            st.success(f"Draft #{version_id} is now ACTIVE!")
            del st.session_state.lab_roster
            st.rerun()
