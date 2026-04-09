import streamlit as st
import pandas as pd
from shift_manager.manager import BusinessManager

def render_archive(mgr: BusinessManager, company_id: str):
    """Render Archive page."""
    st.header("🗄️ Archive & History")
    
    # Show schedule version history
    st.subheader("📜 Schedule Version History")
    versions = mgr.get_schedule_version_history(company_id)
    
    if versions:
        version_data = []
        for v in versions:
            version_data.append({
                "ID": v['id'],
                "Type": v['schedule_type'],
                "Start Date": v['start_date'],
                "End Date": v['end_date'],
                "Score": f"{v['score']:.2f}" if v['score'] else "-",
                "Created": v['created_at'][:10],
                "By": v['created_by']
            })
        st.dataframe(pd.DataFrame(version_data), width="stretch", hide_index=True)
    else:
        st.info("No schedule versions found.")
    
    st.divider()
    st.subheader("🏷️ Archive Current Active")
    
    active = mgr.get_active_schedule_version(company_id)
    if active:
        if st.button("🗄️ Archive Active Schedule", type="primary"):
            mgr.archive_schedule_version(active['id'])
            st.success("Active schedule archived!")
            st.rerun()
    else:
        st.info("No active schedule to archive.")
