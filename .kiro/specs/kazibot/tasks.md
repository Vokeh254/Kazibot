# Implementation Plan: KaziBot

## Overview

KaziBot is implemented as a Python FastAPI backend + React/TypeScript frontend. The plan builds incrementally: project scaffolding and data layer first, then each backend service (scraper, AI, Gmail drafts), then the frontend pages, and finally wiring everything together. Property-based tests (Hypothesis) are co-located with the components they verify.

---

## Tasks

- [x] 1. Project scaffolding and environment setup
  - Create `backend/` and `frontend/` directory structures as specified in the design
  - Create `backend/config.py` using `pydantic-settings` to load all env vars (`DATABASE_URL`, `LLM_PROVIDER`, `FERNET_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `CUSTOM_USER_AGENT`) from `.env`
  - Create `.env.example` listing all required variables without real values
  - Create `backend/main.py` with a bare FastAPI app factory and lifespan context manager (no routes yet)
  - Initialise `frontend/` with `npm create vite@latest -- --template react-ts`, install `tailwindcss`, `@tanstack/react-query`, `react-router-dom`, `react-hot-toast`
  - _Requirements: 8.5_

- [x] 2. Database layer — models, migrations, and session factory
  - [x] 2.1 Implement SQLAlchemy ORM models and async session factory
    - Create `backend/database.py`: async engine factory reading `DATABASE_URL`; export `get_async_session` dependency
    - Create `backend/models/job_listing.py`: `JobListing` ORM model with all columns and the `(title, company, board_source)` unique constraint; define `JobStatus` enum
    - Create `backend/models/generated_email.py`: `GeneratedEmail` ORM model with FK to `JobListing`
    - Create `backend/models/user_profile.py`: `UserProfile` ORM model (singleton row)
    - Initialise Alembic (`alembic init alembic`); configure `env.py` to target the async engine; generate and apply the initial migration
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 2.2 Write property test for data persistence round-trip
    - Use Hypothesis to generate arbitrary `JobListing`, `GeneratedEmail`, and `UserProfile` instances; write each to an in-memory SQLite DB and read back; assert all fields equal the original
    - `# Feature: kazibot, Property 11: Data persistence round-trip`
    - **Property 11: Data persistence round-trip**
    - **Validates: Requirements 7.1, 7.2, 7.3**

  - [x] 2.3 Write integration tests for database constraints
    - Test that inserting a duplicate `(title, company, board_source)` triple raises an integrity error
    - Test that a `GeneratedEmail` row cannot exist without a parent `JobListing`
    - _Requirements: 7.4_

- [x] 3. Pydantic schemas and profile API
  - [x] 3.1 Implement Pydantic schemas
    - Create `backend/schemas/job_listing.py`: `JobListingResponse`, `JobStatusUpdate`
    - Create `backend/schemas/generated_email.py`: `GeneratedEmailResponse`
    - Create `backend/schemas/user_profile.py`: `UserProfileRequest`, `UserProfileResponse` (masked API key field)
    - _Requirements: 5.1–5.7, 7.1–7.3_

  - [x] 3.2 Implement `TokenStore` for encrypted OAuth2 token persistence
    - Create `backend/services/token_store.py`: `save(token_dict)` encrypts with Fernet and writes to file; `load()` reads, decrypts, and returns dict; key read from `FERNET_KEY` env var
    - _Requirements: 8.1_

  - [x] 3.3 Write property test for token store encrypt-decrypt round-trip
    - Use Hypothesis to generate arbitrary token dicts; call `save()` then `load()`; assert the result equals the original; assert file bytes are not valid UTF-8 JSON
    - `# Feature: kazibot, Property 12: Token store encrypt-decrypt round-trip`
    - **Property 12: Token store encrypt-decrypt round-trip**
    - **Validates: Requirements 8.1**

  - [x] 3.4 Implement profile router
    - Create `backend/routers/profile.py`: `GET /api/profile` (returns masked key), `PUT /api/profile` (encrypts API key with Fernet before storing)
    - Wire router into `backend/main.py`
    - _Requirements: 5.1–5.7, 8.2, 8.3_

  - [x] 3.5 Write property test for API key masking
    - Use Hypothesis to generate key strings of length ≥ 4; assert masked form ends with same last 4 chars and all preceding chars are the mask character
    - `# Feature: kazibot, Property 10: API key masking preserves last 4 characters`
    - **Property 10: API key masking preserves last 4 characters**
    - **Validates: Requirements 5.7**

  - [x] 3.6 Write property test for API key not appearing in logs
    - Use Hypothesis to generate API key strings; run profile-save and prompt-construction code paths with a captured log handler; assert no log record contains the key value
    - `# Feature: kazibot, Property 13: API key never appears in log output`
    - **Property 13: API key never appears in log output**
    - **Validates: Requirements 8.3**

- [x] 4. Checkpoint — database and profile layer
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Scraper framework and board plugins
  - [x] 5.1 Implement `BaseScraper` ABC and `ScraperOrchestrator`
    - Create `backend/services/scraper/base.py`: `BaseScraper` ABC with abstract `scrape()` returning `list[JobListingCreate]`; include configurable User-Agent and randomised 3–7 s delay between requests; headless/headful toggle from config
    - Create `backend/services/scraper/__init__.py`: `ScraperOrchestrator` that iterates registered board plugins, calls `scrape()` on each, deduplicates against the DB, and persists new listings; wraps each board in a retry loop (max 3 attempts) with logging on failure
    - Shared Playwright browser context launched once per session, torn down in `async with`
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.7, 1.8, 1.9_

  - [x] 5.2 Write property test for scraper deduplication
    - Use Hypothesis to generate arbitrary sets of `JobListingCreate` objects (including duplicates); run `ScraperOrchestrator` persist logic; assert no two rows share the same `(title, company, board_source)` triple
    - `# Feature: kazibot, Property 1: Scraper deduplication preserves uniqueness`
    - **Property 1: Scraper deduplication preserves uniqueness**
    - **Validates: Requirements 1.7, 7.4**

  - [x] 5.3 Write property test for scraper delay invariant
    - Use Hypothesis with `@settings(max_examples=100)`; mock `asyncio.sleep`; for any N ≥ 2 requests assert each recorded sleep value is in [3, 7]
    - `# Feature: kazibot, Property 3: Scraper delay invariant`
    - **Property 3: Scraper delay invariant**
    - **Validates: Requirements 1.3**

  - [x] 5.4 Implement Fuzu board scraper
    - Create `backend/services/scraper/fuzu.py`: `FuzuScraper(BaseScraper)` — implement `scrape()` using Playwright to load listings and parse all required fields
    - _Requirements: 1.1, 1.6_

  - [x] 5.5 Write property test for scraper field completeness (Fuzu)
    - Use Hypothesis to generate fixture HTML variants; assert parsed output always contains non-null `title`, `company`, `description`; assert optional fields are extracted when present
    - `# Feature: kazibot, Property 2: Scraper field completeness`
    - **Property 2: Scraper field completeness**
    - **Validates: Requirements 1.1**

  - [x] 5.6 Implement BrighterMonday board scraper
    - Create `backend/services/scraper/brighter_monday.py`: `BrighterMondayScraper(BaseScraper)` — implement `scrape()` using Playwright
    - _Requirements: 1.1, 1.6_

  - [x] 5.7 Implement MyJobMag board scraper
    - Create `backend/services/scraper/my_job_mag.py`: `MyJobMagScraper(BaseScraper)` — implement `scrape()` using Playwright
    - _Requirements: 1.1, 1.6_

  - [x] 5.8 Implement scrape router
    - Create `backend/routers/scrape.py`: `POST /api/scrape` endpoint that triggers `ScraperOrchestrator` and returns a count of newly persisted listings
    - Wire router into `backend/main.py`
    - _Requirements: 1.7, 1.8_

  - [x] 5.9 Write unit tests for scraper (mock Playwright)
    - Mock Playwright page objects using fixture HTML; assert all three board parsers return correctly structured `JobListingCreate` objects
    - _Requirements: 1.1_

- [x] 6. Checkpoint — scraper layer
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. AI cover letter generation service
  - [x] 7.1 Implement `LLMProvider` protocol and concrete providers
    - Create `backend/services/ai_tailor.py`: define `LLMProvider` protocol with `async complete(prompt: str) -> str`
    - Implement `OpenAIProvider` and `AnthropicProvider`; select active provider at startup from `LLM_PROVIDER` env var
    - Apply exponential backoff with jitter for HTTP 429 responses
    - _Requirements: 2.6_

  - [x] 7.2 Implement prompt template and `AI_Tailor` service
    - Create `backend/prompts/cover_letter.txt`: prompt template with placeholders for all `UserProfile` fields and the job description
    - Implement `AI_Tailor.generate(job: JobListing, profile: UserProfile) -> str`: reads template from file, interpolates all profile fields, calls `LLMProvider.complete()`
    - Include GitHub URL and portfolio URL in prompt when non-null
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.8_

  - [x] 7.3 Write property test for AI prompt completeness
    - Use Hypothesis to generate arbitrary `UserProfile` (non-empty resume, non-empty tech stack) and `JobListing` objects; assert the constructed prompt string contains the job description, resume text, tech stack, and both URLs when non-null
    - `# Feature: kazibot, Property 4: AI prompt completeness`
    - **Property 4: AI prompt completeness**
    - **Validates: Requirements 2.1, 2.2, 2.4, 2.5**

  - [x] 7.4 Implement AI router
    - Create `backend/routers/ai.py`: `POST /api/ai/generate/{job_id}` — fetch job + profile, call `AI_Tailor.generate()`, persist result to `GeneratedEmail`, update `Job_Status` if needed; on LLM error log (without key) and return structured error payload
    - Wire router into `backend/main.py`
    - _Requirements: 2.1, 2.7_

  - [x] 7.5 Write unit tests for AI_Tailor (mock LLM client)
    - Mock the HTTP client for both OpenAI and Anthropic; assert prompt construction and response handling; assert error responses keep job in `pending_ai` status
    - _Requirements: 2.7_

- [x] 8. Checkpoint — AI service layer
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Gmail Draft service and OAuth2 flow
  - [x] 9.1 Implement `Draft_Service`
    - Create `backend/services/draft_service.py`: `push_to_draft(job: JobListing, email_body: str)` — builds Gmail API `drafts.create` payload with `To` header set to `application_email` (when non-null); calls only `drafts.create`, never `messages.send`; on success updates job status to `draft_created`
    - Use `google-auth` + `google-api-python-client` with `gmail.compose` scope only
    - Handle automatic token refresh via stored refresh token; on refresh failure surface 401
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.7, 8.1, 8.4_

  - [x] 9.2 Write property test — Draft_Service never calls send endpoint
    - Use Hypothesis to generate arbitrary job and email body inputs; mock the Gmail API client; assert zero calls to `messages.send` and exactly one call to `drafts.create`
    - `# Feature: kazibot, Property 5: Draft_Service never calls the Gmail send endpoint`
    - **Property 5: Draft_Service never calls the Gmail send endpoint**
    - **Validates: Requirements 3.3**

  - [x] 9.3 Write property test — draft creation updates job status
    - Use Hypothesis to generate job listings in various non-final statuses; after `push_to_draft()` returns successfully, assert persisted status is exactly `draft_created`
    - `# Feature: kazibot, Property 6: Draft creation updates job status to Draft Created`
    - **Property 6: Draft creation updates job status to Draft Created**
    - **Validates: Requirements 3.4**

  - [x] 9.4 Write property test — draft To field matches application email
    - Use Hypothesis to generate job listings with non-null `application_email`; capture the `drafts.create` payload; assert `To` header equals `application_email`
    - `# Feature: kazibot, Property 7: Draft "To" field matches application email`
    - **Property 7: Draft "To" field matches application email**
    - **Validates: Requirements 3.7**

  - [x] 9.5 Implement OAuth2 auth flow endpoints
    - Create `backend/routers/drafts.py`: `GET /api/auth/gmail` (initiates OAuth2 redirect), `GET /api/auth/gmail/callback` (exchanges code for tokens, saves via `TokenStore`), `POST /api/drafts/{job_id}` (calls `Draft_Service.push_to_draft`)
    - Wire router into `backend/main.py`
    - _Requirements: 3.1, 3.5, 3.6, 8.1_

  - [-] 9.6 Write unit tests for Draft_Service (mock Gmail API client)
    - Assert draft payload structure: correct headers, body, `To` field populated; assert error paths return correct HTTP status codes
    - _Requirements: 3.1, 3.6, 3.7_

- [ ] 10. Jobs router
  - Create `backend/routers/jobs.py`: `GET /api/jobs` (optional `?status=` filter), `GET /api/jobs/{id}` (includes `generated_email`), `PATCH /api/jobs/{id}/status`
  - Wire router into `backend/main.py`
  - _Requirements: 4.1, 4.5, 4.6_

- [ ] 11. Checkpoint — all backend endpoints
  - Ensure all tests pass and all 10 REST endpoints respond correctly, ask the user if questions arise.

- [ ] 12. Frontend — shared types, API client, and base components
  - [ ] 12.1 Define shared TypeScript types
    - Create `frontend/src/types/index.ts`: `JobListing`, `GeneratedEmail`, `UserProfile`, `JobStatus` enum mirroring backend schemas
    - _Requirements: 4.1–4.6, 5.1–5.7, 6.1–6.7_

  - [ ] 12.2 Implement typed API client modules
    - Create `frontend/src/api/jobs.ts`, `api/profile.ts`, `api/ai.ts`, `api/drafts.ts` — typed `fetch` wrappers for all backend endpoints
    - _Requirements: 4.1–4.6, 5.6, 6.3_

  - [ ] 12.3 Implement shared UI components
    - Create `frontend/src/components/JobCard.tsx`: renders `title`, `company`, `deadline`, and `<StatusBadge status={…} />`
    - Create `frontend/src/components/StatusBadge.tsx`: distinct Tailwind CSS classes for each of the four `JobStatus` values
    - Create `frontend/src/components/LoadingSpinner.tsx`
    - _Requirements: 4.2, 4.3_

  - [ ] 12.4 Write property test for JobCard rendering required fields
    - Use Vitest + React Testing Library; use `@fast-check/vitest` to generate arbitrary `JobListing` objects; assert rendered output contains title, company, deadline, and status badge
    - `# Feature: kazibot, Property 8: JobCard renders all required fields`
    - **Property 8: JobCard renders all required fields**
    - **Validates: Requirements 4.2**

  - [ ] 12.5 Write property test for StatusBadge distinct styling per status
    - Use `@fast-check/vitest`; for any two distinct `JobStatus` values assert the rendered badge CSS class differs
    - `# Feature: kazibot, Property 9: StatusBadge uses distinct styling per status`
    - **Property 9: StatusBadge uses distinct styling per status**
    - **Validates: Requirements 4.3**

- [ ] 13. Frontend — Job Feed page
  - Implement `frontend/src/pages/JobFeed.tsx`: fetch `/api/jobs` with React Query; render responsive grid of `JobCard` components; "Run Scraper" button posts to `/api/scrape` and invalidates query on success; "Skip" and "Applied" buttons call `PATCH /api/jobs/{id}/status`; navigate to `ReviewPortal` on card click
  - _Requirements: 4.1, 4.4, 4.5, 4.6, 4.7_

- [ ] 14. Frontend — Review Portal page
  - Implement `frontend/src/pages/ReviewPortal.tsx`: fetch `/api/jobs/{id}` with React Query; two-column layout (job description read-only | editable `<textarea>` for email); display title, company, deadline prominently; "Generate" button (when `pending_ai`) calls `POST /api/ai/generate/{id}`; "Push to Gmail Drafts" button calls `POST /api/drafts/{id}`, is disabled while loading, shows success/error toasts via `react-hot-toast`; updates visible `Job_Status` on success
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

- [ ] 15. Frontend — Profile Settings page
  - Implement `frontend/src/pages/ProfileSettings.tsx`: form for resume Markdown, tech stack, GitHub URL, portfolio URL, LLM provider selector, and API key field; fetch `/api/profile` on mount; `PUT /api/profile` on save; mask API key after save (display `****…<last4>`); "Connect Gmail" button navigates to `/api/auth/gmail`
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

- [ ] 16. Frontend — routing and app shell
  - Implement `frontend/src/App.tsx`: define React Router v6 routes for `/`, `/review/:id`, `/profile`; add global `QueryClientProvider` and `Toaster`; add navigation header/sidebar linking all three pages
  - _Requirements: 4.4, 6.1_

- [ ] 17. Checkpoint — full frontend
  - Ensure all Vitest tests pass, ask the user if questions arise.

- [ ] 18. Integration tests — end-to-end backend flows
  - [ ] 18.1 Scraper → Database integration test
    - Serve fixture HTML via an embedded HTTP server; run `ScraperOrchestrator` against it; verify listings are persisted and a second run produces no duplicates
    - _Requirements: 1.1, 1.7, 7.4_

  - [ ] 18.2 AI → Database integration test
    - Mock the LLM HTTP client; call `POST /api/ai/generate/{job_id}` via `httpx.AsyncClient`; assert `GeneratedEmail` row created and job status unchanged from `pending_ai`
    - _Requirements: 2.1, 7.2_

  - [ ] 18.3 Draft_Service → Gmail API integration test
    - Mock the Gmail HTTP endpoint; call `POST /api/drafts/{job_id}`; assert exactly one `drafts.create` call and status updated to `draft_created`
    - _Requirements: 3.1, 3.3, 3.4_

- [ ] 19. Final checkpoint — all tests pass
  - Ensure all backend (pytest) and frontend (vitest) tests pass, ask the user if questions arise.

---

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- All Hypothesis property tests use `@settings(max_examples=100)` and the tag `# Feature: kazibot, Property N: <text>`
- Frontend property tests use `@fast-check/vitest` (fast-check is the PBT library for TypeScript/Vitest)
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at each service boundary
- The backend and frontend can be developed in parallel after Task 2 (database layer) is complete
