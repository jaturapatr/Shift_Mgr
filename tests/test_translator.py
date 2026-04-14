import unittest
from unittest.mock import patch, MagicMock
import json
import requests
from shift_manager.translator import LLMTranslator, GemmaTranslator
from shift_manager.models import MachineConstraint, ConstraintPrimitive, Employee, Team

class TestTranslator(unittest.TestCase):
    def setUp(self):
        self.llm = LLMTranslator()
        self.company_id = "COMP_01"
        self.employees = [Employee(id="EMP_01", company_id=self.company_id, team_id="TEAM_A", name="Alice")]
        self.teams = [Team(id="TEAM_A", company_id=self.company_id, name="Team A")]

    @patch('requests.post')
    def test_translate_policy_success(self, mock_post):
        # Setup mock response with tool_calls
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "function": {
                            "name": "add_window_limit",
                            "arguments": json.dumps({
                                # "target_type" is handled by _parse_tool_call mapping
                                "window_size": 7,
                                "unit": "DAYS",
                                "op": "<=",
                                "value": 6,
                                "explanation": "Max 6 work days",
                                "employee_id": "EMP_01"
                            })
                        }
                    }]
                }
            }]
        }
        mock_post.return_value = mock_response

        # Execute
        results = self.llm.translate_policy("1 day off per week", self.employees, self.teams, self.company_id)

        # Verify
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].primitive, ConstraintPrimitive.WINDOW_LIMIT)
        self.assertEqual(results[0].value, 6)
        self.assertEqual(results[0].company_id, self.company_id)
        mock_post.assert_called_once()

    @patch('requests.post')
    def test_manage_logic_add(self, mock_post):
        # Setup mock response for ADD action with tool_calls
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": "Adding cashier requirement",
                    "tool_calls": [{
                        "function": {
                            "name": "add_staffing_goal",
                            "arguments": json.dumps({
                                "team_id": "TEAM_CASHIER",
                                "value": 2,
                                "op": "==",
                                "explanation": "Adding cashier requirement"
                            })
                        }
                    }]
                }
            }]
        }
        mock_post.return_value = mock_response

        # Execute
        result = self.llm.manage_logic("Need 2 cashiers", [], self.employees, self.teams, self.company_id)

        # Verify
        self.assertEqual(result["action"], "ADD")
        self.assertEqual(len(result["new_constraints"]), 1)
        self.assertEqual(result["new_constraints"][0]["primitive"], ConstraintPrimitive.STAFFING_GOAL.value)

    @patch('requests.post')
    def test_manage_logic_conflict(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": "Too many staff requested. Cannot apply.",
                    "tool_calls": []
                }
            }]
        }
        mock_post.return_value = mock_response

        # Execute
        result = self.llm.manage_logic("Need 50 cashiers", [], self.employees, self.teams, self.company_id)

        # Verify
        self.assertEqual(result["action"], "ADD") 
        self.assertIn("Too many staff requested", result["human_feedback"])

    @patch('requests.post')
    def test_llm_timeout_handling(self, mock_post):
        # Simulate timeout
        mock_post.side_effect = requests.exceptions.Timeout("Read timed out")

        # Execute
        result = self.llm.manage_logic("Slow request", [], self.employees, self.teams, self.company_id)

        # Verify
        self.assertEqual(result["action"], "ERROR")
        self.assertIn("Communication error", result["human_feedback"])

    @patch('requests.post')
    def test_gemma_translator_basic(self, mock_post):
        gemma = GemmaTranslator()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": json.dumps([
                {"primitive": "POINT_FIX", "employee_id": "EMP_01", "date": "2026-04-14", "value": 0}
            ])
        }
        mock_post.return_value = mock_response

        results = gemma.translate_requests("Alice off Tuesday", ["EMP_01"], self.company_id)
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].primitive, ConstraintPrimitive.POINT_FIX)

if __name__ == '__main__':
    unittest.main()
