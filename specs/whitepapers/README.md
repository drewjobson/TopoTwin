# Kaggle 5-Day AI Agents Course: Whitepaper Index

This directory documents the core learnings and architectures from the **5-Day AI Agents: Intensive Vibe Coding Course with Google** (June 2026). These summaries serve as theoretical blueprints for the building we are doing in the **TopoPlot (TopoTwin)** repository, demonstrating how each concept is practically implemented.

---

## Documented Whitepapers

### 1. [Spec-Driven Production Grade Development in the Age of Vibe Coding](spec_driven_development.md)
* **Author:** Lee Boonstra (Unit 5)
* **Focus:** Bridging the gap from fragile vibe-coded prototypes to scalable enterprise software using behavior-driven Gherkin specifications (where code is disposable and specifications are the source of truth).
* **TopoPlot Demonstration:** Implemented in [specs/topo_spec.md](../topo_spec.md).

### 2. [Vibe Coding Agent Security and Evaluation](agent_security_evaluation.md)
* **Focus:** Security frameworks for non-deterministic agent workflows, covering the 7-Pillar Security Architecture, ephemeral sandboxing, slopsquatting defenses, and OpenTelemetry trajectory tracing.
* **TopoPlot Demonstration:** Implemented via role-based access gating, semantic coordinate interception, and automated `vibe_trajectory.jsonl` logging.

### 3. [Agent Skills](agent_skills.md)
* **Focus:** A modular standard (using `SKILL.md` and `manifest.json`) to package procedural knowledge, preventing context rot and prompts bloat by only loading specialized instructions dynamically when needed.
* **TopoPlot Demonstration:** Showcased through local integration of skills (like python dependency management and data-loss prevention) to restrict file mutations and verify builds.

### 4. [Agent Tools and Interoperability (with MCP)](agent_tools_interoperability.md)
* **Focus:** Standardizing agent-to-tool connections using the Model Context Protocol (MCP), decoupling reasoning models (hosts/clients) from execution environments (servers), and introducing the Kaggle MCP Server.
* **TopoPlot Demonstration:** Orchestrates API queries (ArcGIS, Nominatim, UConn DEM ImageServer) using standardized, modular Python interfaces.

### 5. [The New SDLC with Vibe Coding](new_sdlc_vibe_coding.md)
* **Authors:** Addy Osmani, Shubham Saboo, Sokratis Kartakis
* **Focus:** Redefining the software development lifecycle from writing syntax to designing the agent harness ($\text{Agent} = \text{Model} + \text{Harness}$), moving the developer bottleneck to design and verification.
* **TopoPlot Demonstration:** Wraps the core generative model in a strict validation-driven self-repair loop and evaluation suit.

---

## Livestream Course Lectures

### [YouTube Course Livestream Learnings](livestreams_learnings.md)
* **Source:** [YouTube Playlist: PLqFaTIg4myu8AFXUjrVhDkUGp0A9kK8CX](https://www.youtube.com/playlist?list=PLqFaTIg4myu8AFXUjrVhDkUGp0A9kK8CX)
* **Focus:** Summary of core lessons, live coding sessions, and codelab objectives covered during the daily video broadcasts.

