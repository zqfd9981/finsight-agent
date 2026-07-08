# Frontend Pseudo-Streaming And Final Response Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Streamlit workbench show the full final response and a pseudo-streaming execution experience without changing backend protocols.

**Architecture:** Keep the backend request model unchanged and implement the experience entirely in the frontend. The analysis page will manage a transient "run in progress" state and render an optimistic stage timeline immediately after submit; once the synchronous request returns, the real envelope will replace the placeholders. The debug page will expose the final response payload alongside routing/planning/execution traces.

**Tech Stack:** Streamlit, existing frontend state helpers, shared response contracts, Python unittest

---

### Task 1: Add failing tests for richer final-response display

**Files:**
- Modify: `tests/unit/test_streamlit_analysis_view.py`
- Modify: `tests/unit/test_streamlit_debug_view.py`

- [ ] **Step 1: Write failing tests for analysis view model**
- [ ] **Step 2: Run the targeted tests and confirm they fail for missing final-response fields**
- [ ] **Step 3: Write failing tests for debug view model final-response exposure**
- [ ] **Step 4: Run the targeted tests and confirm they fail**

### Task 2: Add failing tests for pseudo-streaming transient state

**Files:**
- Create or Modify: `tests/unit/test_streamlit_workbench_state.py`
- Modify: `frontend/streamlit_app/state/workbench_state.py`

- [ ] **Step 1: Add tests for setting, reading, and clearing an in-flight analysis run state**
- [ ] **Step 2: Run the targeted state tests and confirm they fail**

### Task 3: Implement frontend-only final-response rendering and pseudo-streaming state

**Files:**
- Modify: `frontend/streamlit_app/pages/analysis_view.py`
- Modify: `frontend/streamlit_app/pages/debug_view.py`
- Modify: `frontend/streamlit_app/state/workbench_state.py`

- [ ] **Step 1: Add a transient in-flight analysis state helper to session state**
- [ ] **Step 2: Extend analysis view model to expose report blocks, uncertainty notes, and next actions**
- [ ] **Step 3: Render a pseudo-streaming progress timeline while the request is running**
- [ ] **Step 4: Render the full final response after completion**
- [ ] **Step 5: Expose final-response details in the debug view**

### Task 4: Verify targeted frontend behavior

**Files:**
- Test: `tests/unit/test_streamlit_analysis_view.py`
- Test: `tests/unit/test_streamlit_debug_view.py`
- Test: `tests/unit/test_streamlit_workbench_state.py`

- [ ] **Step 1: Run the targeted unit tests for the modified frontend modules**
- [ ] **Step 2: Fix any regressions revealed by the targeted tests**
- [ ] **Step 3: Re-run the same tests until all pass**
