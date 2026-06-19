import os
import re
from typing import Optional, Dict, Any

def resolve_context(template_str: str, override_state: Optional[Dict[str, Any]] = None) -> str:
    """Scans a template string for [[VARIABLE_NAME]] and replaces it with values.
    
    Checks override_state first, then falls back to os.environ.
    If a variable is unresolved, leaves it as-is to prevent silent failures.
    """
    if template_str is None:
        return ""
        
    state_to_check = override_state or {}
    
    # Standard fallback defaults for USGS and CT GIS endpoints
    defaults = {
        "USGS_URL": "https://epqs.nationalmap.gov/v1/json",
        "CT_PARCEL_URL": "https://services3.arcgis.com/3FL1kr7L4LvwA2Kb/arcgis/rest/services/Connecticut_CAMA_and_Parcel_Layer_2024/FeatureServer/0/query"
    }
    
    def replacement(match):
        var_name = match.group(1).strip()
        
        # 1. Check override state
        if var_name in state_to_check and state_to_check[var_name] is not None:
            return str(state_to_check[var_name])
            
        # 2. Check environment variables
        elif var_name in os.environ and os.environ[var_name] is not None:
            return os.environ[var_name]
            
        # 3. Check hardcoded defaults
        elif var_name in defaults:
            return defaults[var_name]
            
        # 4. Leave unresolved
        else:
            return match.group(0)
            
    # Regex matches [[VARIABLE_NAME]]
    return re.sub(r'\[\[([^\]]+)\]\]', replacement, template_str)

if __name__ == "__main__":
    # Test Context Resolver
    test_str = "Connecting to USGS at [[USGS_URL]] for user [[USERNAME]]"
    os.environ["USERNAME"] = "agent_john"
    
    resolved = resolve_context(test_str)
    print("Resolved String:")
    print(resolved)
    print("Success: ", "https://epqs.nationalmap.gov/v1/json" in resolved and "agent_john" in resolved)
    
    # Test with override
    resolved_override = resolve_context(test_str, override_state={"USERNAME": "agent_alice"})
    print("Resolved String with Override:")
    print(resolved_override)
    print("Success Override: ", "agent_alice" in resolved_override)
