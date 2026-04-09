from typing import List
from datetime import date, timedelta, datetime

def get_shift_string(blocks: List[int]) -> str:
    """Convert block indices (0-5) to human-readable shift string."""
    if not blocks:
        return "Day-Off"
    
    blocks.sort()
    current_shift = [blocks[0]]
    all_shifts = []
    
    for i in range(1, len(blocks)):
        if blocks[i] == blocks[i-1] + 1:
            current_shift.append(blocks[i])
        else:
            all_shifts.append(current_shift)
            current_shift = [blocks[i]]
    all_shifts.append(current_shift)
    
    res_parts = []
    for s in all_shifts:
        start_h = s[0] * 4
        end_h = (s[-1] + 1) * 4
        res_parts.append(f"{start_h:02d}:00-{end_h:02d}:00")
    
    return ", ".join(res_parts)

def generate_roster_html(company_name: str, start_date_str: str, employees: List, 
                        assignments: dict, teams: List, leave_records: List = None) -> str:
    """Generate printable HTML representation of the roster."""
    start_dt = date.fromisoformat(start_date_str)
    dates = [start_dt + timedelta(days=i) for i in range(7)]
    date_strs = [d.isoformat() for d in dates]
    
    # Create a lookup for leaves and replacements
    leave_lookup = set()
    replacement_lookup = set()
    if leave_records:
        for r in leave_records:
            leave_lookup.add((r['employee_id'], r['date']))
            if r.get('replacement_id'):
                replacement_lookup.add((r['replacement_id'], r['date']))

    # Use multi-line string then format manually to avoid double-brace confusion in f-strings
    html_head = """
    <html>
    <head>
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333; margin: 40px; }
            .header { text-align: center; margin-bottom: 30px; border-bottom: 2px solid #eee; padding-bottom: 20px; }
            .header h1 { margin: 0; color: #1f4e79; font-size: 28px; }
            .header p { margin: 5px 0; color: #666; }
            table { width: 100%; border-collapse: collapse; margin-top: 20px; table-layout: fixed; }
            th, td { border: 1px solid #dee2e6; padding: 12px 8px; text-align: center; font-size: 13px; }
            th { background-color: #f8f9fa; color: #495057; font-weight: 600; text-transform: uppercase; }
            .emp-col { width: 150px; text-align: left; font-weight: bold; background-color: #fff !important; }
            .role-header { background-color: #e9ecef; text-align: left; padding-left: 15px; font-weight: bold; color: #495057; }
            .shift-cell { color: #0056b3; }
            .off-cell { color: #dc3545; font-style: italic; opacity: 0.6; }
            .leave-cell { color: #ff8c00; font-weight: bold; font-style: italic; }
            tr:nth-child(even) { background-color: #fcfcfc; }
            @media print { body { margin: 0; } button { display: none; } }
        </style>
    </head>
    <body>
    """
    
    header_content = f"""
        <div class="header">
            <h1>{company_name} - Official Roster</h1>
            <p>Week of {start_dt.strftime('%A, %d %B %Y')} to {(start_dt + timedelta(days=6)).strftime('%d %B %Y')}</p>
            <p style="font-size: 11px;">Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
        <table>
            <thead>
                <tr>
                    <th class="emp-col">Employee</th>
                    {"".join(f"<th>{d.strftime('%a %d')}</th>" for d in dates)}
                </tr>
            </thead>
            <tbody>
    """
    
    rows = ""
    for team in teams:
        team_emps = sorted([e for e in employees if e.team_id == team.id], key=lambda x: x.name)
        if team_emps:
            rows += f'<tr><td colspan="8" class="role-header">{team.name} TEAM</td></tr>'
            for emp in team_emps:
                rows += f'<tr><td class="emp-col">{emp.name}</td>'
                for d_str in date_strs:
                    blocks = assignments.get(d_str, {}).get(emp.id, [])
                    if blocks:
                        shift = get_shift_string(blocks)
                        is_rep = (emp.id, d_str) in replacement_lookup
                        display_shift = f"🔄 {shift}" if is_rep else shift
                        rows += f'<td class="shift-cell">{display_shift}</td>'
                    elif (emp.id, d_str) in leave_lookup:
                        rows += '<td class="leave-cell">Leaved</td>'
                    else:
                        rows += '<td class="off-cell">Day-Off</td>'
                rows += '</tr>'
                
    footer = """
            </tbody>
        </table>
        <div style="margin-top: 30px; font-size: 11px; color: #999; text-align: center;">
            &copy; Shift Manager System | Confidential Staff Document
        </div>
    </body>
    </html>
    """
    return html_head + header_content + rows + footer
