import os
import yaml

# Path to policies.yaml
POLICY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "policies.yaml")

class PolicyService:
    def __init__(self, role: str = "viewer", env: str = "production"):
        self.role = role
        self.env = env
        self.config = self._load_policies()
        
        # Semantic blacklist (e.g. Area 51 bounding box)
        self.semantic_blacklist = {
            "name": "Restricted Area 51 Air Force Base",
            "lat_min": 37.20,
            "lat_max": 37.26,
            "lon_min": -115.85,
            "lon_max": -115.75
        }

    def _load_policies(self) -> dict:
        if not os.path.exists(POLICY_FILE):
            # Fallback hardcoded defaults if file is missing
            return {
                "environments": {"production": {"blocked_tools": ["raw_shell_execute"]}},
                "roles": {"viewer": {"allowed_tools": ["geocode_address", "query_ct_parcel", "get_elevation_grid", "build_solid_mesh", "validate_mesh", "create_plotly_visual", "write_binary_stl"]}}
            }
        with open(POLICY_FILE, "r") as f:
            return yaml.safe_load(f)

    def is_tool_allowed(self, tool_name: str) -> bool:
        """Structural Gating: Intercepts tool calls and verifies environment/role permissions."""
        # 1. Check Environment Blocks
        env_config = self.config.get("environments", {}).get(self.env, {})
        blocked_tools = env_config.get("blocked_tools", [])
        if tool_name in blocked_tools:
            print(f"[SECURITY CHECK - BLOCKED] Tool '{tool_name}' is blocked in environment '{self.env}'.")
            return False
            
        # 2. Check Role Permissions
        role_config = self.config.get("roles", {}).get(self.role, {})
        allowed_tools = role_config.get("allowed_tools", [])
        
        if "*" in allowed_tools:
            return True
            
        if tool_name in allowed_tools:
            return True
            
        print(f"[SECURITY CHECK - DENIED] Role '{self.role}' does not have permission to execute tool '{tool_name}'.")
        return False

    def check_action_semantic(self, tool_name: str, arguments: dict) -> bool:
        """Semantic Gating: Checks arguments for policy violations (e.g., PII leaks or restricted zones)."""
        # Check coordinate queries for restricted zones
        if tool_name in ["get_elevation_grid", "query_ct_parcel"]:
            lat = arguments.get("lat") or arguments.get("center_lat")
            lon = arguments.get("lon") or arguments.get("center_lon")
            
            if lat is not None and lon is not None:
                # Check against blacklisted zones
                b = self.semantic_blacklist
                if b["lat_min"] <= lat <= b["lat_max"] and b["lon_min"] <= lon <= b["lon_max"]:
                    print(
                        f"[SECURITY CHECK - VIOLATION] Semantic Gating intercepted call to '{tool_name}' "
                        f"targeting Restricted Area: '{b['name']}' at coordinates ({lat}, {lon})."
                    )
                    return False
        return True

if __name__ == "__main__":
    # Test Policy Service
    p = PolicyService(role="viewer", env="production")
    print("Test structural allowed: ", p.is_tool_allowed("geocode_address") == True)
    print("Test structural blocked: ", p.is_tool_allowed("raw_shell_execute") == False)
    
    # Test semantic gating
    args_safe = {"center_lat": 41.2781, "center_lon": -72.5273}
    args_unsafe = {"center_lat": 37.23, "center_lon": -115.80}
    print("Test semantic safe: ", p.check_action_semantic("get_elevation_grid", args_safe) == True)
    print("Test semantic unsafe: ", p.check_action_semantic("get_elevation_grid", args_unsafe) == False)
