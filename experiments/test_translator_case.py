import os
import json
from dotenv import load_dotenv
from shift_manager.translator import LLMTranslator
from shift_manager.models import MachineConstraint, Employee, Team

load_dotenv()

def test_specific_instruction():
    translator = LLMTranslator()
    company_id = "COMP_01"
    
    # Structured context
    employees = [
        Employee(id="EMP_01", company_id=company_id, team_id="TEAM_CASHIER", name="Alice"),
        Employee(id="EMP_SA", company_id=company_id, team_id="TEAM_SERVICE", name="Service A"),
        Employee(id="EMP_SF", company_id=company_id, team_id="TEAM_SERVICE", name="Service F"),
    ]
    teams = [
        Team(id="TEAM_CASHIER", company_id=company_id, name="CASHIER"),
        Team(id="TEAM_SERVICE", company_id=company_id, name="SERVICE"),
    ]
    
    instruction = "Avoid Service A and Service F on the same shift"
    
    print(f"Testing Instruction: {instruction}")
    print("-" * 40)
    
    result = translator.manage_logic(instruction, [], employees, teams, company_id)
    
    print(f"Action: {result.get('action')}")
    print(f"Feedback: {result.get('human_feedback')}")
    print("Generated Constraints:")
    print(json.dumps(result.get("new_constraints", []), indent=2))

if __name__ == "__main__":
    test_specific_instruction()
