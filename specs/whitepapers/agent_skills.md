# Whitepaper Summary: Agent Skills

* **Topic:** Day 3 / Unit 3 of the "5-Day AI Agents: Intensive Vibe Coding Course with Google" (June 2026)
* **Theme:** Lightweight, portable procedural knowledge packages for AI agents.

---

## 1. Executive Summary
As agent architectures scale, forcing an agent to handle complex, multi-domain tasks by adding more text to its system prompt degrades its reasoning, speed, and recall. This phenomenon is known as **context rot**. This whitepaper introduces **Agent Skills**—an open standard for modular, self-contained procedural knowledge packages that can be loaded dynamically, enabling agents to execute complex specialized workflows while keeping context windows lean.

---

## 2. Core Concepts

### A. Context Rot vs. Progressive Disclosure
* **Context Rot:** LLMs perform worse at reasoning, instruction following, and attention when their prompt contains excessive, irrelevant instructions or massive catalogs of tools.
* **Progressive Disclosure:** An architecture where the agent is initialized with a high-level router and minimal core tools. The detailed execution steps (the "procedural memory") are stored as separate "skills" and only loaded when a specific task triggers them.

### B. Types of Agent Memory
* **Semantic Memory:** Factual knowledge (e.g., database schemas, API parameters, vocabulary).
* **Episodic Memory:** Log of past interactions and conversation history.
* **Procedural Memory (Skills):** Step-by-step instructions on *how* to execute a workflow (e.g., how to debug a failing build, how to scrape a website, how to validate a CAD file).

### C. Standard Skill Directory Structure
A standard skill is structured as a self-contained folder:
```
skills/my-specialist-skill/
├── SKILL.md          # Mandatory. Contains YAML frontmatter (name, description) and instructions.
├── scripts/          # Optional. Executable tools, helper scripts, or automation modules.
├── references/       # Optional. Documentation, API specs, or cheat sheets.
└── assets/           # Optional. Files, templates, or resources needed during execution.
```

### D. Central Indexing with `manifest.json`
To allow an agent to discover, load, and version control skills efficiently without scanning the entire disk at startup:
* **The Manifest:** A JSON metadata registry mapping each skill name, version, and folder location.
* **Integrity Validation:** Uses checksums (e.g., SHA-256) inside the manifest to guarantee that the skill contents have not been modified or corrupted.

---

## 3. TopoPlot Implementation & Learning Demonstration
In the TopoPlot workspace and environment, we demonstrate the learnings of this whitepaper through:
1. **Local Skill Integration:** The workspace inherits global skills (such as `accidental-data-loss-prevention` and `managing-python-dependencies`) and uses local config skills.
2. **Standardized Instructions:** Custom skill layouts (like `SKILL.md`) are used to package domain-specific guidelines (e.g., 3D mesh design rules, parcel boundary winding checks), preventing prompt bloat in the main orchestrator agent.
