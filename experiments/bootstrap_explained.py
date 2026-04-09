import sys
import os
sys.path.append(os.path.join(os.getcwd(), "src"))
from shift_manager.manager import BusinessManager
from shift_manager.translator import GemmaTranslator

def bootstrap_logic_with_explanations():
    print("--- Bootstrapping Machine Constraints with Explanations ---")
    mgr = BusinessManager()
    translator = GemmaTranslator()
    
    companies = mgr.get_companies()
    for comp in companies:
        print(f"Processing Company: {comp.name}")
        context_rules = mgr.load_context(comp.id)
        
        for rule in context_rules:
            print(f"  - Translating: '{rule.natural_language}'")
            machine_rules = translator.translate_policy(rule.natural_language, comp.id)
            if machine_rules:
                mgr.sync_constraints(comp.id, rule.id, machine_rules)
                print(f"    ✅ Logic & Explanation Recorded.")
            else:
                print(f"    ⚠️ Failed")

if __name__ == "__main__":
    bootstrap_logic_with_explanations()
