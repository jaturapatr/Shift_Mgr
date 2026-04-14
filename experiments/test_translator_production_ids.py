import os
import json
from dotenv import load_dotenv
from shift_manager.translator import LLMTranslator
from shift_manager.models import MachineConstraint, Employee, Team

load_dotenv()

def test_production_id_mapping():
    translator = LLMTranslator()
    company_id = "COMP_01"
    
    # Production-style UUIDs
    employees = [
        Employee(id="EMP-001", company_id=company_id, team_id="TEAM-CASHIER", name="Alice"),
        Employee(id="UUID-SA-123", company_id=company_id, team_id="TEAM-SERVICE", name="Service A"),
        Employee(id="UUID-SF-456", company_id=company_id, team_id="TEAM-SERVICE", name="Service F"),
    ]
    teams = [
        Team(id="TEAM-CASHIER", company_id=company_id, name="CASHIER"),
        Team(id="TEAM-SERVICE", company_id=company_id, name="SERVICE"),
    ]
    
    instruction = "Avoid Service A and Service F on the same shift"
    
    print(f"Testing Instruction: {instruction}")
    print("-" * 40)
    
    result = translator.manage_logic(instruction, [], employees, teams, company_id)
    
    print(f"Action: {result.get('action')}")
    print(f"Feedback: {result.get('human_feedback')}")
    print("Generated Constraints (Looking for UUIDs):")
    print(json.dumps(result.get("new_constraints", []), indent=2))

if __name__ == "__main__":
    test_production_id_mapping()
