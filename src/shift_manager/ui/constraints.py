import streamlit as st
import pandas as pd
import json
import os
from typing import List
from shift_manager.models import ConstraintPrimitive, MachineConstraint
from shift_manager.manager import BusinessManager
from shift_manager.translator import GemmaTranslator, LLMTranslator

def render_constraint_management(mgr: BusinessManager, company_id: str, context: List, all_constraints: List):
    """Render the simplified Intent-Based Constraint Management page."""
    st.header("🧠 Logic Command Center")
    st.write("Manage your scheduling rules using natural language.")
    
    # --- 0. TRANSLATOR SELECTION ---
    with st.sidebar:
        st.divider()
        st.header("🤖 Model Selection")
        llm_type = st.radio(
            "Translator Engine",
            ["Cloud LLM (OpenAI-compatible)", "Local SLM (Gemma:2b)"],
            index=0 if os.getenv("LLM_API_KEY") else 1,
            help="Cloud LLM requires .env configuration. Local SLM requires Ollama running."
        )
        
        if llm_type.startswith("Cloud"):
            translator = LLMTranslator()
        else:
            translator = GemmaTranslator()

    employees = mgr.load_employees(company_id)
    teams = mgr.get_teams(company_id)

    # --- 1. SINGLE COMMAND INPUT ---
    with st.container(border=True):
        user_input = st.text_area(
            "What would you like to change?", 
            placeholder="e.g., 'Alice needs next Tuesday off' or 'Set cashier requirement to 2 per block' or 'Remove the 9-hour rest rule'",
            help="The LLM will identify if this is a new rule, an update, or a deletion."
        )
        
        if st.button("🪄 Process Instruction", type="primary"):
            if user_input:
                with st.spinner("Analyzing intent and checking for conflicts..."):
                    result = translator.manage_logic(user_input, all_constraints, employees, teams, company_id)
                    st.session_state.logic_preview = result
            else:
                st.warning("Please enter an instruction first.")

    # --- 2. INTENT PREVIEW & CONFIRMATION ---
    if "logic_preview" in st.session_state:
        res = st.session_state.logic_preview
        st.divider()
        st.subheader("📋 Interpretation")
        
        if res.get("action") == "CONFLICT":
            st.error(f"🚨 Conflict Detected: {res.get('conflict_details')}")
            st.write(res.get("human_feedback"))
        elif res.get("action") == "ERROR":
            st.error(res.get("human_feedback"))
        else:
            st.info(f"**Action:** {res.get('action')}\n\n**Plan:** {res.get('human_feedback')}")
            
            # Show technical details in expander
            with st.expander("Technical Logic Details"):
                st.write(res.get("new_constraints") or f"Affecting indices: {res.get('target_indices')}")

            c1, c2 = st.columns(2)
            if c1.button("✅ Confirm & Apply", type="primary", width="stretch"):
                # EXECUTE THE ACTION
                action = res.get("action")
                indices = res.get("target_indices", [])
                new_data = res.get("new_constraints", [])
                
                if action == "DELETE":
                    # Sort indices descending to delete correctly
                    for i in sorted(indices, reverse=True):
                        if i < len(all_constraints): all_constraints.pop(i)
                elif action == "UPDATE":
                    # Replace first target with first new, delete others, or similar logic
                    for i in sorted(indices, reverse=True):
                        if i < len(all_constraints): all_constraints.pop(i)
                    for item in new_data:
                        all_constraints.append(MachineConstraint(**{**item, "company_id": company_id}))
                elif action == "ADD":
                    for item in new_data:
                        all_constraints.append(MachineConstraint(**{**item, "company_id": company_id}))
                
                # Save
                with open(mgr.constraint_path, "w") as f:
                    json.dump([c.model_dump(exclude_none=True, exclude_defaults=True) for c in all_constraints], f, indent=4)
                
                st.success("Logic stack updated!")
                del st.session_state.logic_preview
                st.rerun()
                
            if c2.button("❌ Cancel", width="stretch"):
                del st.session_state.logic_preview
                st.rerun()

    # --- 3. THE LOGIC STACK (Active Rules) ---
    st.divider()
    st.subheader("📜 Active Logic Stack")
    st.write("These are the business intentions currently driving the engine.")
    
    if all_constraints:
        for idx, c in enumerate(all_constraints):
            with st.container(border=True):
                col_text, col_btn = st.columns([5, 1])
                # Show explanation as the primary header
                label = c.explanation or f"{c.primitive.value} (No explanation)"
                col_text.write(f"**{idx}. {label}**")
                
                if col_btn.button("🗑️", key=f"del_{idx}", help="Remove this rule"):
                    all_constraints.pop(idx)
                    with open(mgr.constraint_path, "w") as f:
                        json.dump([con.model_dump(exclude_none=True, exclude_defaults=True) for con in all_constraints], f, indent=4)
                    st.rerun()
                
                # Hidden technical details
                with col_text.expander("Show machine details"):
                    st.json(c.model_dump(mode='json'))
    else:
        st.info("No active rules found. Use the Command Center above to add some!")

    # Legacy context sync (optional, can be kept or removed)
    with st.expander("🌐 Legacy Business Policies (Natural Language)"):
        for p in context:
            st.write(f"- {p.natural_language}")
