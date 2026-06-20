# Whitepaper Summary: Vibe Coding Agent Security and Evaluation

* **Topic:** Day 4 / Unit 4 of the "5-Day AI Agents: Intensive Vibe Coding Course with Google" (June 2026)
* **Theme:** Establishing security and evaluation frameworks in AI agent workflows.

---

## 1. Executive Summary
As autonomous AI agents are granted access to execute commands, modify repositories, and read credentials, they present a significant security and stability risk. Because generative AI code pathways are non-deterministic, traditional application-level security and testing are insufficient. This paper details the necessary safeguards, including sandboxing, dependency validation, and trajectory-level evaluation.

---

## 2. Core Security Pillars

### A. The 7-Pillar Security Architecture
To construct "Effective Trust" around autonomous agents, developers must implement seven key controls:
1. **Ephemeral Sandboxing:** Isolating all agent executions in disposable environments (e.g., lightweight containers or microVMs) to prevent host contamination.
2. **Defenses Against Slopsquatting:** Actively scanning suggested dependencies for hallucinated package names (phantom dependencies) before they are fetched, preventing attackers from injecting malicious code via public PyPI or npm registers.
3. **Active Red/Blue/Green Security Triad:**
   * *Red Team:* Proactively probing and attacking the agent system (e.g., prompt injections) to identify weaknesses.
   * *Blue Team:* Real-time monitoring and threat detection of agent activities.
   * *Green Team:* Designing the guardrails and self-healing policies to patch discovered vulnerabilities.
4. **OpenTelemetry Trajectory Evaluation:** Structuring and tracing agent reasoning steps, API requests, and tool calls to detect loop cycles, drift, or malicious intent.
5. **Least Privilege & Zero Ambient Authority:** Restricting credentials, file access, and network routing to the bare minimum required for the task.
6. **Human-in-the-Loop (HITL) Gates:** Requiring explicit human approval for high-risk operations (e.g., database writes, deployments, or remote code execution).
7. **SBOM & Provenance Tracking:** Documenting and signing all software assets and dependencies generated or consumed by the agent.

### B. Trajectory Observability
* **Intent Drift:** Occurs when an agent, through sequential planning steps, loses track of the user's original objective and goes off-task.
* **Confused Deputy Problem:** When an agent is tricked (via prompt injection or malicious input) into using its elevated permissions to perform actions on behalf of an attacker.
* **Solution:** Tracing the full execution graph using OpenTelemetry (OTel) to evaluate intermediate reasoning steps, ensuring the agent stays within semantic bounds.

---

## 3. TopoPlot Implementation & Learning Demonstration
In the TopoPlot workspace, we demonstrate the learnings of this whitepaper through:
1. **Structural and Semantic Gating:**
   * *Role-Based Gating:* Restricting administrative shell tools (`raw_shell_execute`) when running under the `viewer` role in production.
   * *Parameter Gating:* Intercepting and blocking GIS coordinate queries targeting restricted locations (e.g., sensitive military bases).
2. **Watertight Manifold & Volume Checks:** Implementing a strict validation step via `trimesh` to ensure physical safety and compatibility of the output model before allowing export.
3. **Trajectory Serialization:** Writing every execution step, reasoning path, and validation attempt to a local `vibe_trajectory.jsonl` file, forming a complete, audit-ready trajectory log.
