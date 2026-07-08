# DevAGI Router Planner LLM Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the stubbed environment-variable JSON LLM path with a real DevAGI OpenAI-compatible client for structured router and planner calls while preserving deterministic test fallbacks.

**Architecture:** Keep `RouterService`, `PlannerService`, and other LLM consumers unchanged at the call site and upgrade only `finsight_agent.infra.llm.LlmClient`. The client should first honor legacy `FINSIGHT_<PROMPT>_JSON` overrides for tests, then fall through to a real HTTP request against DevAGI using environment-based configuration and JSON-only prompting.

**Tech Stack:** Python, `requests`, `unittest`, existing router/planner prompt files, DevAGI OpenAI-compatible `/v1/chat/completions`

---

### Task 1: Add Red Tests For Real LLM Client Path

**Files:**
- Modify: `tests/unit/test_semantic_routing_and_planning.py`
- Create: `tests/unit/test_llm_client.py`
- Test: `tests/unit/test_llm_client.py`

- [ ] **Step 1: Write failing tests for legacy override and real HTTP request composition**
- [ ] **Step 2: Run targeted unit tests and verify failure comes from missing real-client behavior**
- [ ] **Step 3: Keep semantic routing/planning tests unchanged so they still guard fallback contracts**

### Task 2: Implement DevAGI-Compatible LLM Client

**Files:**
- Modify: `backend/src/finsight_agent/infra/llm/client.py`
- Modify: `backend/src/finsight_agent/infra/llm/__init__.py`

- [ ] **Step 1: Preserve `FINSIGHT_<PROMPT>_JSON` override support for deterministic tests**
- [ ] **Step 2: Read runtime config from environment variables for base URL, API key, model, and timeout**
- [ ] **Step 3: Build JSON-only chat completion requests and parse the assistant JSON payload**
- [ ] **Step 4: Raise clear runtime errors when API key is missing or response payload is malformed**

### Task 3: Verify Router Planner Integration

**Files:**
- Test: `tests/unit/test_llm_client.py`
- Test: `tests/unit/test_semantic_routing_and_planning.py`

- [ ] **Step 1: Run the focused LLM client tests**
- [ ] **Step 2: Run semantic routing/planning tests to verify LLM success and fallback still behave correctly**
- [ ] **Step 3: Report exact verification commands and outcomes**
