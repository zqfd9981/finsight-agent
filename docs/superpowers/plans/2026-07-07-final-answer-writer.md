# Final Answer Writer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an LLM-written `answer_markdown` to final responses while preserving the existing structured trace and evidence fields.

**Architecture:** Extend the shared final response contract with a new free-form user-facing answer field. Add a dedicated reporting-layer final writer that consumes a compact structured payload, uses the existing LLM client for structured JSON generation, and degrades safely to a minimal fallback answer when the writer is unavailable. Keep routing, planning, and stage execution unchanged; only `synthesize_report`, `synthesize_brief_answer`, reporting service, and frontend rendering need to understand the new field.

**Tech Stack:** Python dataclasses, existing `LlmClient`, Streamlit frontend, unittest

---

### Task 1: Lock the new contract with failing tests

**Files:**
- Modify: `tests/unit/test_orchestrator_stage_runners.py`
- Modify: `tests/unit/test_streamlit_api_client.py`
- Modify: `tests/unit/test_streamlit_analysis_view.py`

- [ ] **Step 1: Add a failing test asserting report responses contain `answer_markdown`**
- [ ] **Step 2: Add a failing API client parse test asserting `answer_markdown` survives round trip**
- [ ] **Step 3: Add a failing frontend view-model test asserting analysis view prefers `answer_markdown`**
- [ ] **Step 4: Run targeted tests and confirm they fail for the missing field**

### Task 2: Implement the shared contract and reporting writer

**Files:**
- Modify: `shared/contracts/final_response.py`
- Create: `backend/src/finsight_agent/capabilities/reporting/final_answer_writer.py`
- Modify: `backend/src/finsight_agent/capabilities/reporting/service.py`

- [ ] **Step 1: Extend `FinalResponse` with `answer_markdown`**
- [ ] **Step 2: Add a reporting-layer final writer that returns `answer_markdown` and confidence**
- [ ] **Step 3: Wire `ReportingService` to call the writer for brief and report responses**
- [ ] **Step 4: Add a safe fallback answer when the writer call fails**

### Task 3: Feed final-writer context from orchestrator stages

**Files:**
- Modify: `backend/src/finsight_agent/control_plane/orchestrator/stage_runners/synthesize_report.py`
- Modify: `backend/src/finsight_agent/control_plane/orchestrator/stage_runners/synthesize_brief_answer.py`

- [ ] **Step 1: Build a compact final-writer payload from report-stage structured outputs**
- [ ] **Step 2: Pass strategy-aware evidence counts and uncertainty notes into reporting**
- [ ] **Step 3: Pass brief-answer context for metric lookups into reporting**

### Task 4: Show the final answer in the frontend

**Files:**
- Modify: `frontend/streamlit_app/pages/analysis_view.py`
- Modify: `frontend/streamlit_app/pages/debug_view.py`
- Modify: `frontend/streamlit_app/api_client.py`

- [ ] **Step 1: Parse `answer_markdown` from the API payload**
- [ ] **Step 2: Render `answer_markdown` as the primary user-facing answer in analysis view**
- [ ] **Step 3: Expose `answer_markdown` in debug view final response details**

### Task 5: Verify end to end with targeted tests

**Files:**
- Test: `tests/unit/test_orchestrator_stage_runners.py`
- Test: `tests/unit/test_streamlit_api_client.py`
- Test: `tests/unit/test_streamlit_analysis_view.py`
- Test: `tests/unit/test_streamlit_debug_view.py`

- [ ] **Step 1: Run targeted unit tests for reporting, API client, and Streamlit views**
- [ ] **Step 2: Fix any regressions surfaced by the tests**
- [ ] **Step 3: Re-run the same tests until all pass**
