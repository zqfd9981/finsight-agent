## 1. Spec And Contract Alignment

- [x] 1.1 Add the main `workbench-backend-api-boundary` spec covering the V1 synchronous analysis endpoint, request contract, response envelope, and HTTP status semantics.
- [x] 1.2 Update the main `shared-analysis-contracts` spec so shared contracts explicitly include the API request object and response envelope.
- [x] 1.3 Sync supporting contract documentation and fixtures planning so the new API boundary wording matches the formal specs.

## 2. Shared Contract Preparation

- [x] 2.1 Add shared contract models for the analysis request object and response envelope under `shared/contracts/`.
- [x] 2.2 Add or update fixtures for a first-turn request, a follow-up request, and a successful response envelope.
- [x] 2.3 Document any optional fields deferred from V1 so implementation does not invent extra request parameters.

## 3. Backend And Frontend Boundary Implementation

- [x] 3.1 Add a minimal FastAPI endpoint skeleton under `backend/apps/api/` that accepts the shared request contract and returns the shared response envelope.
- [x] 3.2 Add a backend adapter layer that converts the endpoint request into the current backend service entry flow without exposing internal modules to the frontend.
- [x] 3.3 Add a frontend workbench client or adapter under `frontend/streamlit_app/` that calls the backend API boundary instead of importing backend internals.

## 4. Verification

- [x] 4.1 Add tests for shared request/response contracts and fixture validity.
- [x] 4.2 Add tests that verify the frontend uses the API boundary rather than direct backend internal imports.
- [x] 4.3 Run the project verification commands and confirm the API-boundary skeleton still passes the test suite.
