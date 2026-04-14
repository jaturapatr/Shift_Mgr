# ⛽ Shift Manager - User Manual

## 1. Introduction
Shift Manager is a high-performance roster management application built with Python and Streamlit. It leverages a custom constraint-based optimization engine to ensure your organization operates 24/7 while respecting employee rest periods and staffing requirements.

## 2. Quick Start Guide (Roster in 5 Minutes) 🚀
The fastest way to get your first roster running:

1.  **Launch the App**: Run `streamlit run streamlit_app.py` in your terminal.
2.  **Navigation**: Use the Sidebar to select "System Management".
3.  **Data Setup**: Use the "Reset Database" or "Import Defaults" button if you are starting fresh.
4.  **Define Staff**:
    - Go to "System Management" -> "Manage Employees".
    - Ensure at least 1 **CASHIER** and 2 **SERVICE** staff are added to a Team.
5.  **Configure Rules**:
    - Go to "Constraint Management".
    - Activate policies like "Operate 24/7" and "1 day-off per week".
6.  **Create Roster**:
    - Navigate to "Roster Preparation".
    - Select a Date Range.
    - Click **"Generate Optimized Roster"**.
7.  **Review**: Check the "Active Roster" tab to see your new schedule.

## 3. Setup & Requirements 💻

### System Requirements
- **OS**: Windows (optimized for PowerShell).
- **Python**: 3.8+ (3.13 recommended).
- **Dependencies**: Streamlit, Pandas, SQlite3.

### Installation
1.  **Clone the Repository**.
2.  **Create Virtual Environment**:
    ```powershell
    python -m venv venv
    ```
3.  **Activate Environment**:
    ```powershell
    .\venv\Scripts\Activate.ps1
    ```
4.  **Install Dependencies**:
    ```powershell
    pip install -e .
    ```

## 4. Interface Guide 🧭

### Sidebar
- **Context Selection**: Toggle between different companies.
- **Navigation**: Switching between Roster, Preparation, Constraints, History, and System settings.
- **Staff Status**: Real-time tracking of employee accumulated hours. Clicking an employee shows their specific detail view.

### Active Roster
A read-only view of the currently published shift schedule. It displays a grid of time blocks and assigned personnel.

### Roster Preparation (The Lab) 🧪
This is the core of the application.
- **Interactive Grid**: Manually assign or remove staff from specific blocks.
- **Engine Logic**: Use the "Solver" to automatically fill gaps based on constraints.
- **Publishing**: Once satisfied, "Commit" the roster to make it active.

## 5. Constraint Management & Logic 🧠
The engine uses **Policies** to generate valid rosters.

- **Natural Language Policies**: Human-readable rules (e.g., "At least 8 hours rest").
- **Technical Constraints**:
    - **WINDOW_LIMIT**: Restricts how many shifts occur in a time window.
    - **STAFF_GOAL**: Ensures minimum coverage for specific roles (Cashier/Service).
    - **OBJECTIVE_WEIGHT**: Penalizes undesirable patterns (like 12h shifts or split shifts) to favor more balanced schedules.

## 6. Maintenance & Safety 🛠️
Manage your data effectively in "System Management":
- **Backup/Restore**: Keep your `roster_memory.db` safe.
- **Data Cleanup**: Remove old archives to keep the system fast.

## 7. Troubleshooting ❓
- **App won't start**: Ensure `venv` is activated and `pip install` completed.
- **Solver fails to find solution**: Check if you have enough staff to fulfill the "STAFF_GOAL" constraints (e.g., 24/7 operation requires at least 4-5 employees per role).
- **Database Error**: Ensure no other process is locking `roster_memory.db`.
