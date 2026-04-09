import sqlite3
import os

def clear_roster_data():
    db_path = "roster_memory.db"
    if not os.path.exists(db_path):
        print(f"Database {db_path} not found.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("--- 🗑️ Clearing Roster Operational Data ---")
    
    # Operational tables that link to specific roster versions and transactions
    tables_to_clear = [
        "schedule_versions",
        "employee_state_log",
        "dayoff_preferences",
        "leave_records",
        "attendance_records",
        "quota_usage"
    ]
    
    for table in tables_to_clear:
        try:
            cursor.execute(f"DELETE FROM {table}")
            print(f"✅ Cleared table: {table}")
        except sqlite3.OperationalError as e:
            print(f"⚠️ Table {table} does not exist or error occurred: {e}")

    # Reset auto-increments for IDs to start fresh
    cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('schedule_versions', 'employee_state_log', 'dayoff_preferences', 'leave_records', 'attendance_records', 'quota_usage')")
    
    conn.commit()
    conn.close()
    print("\n🏁 Data reset complete. Master data (Companies, Teams, Employees) preserved.")

if __name__ == "__main__":
    clear_roster_data()
