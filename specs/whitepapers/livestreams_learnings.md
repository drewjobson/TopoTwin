# Livestream Learnings: 5-Day AI Agents Course

This document captures the key summaries, structural learnings, and codelab takeaways from the official livestream series for the **5-Day AI Agents: Intensive Vibe Coding Course with Google** (June 15–19, 2026).

* **Playlist URL:** [YouTube Playlist: PLqFaTIg4myu8AFXUjrVhDkUGp0A9kK8CX](https://www.youtube.com/playlist?list=PLqFaTIg4myu8AFXUjrVhDkUGp0A9kK8CX)

---

## Day 1: Introduction to Agents & Vibe Coding

* **Focus:** Moving beyond basic LLM chatbots to autonomous AI agents that act on natural language intent.
* **Core Concept:** **Vibe Coding**—using natural language as the primary interface for software development. The role of the engineer shifts from writing manual syntax to defining intent and instructing models.
* **Key Tooling & Demos:**
  * Introduction to **Antigravity 2.0** and the **Agents CLI** toolchain.
  * Setting up local IDE environments to work alongside agent assistants.
* **Codelabs & Practical Work:**
  * *Antigravity Quickstart:* Getting familiar with the command-line utility and workspace interfaces.
  * *AI Studio to Cloud Run:* Writing a web application in Google AI Studio and deploying it to production using Google Cloud Run.

---

## Day 2: Tools & Interoperability

* **Focus:** Standardizing how agents interact with external APIs, databases, and other systems.
* **Core Concept:** **Model Context Protocol (MCP)**. This open standard solves the $N \times M$ integration problem (connecting $N$ models to $M$ tools) by introducing a standardized protocol layer, reducing integration complexity to $N + M$.
* **Key Tooling & Demos:**
  * **MCP Host, Client, and Server** architecture.
  * Demonstration of the **Kaggle MCP Server** allowing agents to search/download datasets, pull notebook outputs, and submit to competitions.
  * Exploration of machine-to-machine commerce concepts: Agent Payments Protocol (AP2) and Universal Commerce Protocol (UCP).
* **Codelabs & Practical Work:**
  * Exposing custom Python functions as agent-executable tools.
  * Integrating MCP servers into the Antigravity agent configuration.

---

## Day 3: Agent Skills & Context Engineering

* **Focus:** Modularizing agent instructions to keep context windows lean and prevent reasoning degradation.
* **Core Concept:** **Context Rot & Progressive Disclosure**. Massive prompts degrade LLM attention. Progressive disclosure solves this by packing instructions into self-contained "skills" (folders containing `SKILL.md`) that the agent dynamically loads only when triggered by a specific task.
* **Key Tooling & Demos:**
  * **Procedural Memory vs. Semantic/Episodic Memory.** Procedural memory instructs the agent on *how* to perform a multi-step task.
  * Managing a large repository of skills using `manifest.json` for name-to-path mappings and SHA-256 integrity checksums.
* **Codelabs & Practical Work:**
  * Designing a custom skill using the `SKILL.md` format.
  * Invoking and managing subagents with specialized skills via the Agents CLI and ADK (Agent Development Kit).

---

## Day 4: Agent Quality, Security, and Evaluation

* **Focus:** Protecting agent workflows against malicious inputs and evaluating non-deterministic execution paths.
* **Core Concept:** **7-Pillar Security Architecture** for constructing "Effective Trust":
  1. Ephemeral Sandboxing
  2. Defenses against "slopsquatting" (registering hallucinated packages on PyPI/npm)
  3. Red/Blue/Green Security Triad
  4. OpenTelemetry Trajectory Tracing
  5. Least Privilege
  6. Human-in-the-Loop (HITL) gates
  7. SBOM / Provenance Tracking
* **Key Tooling & Demos:**
  * **OpenTelemetry (OTel):** Tracing the agent's intermediate "thought process" (reasoning steps, tool calls) rather than just validating the final output.
  * Identifying **Intent Drift** and **Confused Deputy** vulnerabilities.
* **Codelabs & Practical Work:**
  * Building an expense-approval agent that routes high-value tasks through a Human-in-the-Loop (HITL) review dashboard.
  * Running threat scans and security-gating evaluations on active agents.

---

## Day 5: Spec-Driven Production

* **Focus:** Scaling prototypes to secure, enterprise-grade cloud environments.
* **Core Concept:** **Spec-Driven Development (SDD)**. Behavior-driven Gherkin specifications (Given-When-Then scenarios) serve as the absolute source of truth. The generated code is treated as disposable; if it fails validation, the agent re-runs code generation against the Gherkin specification until it passes.
* **Key Tooling & Demos:**
  * Structuring automated verification suites to check code quality and safety.
  * Deploying agent microservices to Google Cloud at scale, using asynchronous event architectures.
  * Launching the **Capstone Project** (running through July 6, 2026) across tracks: Agents for Good, Agents for Business, Concierge Agents, and Freestyle.
* **Codelabs & Practical Work:**
  * Hosting an agent on Google Cloud and connecting it to a front-end UI.
