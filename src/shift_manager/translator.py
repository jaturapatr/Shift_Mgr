import requests
import json
from datetime import date
from typing import List, Optional, Dict
from shift_manager.models import MachineConstraint, ConstraintPrimitive, ConstraintOp, ConstraintUnit

class GemmaTranslator:
    def __init__(self, model_name: str = "gemma:2b", host: str = "http://localhost:11434"):
        self.model_name = model_name
        self.api_url = f"{host}/api/generate"

    def manage_logic(self, user_input: str, current_constraints: List[MachineConstraint], employee_ids: List[str], company_id: str) -> Dict:
        """
        The "Command Center" logic. 
        Determines the ACTION (Add, Update, Delete) and the resulting primitives.
        """
        constraints_summary = [
            {"index": i, "explanation": c.explanation, "primitive": c.primitive.value} 
            for i, c in enumerate(current_constraints)
        ]
        
        system_prompt = f"""
        You are the Logic Manager for a scheduling system.
        Analyze the User Input and the Current Logic Stack to determine the correct action.
        
        Actions:
        - ADD: Create new primitives.
        - UPDATE: Modify existing primitives based on index.
        - DELETE: Remove existing primitives based on index.
        
        Available Employee IDs: {', '.join(employee_ids)}
        
        Return JSON:
        {{
            "action": "ADD" | "UPDATE" | "DELETE" | "CONFLICT",
            "target_indices": [int], 
            "new_constraints": [MachineConstraint objects],
            "human_feedback": "Explain what you are doing",
            "conflict_details": "If CONFLICT, explain why"
        }}
        """

        prompt = f"""
        Current Logic Stack: {json.dumps(constraints_summary)}
        User Instruction: "{user_input}"
        """

        payload = {
            "model": self.model_name,
            "prompt": f"{system_prompt}\n\n{prompt}\n\nJSON Output:",
            "stream": False,
            "format": "json"
        }

        try:
            response = requests.post(self.api_url, json=payload, timeout=45)
            response.raise_for_status()
            return json.loads(response.json().get("response", "{}"))
        except Exception as e:
            return {"action": "ERROR", "human_feedback": f"SLM Communication error: {e}"}

    def translate_requests(self, user_input: str, employee_ids: List[str], company_id: str, current_year: int = 2026) -> List[MachineConstraint]:
        system_prompt = f"""
        You are a Logic Architect for a gas station scheduling system.
        Translate manager instructions into a JSON list of MachineConstraint objects using primitives.
        
        Available Employee IDs: {', '.join(employee_ids)}
        Current Year: {current_year}
        
        Primitives:
        - POINT_FIX: Set a specific block/day for an employee to a value (0=off, 1=work).
          Params: employee_id, date, value, block_index (optional)
        - STAFFING_GOAL: Set required staff count for a role/block.
          Params: date, role ("CASHIER"|"SERVICE"), block_index, value, op ("=="|"<="|">=")
        
        Output format: [{{"primitive": "PRIMITIVE_NAME", ...params}}]
        
        Example: "Alice wants next Tuesday off."
        Output: [{{"primitive": "POINT_FIX", "employee_id": "EMP_01", "date": "2026-04-14", "value": 0}}]
        """

        payload = {
            "model": self.model_name,
            "prompt": f"{system_prompt}\n\nManager Input: \"{user_input}\"\n\nJSON Output:",
            "stream": False,
            "format": "json"
        }

        try:
            response = requests.post(self.api_url, json=payload)
            response.raise_for_status()
            data = response.json()
            parsed = json.loads(data.get("response", "[]"))
            return [MachineConstraint(**{**item, "company_id": company_id}) for item in parsed]
        except Exception as e:
            print(f"Error translating request: {e}")
            return []

    def translate_policy(self, policy_text: str, company_id: str) -> List[MachineConstraint]:
        """
        Translates a business policy into mathematical primitives.
        """
        system_prompt = """
        You are a CP-SAT Logic Engineer. Translate a policy into a JSON list of MachineConstraint primitives.
        
        Primitives:
        - WINDOW_LIMIT: sum of work in window <= value.
          Params: window_size, unit ("BLOCKS"|"DAYS"), op ("<="|">="), value
        - STAFFING_GOAL: global staffing rules.
          Params: op, value (if applies to all blocks)
        - OBJECTIVE_WEIGHT: term added to minimization objective.
          Params: value (code: 4=OT penalty), weight (usually 2)
        - GROUP_BALANCING: Balance hours for a role.
        
        Mapping Rules:
        - "9 hours rest": Must be translated to WINDOW_LIMIT(window_size=4, unit="BLOCKS", op="<=", value=1). Explain: "9 hours is > 2 blocks (8 hours), so 3 blocks must be skipped. Window size is 4 with max 1 work block."
        - "1 day off/week": WINDOW_LIMIT(window_size=7, unit="DAYS", op="<=", value=6). Explain: "In any 7-day window, total working days must be at most 6."
        - "allow OT but not prefer": OBJECTIVE_WEIGHT(value=4, weight=2). Explain: "Adds a soft penalty for every hour worked to discourage unnecessary shifts."
        
        Output format:
        [{"primitive": "...", "explanation": "...", ...params}]
        
        Output ONLY the JSON list. Do not explain outside the JSON.
        """

        payload = {
            "model": self.model_name,
            "prompt": f"{system_prompt}\n\nTranslate to Primitives with Explanation: \"{policy_text}\"\n\nJSON Output:",
            "stream": False,
            "format": "json"
        }

        try:
            response = requests.post(self.api_url, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            raw_output = data.get("response", "[]")
            parsed = json.loads(raw_output)
            # Pass all fields through, Pydantic will validate
            return [MachineConstraint(**{**item, "company_id": company_id}) for item in parsed]
        except Exception as e:
            print(f"Error translating policy: {e}")
            return []
