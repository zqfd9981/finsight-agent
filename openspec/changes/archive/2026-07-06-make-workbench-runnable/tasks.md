## 1. Backend HTTP Entry

- [x] 1.1 Add failing TestClient tests at `tests/integration/test_backend_api_app.py` covering: routes registered; POST `/api/v1/analysis/turns` 200 + envelope; missing `query` → 422; GET `/api/v1/eval/event-cases` 200 + list; POST `/api/v1/eval/event-replay` 200 + summary/records
- [x] 1.2 Implement `build_app()` in `backend/apps/api/app_factory.py` with FastAPI + CORS + 3 routes reusing `handle_analysis_turn` / `handle_event_cases` / `handle_event_replay`
- [x] 1.3 Add `app = build_app()` to `backend/apps/api/main.py` while keeping existing `main()` dict for back-compat
- [x] 1.4 Verify `python -m unittest tests.integration.test_backend_api_app tests.unit.test_project_skeleton -v` passes
- [x] 1.5 Commit: `feat(backend): wire FastAPI app factory and workbench routes`

## 2. Frontend HTTP Client and YAML Config

- [x] 2.1 Add failing tests in `tests/unit/test_streamlit_config_resolver.py` for defaults-fallback and round-trip reading of `app.workbench` block
- [x] 2.2 Add failing tests in `tests/unit/test_streamlit_api_client.py` for `send_request` URL composition, non-2xx raises `RuntimeError`, and `fetch_event_replay` round-trip (mock `requests.post`)
- [x] 2.3 Append `app.workbench` block to `config/app.yaml` with `mode / backend_host / backend_port / backend_base_url / frontend_host / frontend_port`
- [x] 2.4 Implement `frontend/streamlit_app/config_resolver.py` with `load_app_config()` and `resolve_workbench_config()`
- [x] 2.5 Extend `frontend/streamlit_app/api_client.py` with `send_request` / `fetch_event_cases` / `fetch_event_replay` using `requests` and YAML-driven base URL; keep existing `build_*` / `parse_*` intact
- [x] 2.6 Verify `python -m unittest tests.unit.test_streamlit_config_resolver tests.unit.test_streamlit_api_client tests.unit.test_project_skeleton -v` passes
- [x] 2.7 Commit: `feat(frontend): wire HTTP client and YAML-driven workbench config`

## 3. Streamlit Real Entry and Render Shells

- [x] 3.1 Append two failing TestCases to `tests/integration/test_streamlit_workbench_smoke.py`: entry module importable + exposes `bootstrap_streamlit_app`; each page exposes a `render_*` callable
- [x] 3.2 Implement `frontend/streamlit_app/streamlit_entry.py` with `bootstrap_streamlit_app()` doing `st.set_page_config` first, sidebar radio page nav, page-specific render dispatch, and module-level call to bootstrap
- [x] 3.3 Append `render_analysis_view(client)` to `frontend/streamlit_app/pages/analysis_view.py` reusing `build_analysis_view_model` and existing `set_last_analysis_result` state helper
- [x] 3.4 Append `render_debug_view()` to `frontend/streamlit_app/pages/debug_view.py` reusing `build_debug_view_model`
- [x] 3.5 Append `render_eval_view(client)` to `frontend/streamlit_app/pages/eval_view.py` reusing `build_eval_view_model` and `fetch_event_cases` / `fetch_event_replay`
- [x] 3.6 Verify `python -m unittest tests.integration.test_streamlit_workbench_smoke tests.unit.test_project_skeleton -v` passes
- [x] 3.7 Commit: `feat(frontend): add Streamlit entry and render shells for the three pages`

## 4. Launchers and End-to-End Smoke

- [x] 4.1 Add failing test `test_backend_subprocess_stays_alive_then_exits_cleanly` and `test_run_workbench_backend_script_can_be_invoked` in `tests/integration/test_workbench_end_to_end.py` (avoid Windows ProactorEventLoop accept flake by not doing HTTP polling inside the test; HTTP path is covered by TestClient in `test_backend_api_app.py`)
- [x] 4.2 Implement `scripts/run_workbench_backend.py` (cross-platform Python `uvicorn.run` launcher) that reads `app.workbench.backend_host` / `backend_port` from `config_resolver`
- [x] 4.3 Implement `scripts/run_workbench_frontend.sh` and `scripts/run_workbench_frontend.cmd` (streamlit run launcher; `--server.headless true`)
- [x] 4.4 Implement `scripts/run_workbench_backend.cmd` Windows cmd wrapper + `scripts/run_workbench_backend.sh` POSIX wrapper around `run_workbench_backend.py`
- [x] 4.5 Implement `scripts/run_workbench.sh` POSIX one-shot launcher: backend in background + poll readiness + foreground streamlit, with `trap 'kill $BACKEND_PID' EXIT`
- [x] 4.6 Verify `python -m unittest tests.integration.test_workbench_end_to_end -v` passes (5/5 stable runs)
- [x] 4.7 Commit: `feat(scripts): add workbench launchers and subprocess end-to-end smoke`

## 5. Documentation, Skeleton Pinning, Status Sync

- [x] 5.1 Add failing `test_workbench_runnable_artifacts_exist` to `tests/unit/test_project_skeleton.py` covering the 8 workbench-runnable artifact paths
- [x] 5.2 Append the 8 new artifact paths to the existing `test_minimal_fast_path_files_exist` `required_files` list (additive only)
- [x] 5.3 Create `docs/finsight/operations/workbench-runbook.md` with sections: prerequisites, start backend, start frontend, one-shot start, troubleshooting (GDELT 429, port-in-use), how to stop, test coverage
- [x] 5.4 Append M9 "Workbench Runnable" row to the milestone table in `docs/finsight/project-status.md`
- [x] 5.5 Add a "可启动状态" section to `docs/finsight/modules/control-plane-status.md` referencing the runbook
- [x] 5.6 Add a "可启动状态" section to `docs/finsight/modules/presentation-eval-status.md` referencing the runbook
- [x] 5.7 Fix the `hao#` typo at line 1 of `docs/superpowers/plans/2026-07-05-streamlit-debug-eval-workbench.md`
- [x] 5.8 Verify `python -m unittest tests.unit.test_project_skeleton tests.integration.test_backend_api_app tests.integration.test_workbench_end_to_end tests.integration.test_streamlit_workbench_smoke -v` passes (37 tests total in workbench suite, all green)
- [x] 5.9 Commit: `docs: add workbench runbook, M9 milestone, skeleton artifact pinning`
