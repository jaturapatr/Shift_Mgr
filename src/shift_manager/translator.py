import requests
import json
import os
from datetime import date
from typing import List, Optional, Dict
from dotenv import load_dotenv
from shift_manager.models import (
    MachineConstraint, ConstraintPrimitive, ConstraintOp, 
    ConstraintUnit, ConstraintTargetType, Employee, Team
)

load_dotenv()

class LLMTranslator:
    """
    Translates Natural Language to OR-Tools constraints using OpenAI-compatible APIs.
    Configured via .env file.
    """
    def __init__(self):
        self.api_key = os.getenv("LLM_API_KEY", "no-key-required")
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.model_name = os.getenv("LLM_MODEL_NAME", "gpt-4o-mini")
        
        # Ensure we point to the correct endpoint
        if self.base_url.endswith("/v1"):
            self.api_url = f"{self.base_url}/chat/completions"
        else:
            self.api_url = f"{self.base_url}/v1/chat/completions" if "localhost" in self.base_url else f"{self.base_url}/chat/completions"

    def _get_tools(self) -> List[Dict]:
        """Defines the function schemas for constraint generation."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "add_window_limit",
                    "description": "Sets a window-based work limit (e.g., max hours in 24h, or max days in a week).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target_type": {"type": "string", "enum": ["GLOBAL", "EMPLOYEE"]},
                            "window_size": {"type": "integer", "description": "Size of the window in blocks or days."},
                            "unit": {"type": "string", "enum": ["BLOCKS", "DAYS"]},
                            "op": {"type": "string", "enum": ["<=", ">=", "=="]},
                            "value": {"type": "integer", "description": "The threshold value."},
                            "employee_id": {"type": "string", "description": "Required if target_type is EMPLOYEE."},
                            "explanation": {"type": "string"}
                        },
                        "required": ["target_type", "window_size", "unit", "op", "value", "explanation"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "add_staffing_goal",
                    "description": "Sets required staffing levels for a specific role or time.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "team_id": {"type": "string", "description": "The ID of the team/role."},
                            "value": {"type": "integer", "description": "Number of staff required."},
                            "op": {"type": "string", "enum": ["==", "<=", ">="]},
                            "date": {"type": "string", "description": "YYYY-MM-DD. Optional, global if omitted."},
                            "block_index": {"type": "integer", "description": "0-5. Optional, applies to all blocks if omitted."},
                            "explanation": {"type": "string"}
                        },
                        "required": ["team_id", "value", "op", "explanation"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "add_preference",
                    "description": "Sets personal or relational preferences (Affinity/Separation).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "employee_id": {"type": "string", "description": "Primary employee ID."},
                            "preference_type": {"type": "string", "enum": ["AVOID_TOGETHER", "MUST_TOGETHER", "AVOID_SHIFT"]},
                            "related_employee_id": {"type": "string", "description": "Secondary employee ID for relational rules."},
                            "team_id": {"type": "string", "description": "Shift/Team ID for AVOID_SHIFT preferences."},
                            "explanation": {"type": "string"}
                        },
                        "required": ["employee_id", "preference_type", "explanation"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "add_objective_weight",
                    "description": "Adds a penalty weight to a specific condition (Short/Long/Split shifts).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "value": {"type": "integer", "description": "1=Short, 2=Long, 4=OT, 5=Split."},
                            "weight": {"type": "integer", "description": "Penalty weight value."},
                            "explanation": {"type": "string"}
                        },
                        "required": ["value", "weight", "explanation"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "set_point_fix",
                    "description": "Forces an employee to either work or be off at a specific date/time.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "employee_id": {"type": "string"},
                            "date": {"type": "string", "description": "YYYY-MM-DD"},
                            "value": {"type": "integer", "description": "0 for OFF, 1 for WORK."},
                            "block_index": {"type": "integer", "description": "Optional 0-5. Applies to full day if omitted."},
                            "explanation": {"type": "string"}
                        },
                        "required": ["employee_id", "date", "value", "explanation"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "set_no_repeated_shift",
                    "description": "Prevents any employee from working the exact same shift blocks on consecutive days.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "explanation": {"type": "string"}
                        },
                        "required": ["explanation"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "set_group_balancing",
                    "description": "Ensures total hours are balanced fairly across all members of a specific team.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "team_id": {"type": "string"},
                            "explanation": {"type": "string"}
                        },
                        "required": ["team_id", "explanation"]
                    }
                }
            }
        ]

    def _build_metadata_dictionary(self, employees: List[Employee], teams: List[Team]) -> str:
        """Constructs a clear dictionary for the LLM to avoid type confusion."""
        emp_list = [{"id": e.id, "name": e.name} for e in employees]
        team_list = [{"id": t.id, "name": t.name} for t in teams]
        return f"DATA_DICTIONARY:\nEMPLOYEES: {json.dumps(emp_list)}\nROLES/TEAMS: {json.dumps(team_list)}"

    def _parse_tool_call(self, tool_call: Dict, company_id: str) -> Optional[MachineConstraint]:
        name = tool_call["function"]["name"]
        args_raw = tool_call["function"]["arguments"]
        
        if isinstance(args_raw, str):
            args = json.loads(args_raw)
        else:
            args = args_raw
        
        mapping = {
            "add_window_limit": ConstraintPrimitive.WINDOW_LIMIT,
            "add_staffing_goal": ConstraintPrimitive.STAFFING_GOAL,
            "add_preference": ConstraintPrimitive.PREFERENCE,
            "add_objective_weight": ConstraintPrimitive.OBJECTIVE_WEIGHT,
            "set_point_fix": ConstraintPrimitive.POINT_FIX,
            "set_no_repeated_shift": ConstraintPrimitive.NO_REPEATED_SHIFT,
            "set_group_balancing": ConstraintPrimitive.GROUP_BALANCING
        }
        
        if name not in mapping:
            return None
            
        primitive = mapping[name]
        target_type = args.get("target_type", ConstraintTargetType.GLOBAL)
        if name == "add_staffing_goal": target_type = ConstraintTargetType.TEAM
        if name == "add_preference" or name == "set_point_fix": 
            target_type = ConstraintTargetType.EMPLOYEE
        if name == "set_group_balancing": target_type = ConstraintTargetType.TEAM
        
        return MachineConstraint(
            primitive=primitive,
            target_type=target_type,
            company_id=company_id,
            **args
        )

    def _parse_message_for_tools(self, message: Dict, company_id: str) -> List[MachineConstraint]:
        """Parses tools from both standard tool_calls field and fallback content parsing."""
        constraints = []
        
        # 1. Standard Tool Calls
        if "tool_calls" in message and message["tool_calls"]:
            for tc in message["tool_calls"]:
                c = self._parse_tool_call(tc, company_id)
                if c: constraints.append(c)
        
        # 2. Fallback: Parse from content if it looks like JSON tool call
        content = message.get("content", "").strip()
        if not constraints and content:
            # Try to extract JSON blocks
            import re
            json_blocks = []
            
            # Match markdown blocks
            md_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
            if md_blocks:
                json_blocks.extend(md_blocks)
            else:
                # Try to find something that looks like a JSON object or array
                match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", content)
                if match:
                    json_blocks.append(match.group(0))
            
            for block in json_blocks:
                try:
                    data = json.loads(block)
                    if isinstance(data, dict):
                        if "name" in data and "arguments" in data:
                            c = self._parse_tool_call({"function": data}, company_id)
                            if c: constraints.append(c)
                        elif "tool_calls" in data: # Nested tool calls
                            for tc in data["tool_calls"]:
                                c = self._parse_tool_call(tc, company_id)
                                if c: constraints.append(c)
                    elif isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and "name" in item:
                                c = self._parse_tool_call({"function": item}, company_id)
                                if c: constraints.append(c)
                except:
                    pass
                
        return constraints

    def translate_policy(self, policy_text: str, employees: List[Employee], teams: List[Team], company_id: str) -> List[MachineConstraint]:
        """
        Translates a business policy into mathematical primitives using LLM Tools.
        """
        return self.translate_batch([policy_text], employees, teams, company_id)

    def translate_batch(self, policies: List[str], employees: List[Employee], teams: List[Team], company_id: str) -> List[MachineConstraint]:
        """
        Translates multiple policies in a single LLM call to save tokens.
        """
        metadata = self._build_metadata_dictionary(employees, teams)
        system_prompt = f"""
        You are a CP-SAT Logic Engineer. Your ONLY goal is to call the correct function tools to represent user policies.
        
        {metadata}
        
        ### SYSTEM_POLICY (MANDATORY):
        1. FOR EACH RULE: Identify if it is a Staffing Goal, a Window Limit, or a Preference.
        2. PERSONAL WORK LIMITS: Use 'add_window_limit' tool. Set target_type='EMPLOYEE' and use the 'id' from dictionary.
        3. WINDOW_SIZE: For weekly limits, window_size=7, unit='DAYS'.
        4. OPERATOR: For "can only work N", use op='<='.
        
        ### BATCH MODE:
        You will receive multiple policies. Call the appropriate tool for EACH policy.
        """
        
        user_content = "Please translate the following batch of policies:\n" + "\n".join([f"- {p}" for p in policies])
        return self._call_llm(system_prompt, user_content, company_id)

    def manage_logic(self, user_input: str, current_constraints: List[MachineConstraint], employees: List[Employee], teams: List[Team], company_id: str) -> Dict:
        """
        Determines the ACTION and uses tools to generate resulting primitives.
        """
        constraints_summary = [
            {"index": i, "explanation": c.explanation, "primitive": c.primitive.value, "target": c.target_type.value} 
            for i, c in enumerate(current_constraints)
        ]
        
        metadata = self._build_metadata_dictionary(employees, teams)
        system_prompt = f"""
        You are the Logic Manager for a scheduling system. 
        Analyze the input and use tools to ADD or UPDATE constraints.
        
        {metadata}
        
        Actions:
        - ADD: Call tools to create new constraints.
        - UPDATE: Call tools to replace existing ones.
        - DELETE: Return the action DELETE with target_indices.
        - CONFLICT: Only if logic is mathematically impossible.
        """

        prompt = f"Current Logic Stack: {json.dumps(constraints_summary)}\nUser Instruction: \"{user_input}\""
        
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "tools": self._get_tools(),
            "tool_choice": "auto",
            "temperature": 0
        }

        try:
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=120)
            response.raise_for_status()
            res_data = response.json()["choices"][0]
            message = res_data["message"]
            
            constraints = self._parse_message_for_tools(message, company_id)
            new_constraints = [c.model_dump(exclude_none=True) for c in constraints]

            action = "ADD"
            if "delete" in user_input.lower() or "remove" in user_input.lower():
                action = "DELETE"
            
            return {
                "action": action,
                "target_indices": [], 
                "new_constraints": new_constraints,
                "human_feedback": message.get("content", "Processing complete.")
            }
        except Exception as e:
            return {"action": "ERROR", "human_feedback": f"LLM Communication error: {e}"}

    def _call_llm(self, system_prompt: str, user_content: str, company_id: str) -> List[MachineConstraint]:
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "tools": self._get_tools(),
            "tool_choice": "auto",
            "temperature": 0
        }

        try:
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=120)
            response.raise_for_status()
            message = response.json()["choices"][0]["message"]
            
            return self._parse_message_for_tools(message, company_id)
        except Exception as e:
            print(f"Error in LLM Translation: {e}")
            return []

class GemmaTranslator:
    def __init__(self, model_name: str = "gemma:2b", host: str = "http://localhost:11434"):
        self.model_name = model_name
        self.api_url = f"{host}/api/generate"

    def manage_logic(self, user_input: str, current_constraints: List[MachineConstraint], employees: List[Employee], teams: List[Team], company_id: str) -> Dict:
        """
        The "Command Center" logic. 
        """
        constraints_summary = [
            {"index": i, "explanation": c.explanation, "primitive": c.primitive.value} 
            for i, c in enumerate(current_constraints)
        ]
        
        employee_ids = [e.id for e in employees]
        
        system_prompt = f"""
        You are the Logic Manager for a scheduling system.
        Analyze the User Input and the Current Logic Stack to determine the correct action.
        
        Actions:
        - ADD: Create new primitives.
        - UPDATE: Modify existing primitives based on index.
        - DELETE: Remove existing primitives based on index.
        - CONFLICT: If the input contradicts itself or existing critical rules.
        
        Available Employee IDs: {', '.join(employee_ids)}
        
        Important: If an ID mentioned in the instruction is not in the 'Available Employee IDs' list but appears to be a name (e.g., 'Service A'), treat it as a valid Employee ID. DO NOT flag it as a conflict unless it is a clear system role (e.g., 'CASHIER').
        
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
