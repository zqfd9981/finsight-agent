## 1. Spec And Documentation Alignment

- [x] 1.1 Update the main `project-implementation-architecture` spec to adopt the `frontend/ + backend/ + shared/` engineering-layer structure.
- [x] 1.2 Update the main `analysis-workbench` spec so the V1 Streamlit workbench is defined under `frontend/` and consumes backend results through stable interfaces only.
- [x] 1.3 Sync `项目框架结构约定.md` with the approved architecture wording so the human-readable guide matches the formal specs.

## 2. Skeleton Migration Preparation

- [x] 2.1 Define the target directory mapping from the current `apps/` and `src/` skeleton to `frontend/streamlit_app/`, `backend/apps/api/`, and `backend/src/finsight_agent/`.
- [x] 2.2 Decide which existing shared contracts and enums move to top-level `shared/` in the first migration batch versus a later batch.
- [x] 2.3 Identify and document any imports or startup paths that would violate the new frontend-to-backend dependency boundary after migration.

## 3. Skeleton Migration Implementation

- [x] 3.1 Move the backend API entry skeleton from `apps/api/` to `backend/apps/api/` without adding new business logic.
- [x] 3.2 Move the V1 Streamlit workbench skeleton from `apps/workbench/` to `frontend/streamlit_app/` without expanding UI behavior.
- [x] 3.3 Move backend runtime modules from `src/finsight_agent/` to `backend/src/finsight_agent/` while preserving the current internal layering.
- [x] 3.4 Move the approved cross-project contracts and enums into top-level `shared/` and leave backend-only reusable entities under `backend/src/`.

## 4. Verification

- [x] 4.1 Update or add skeleton tests so they validate the new top-level directory layout and dependency boundary expectations.
- [x] 4.2 Run the project verification commands and confirm the migrated skeleton still passes the current test suite.
- [x] 4.3 Review the repository tree and change notes to ensure no undocumented architecture conflicts remain before implementation proceeds further.
