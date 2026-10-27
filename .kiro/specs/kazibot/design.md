# Design Document: KaziBot

## Overview

KaziBot is a semi-automated, Human-in-the-Loop job application assistant targeting the Kenyan job market. The system combines three tightly integrated concerns: automated job scraping, LLM-powered cover letter generation, and Gmail Draft creation — all governed by explicit user approval at every dispatch step.

### Key Design Principles

- **Human in the Loop**: No email is ever sent without the user clicking "Push to Gmail Drafts" in the Review Portal. The system creates drafts only.
- **Modular scraper framework**: Each job board is an independent, interchangeable plugin. Adding a new board requires only a new module, not changes to core infrastructure.
- **Provider-agnostic LLM**: The AI layer supports OpenAI and Anthropic behind a common interface, selectable via configuration.
- **Dual-engine persistence**: SQLite for local/development use, PostgreSQL for production — switched by a single environment variable.
- **Security by default**: OAuth2 tokens are encrypted at rest using Fernet symmetric encryption; API keys never appear in logs or source code.

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    React Dashboard (Vite + TS)           │
│  Job_Feed  │  Review_Portal  │  Profile_Settings         │
└─────────────────────┬───────────────────────────────────┘
                      │ HTTP/REST (JSON)
┌─────────────────────▼───────────────────────────────────┐
│                  FastAPI Backend                         │
│  /jobs  │  /ai  │  /drafts  │  /profile  │  /scrape     │
└───┬──────────────────────────────────────────┬──────────┘
    │                                          │
┌───▼──────────┐  ┌───────────────┐  ┌────────▼──────────┐
│  Database    │  │  AI_Tailor    │  │  Draft_Service     │
│  SQLAlchemy  │  │  OpenAI /     │  │  Gmail API         │
│  SQLite /    │  │  Anthropic    │  │  OAuth2 + Fernet   │
│  PostgreSQL  │  └───────────────┘  └────────────────────┘
└──────────────┘
       ▲
┌──────┴───────┐
│   Scraper    │
│  Playwright  │
│  Board Plugins│
└──────────────┘
```

---

## Architecture

### Backend: FastAPI

The backend is a Python FastAPI application that exposes a REST API consumed by the React frontend. FastAPI is chosen for its async-native design, automatic OpenAPI docs, and Pydantic v2 integration for input validation.

All database access uses SQLAlchemy 2.0 async sessions with `aiosqlite` (SQLite) or `asyncpg` (PostgreSQL). Alembic manages schema migrations.

The backend is organized into feature modules:

```
backend/
├── main.py                  # FastAPI app factory, lifespan events
├── config.py                # Settings via pydantic-settings + .env
├── database.py              # Async engine, session factory
├── models/                  # SQLAlchemy ORM models
│   ├── job_listing.py
│   ├── generated_email.py
│   └── user_profile.py
├── schemas/                 # Pydantic request/response schemas
│   ├── job_listing.py
│   ├── generated_email.py
│   └── user_profile.py
├── routers/                 # FastAPI route modules
│   ├── jobs.py
│   ├── ai.py
│   ├── drafts.py
│   ├── profile.py
│   └── scrape.py
├── services/
│   ├── scraper/             # Scraper framework
│   │   ├── base.py          # BaseScraper ABC
│   │   ├── fuzu.py
│   │   ├── brighter_monday.py
│   │   └── my_job_mag.py
│   ├── ai_tailor.py         # LLM cover letter generation
│   ├── draft_service.py     # Gmail Draft creation
│   └── token_store.py       # Encrypted OAuth2 token persistence
└── prompts/
    └── cover_letter.txt     # Prompt template (separate from code)
```

### Frontend: React + TypeScript + Vite

The frontend is a single-page application (SPA) built with React 19, TypeScript, Vite, and Tailwind CSS. It communicates with the FastAPI backend exclusively via REST.

State management uses React Query (TanStack Query v5) for server state caching, pagination, and background refetching. No separate global state library is required.

```
frontend/
├── src/
│   ├── main.tsx
│   ├── App.tsx              # Route definitions (React Router v6)
│   ├── api/                 # Typed API client (fetch wrappers)
│   │   ├── jobs.ts
│   │   ├── profile.ts
│   │   ├── ai.ts
│   │   └── drafts.ts
│   ├── components/          # Shared UI components
│   │   ├── JobCard.tsx
│   │   ├── StatusBadge.tsx
│   │   └── LoadingSpinner.tsx
│   ├── pages/
│   │   ├── JobFeed.tsx
│   │   ├── ReviewPortal.tsx
│   │   └── ProfileSettings.tsx
│   └── types/
│       └── index.ts         # Shared TypeScript types
```

### Scraper Architecture

The Scraper uses a plugin pattern. A `BaseScraper` abstract base class defines the contract for all board implementations:

```python
class BaseScraper(ABC):
    board_name: str

    @abstractmethod
    async def scrape(self) -> list[JobListingCreate]:
        """Scrape all listings from this board."""
        ...
```

A `ScraperOrchestrator` iterates over registered board plugins, runs each, deduplicates results against the database, and persists new listings. Playwright is used for browser automation with configurable headless/headful mode.

Each scraper instance shares a single Playwright browser context, launched once per scraping session and torn down cleanly on completion or error.

### LLM Provider Abstraction

`AI_Tailor` is backed by an `LLMProvider` protocol:

```python
class LLMProvider(Protocol):
    async def complete(self, prompt: str) -> str: ...
```

Concrete implementations are `OpenAIProvider` and `AnthropicProvider`. The active provider is selected at startup from the `LLM_PROVIDER` environment variable. The prompt template is read from `prompts/cover_letter.txt` at runtime, so prompt edits require no code changes or redeployment.

### Gmail Draft Service

`Draft_Service` authenticates via OAuth2 using `google-auth` and `google-api-python-client`. It requests only the `https://www.googleapis.com/auth/gmail.compose` scope, which grants draft creation/management but **does not permit sending email** — enforcing the Human-in-the-Loop requirement at the API permission level.

OAuth2 tokens (access token + refresh token) are serialized to JSON and encrypted using `cryptography.Fernet` before being written to a local file. The Fernet key itself is derived from an environment variable `FERNET_KEY`. When the access token expires, the library automatically uses the stored refresh token to obtain a new one without user interaction.

---

## Components and Interfaces

### REST API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/jobs` | List all job listings (with optional status filter) |
| `GET` | `/api/jobs/{id}` | Get a single job listing with its generated email |
| `PATCH` | `/api/jobs/{id}/status` | Update a job's status (`Skipped`, `Applied`) |
| `POST` | `/api/scrape` | Trigger a new scraping session |
| `POST` | `/api/ai/generate/{job_id}` | Generate a cover letter for a job listing |
| `POST` | `/api/drafts/{job_id}` | Push generated email to Gmail Drafts |
| `GET` | `/api/profile` | Get user profile |
| `PUT` | `/api/profile` | Update user profile |
| `GET` | `/api/auth/gmail` | Initiate Gmail OAuth2 flow |
| `GET` | `/api/auth/gmail/callback` | OAuth2 redirect callback |

### Pydantic Schemas

**JobListingResponse**
```python
class JobListingResponse(BaseModel):
    id: int
    title: str
    company: str
    description: str
    application_email: str | None
    application_url: str | None
    deadline: date | None
    status: JobStatus  # Enum: pending_ai | draft_created | applied | skipped
    scraped_at: datetime
    board_source: str
    generated_email: str | None
```

**UserProfileRequest / UserProfileResponse**
```python
class UserProfileRequest(BaseModel):
    resume_markdown: str
    tech_stack: list[str]
    github_url: HttpUrl | None
    portfolio_url: HttpUrl | None
    llm_provider: Literal["openai", "anthropic"]
    llm_api_key: str  # Stored encrypted; response returns masked value

class UserProfileResponse(BaseModel):
    # same fields but llm_api_key shows only last 4 chars
    llm_api_key_masked: str
```

**JobStatusUpdate**
```python
class JobStatusUpdate(BaseModel):
    status: Literal["applied", "skipped"]
```

### Frontend Pages

**JobFeed**: Fetches `/api/jobs`, renders a responsive grid of `JobCard` components. Each card shows title, company, deadline, and a `StatusBadge`. Buttons to mark as `Skipped` or `Applied` call `PATCH /api/jobs/{id}/status`. A "Run Scraper" button posts to `/api/scrape` and React Query invalidates the job list on success.

**ReviewPortal**: Fetches `/api/jobs/{id}`. Renders a two-column layout: left panel shows the full job description (read-only); right panel is an editable `<textarea>` pre-populated with the generated email. A "Generate" button (shown when status is `Pending AI`) calls `POST /api/ai/generate/{id}`. "Push to Gmail Drafts" calls `POST /api/drafts/{id}`, is disabled while loading, and shows success/error toasts.

**ProfileSettings**: Fetches and updates `/api/profile`. API key fields display only the masked value after save, re-masking on blur. A "Connect Gmail" button navigates to `/api/auth/gmail`.

---

## Data Models

### Entity Relationship

```
UserProfile (1) ──── (many) JobListing (1) ──── (0..1) GeneratedEmail
```

There is a single `UserProfile` row (the local user). Each `JobListing` has at most one `GeneratedEmail`.

### SQLAlchemy ORM Models

**JobListing**

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | Auto-increment |
| `title` | String(255) | Not null |
| `company` | String(255) | Not null |
| `description` | Text | Full job description |
| `application_email` | String(320) | Nullable |
| `application_url` | String(2048) | Nullable |
| `deadline` | Date | Nullable |
| `status` | Enum(JobStatus) | Default: `pending_ai` |
| `board_source` | String(100) | e.g., `fuzu`, `brighter_monday` |
| `scraped_at` | DateTime | UTC, auto-set on insert |

Unique constraint: `(title, company, board_source)` — prevents duplicate records (Requirement 7.4).

**GeneratedEmail**

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | Auto-increment |
| `job_listing_id` | Integer FK → JobListing.id | Unique (one-to-one) |
| `email_body` | Text | LLM output |
| `created_at` | DateTime | UTC |
| `updated_at` | DateTime | UTC, updated on edit |

**UserProfile**

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | Always row 1 (singleton) |
| `resume_markdown` | Text | Markdown-formatted resume |
| `tech_stack` | JSON | List of skill strings |
| `github_url` | String(2048) | Nullable |
| `portfolio_url` | String(2048) | Nullable |
| `llm_provider` | String(20) | `openai` or `anthropic` |
| `llm_api_key_encrypted` | Text | Fernet-encrypted |

**JobStatus Enum**

```python
class JobStatus(str, Enum):
    pending_ai   = "pending_ai"
    draft_created = "draft_created"
    applied      = "applied"
    skipped      = "skipped"
```

### Database Configuration

The database URL is read from the `DATABASE_URL` environment variable:

- SQLite: `sqlite+aiosqlite:///./kazibot.db`
- PostgreSQL: `postgresql+asyncpg://user:pass@host/db`

Alembic handles all schema migrations. The engine is created once at application startup via FastAPI's lifespan context manager.

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Scraper deduplication preserves uniqueness

*For any* set of job listings (including duplicates) scraped from any board and persisted to the database across one or more sessions, no two rows in the `job_listings` table shall share the same `(title, company, board_source)` triple.

**Validates: Requirements 1.7, 7.4**

---

### Property 2: Scraper field completeness

*For any* job board page that contains a valid job listing, the parsed output from any `BaseScraper` implementation shall include non-null values for all required fields: Job Title, Company Name, and Full Job Description. Optional fields (application email, application URL, deadline) shall be extracted when present.

**Validates: Requirements 1.1**

---

### Property 3: Scraper delay invariant

*For any* `BaseScraper` implementation making a sequence of N ≥ 2 consecutive requests to the same board, the delay injected between each pair of consecutive requests shall be at least 3 seconds and at most 7 seconds.

**Validates: Requirements 1.3**

---

### Property 4: AI prompt completeness

*For any* `UserProfile` with non-empty resume text and tech stack, the prompt string constructed by `AI_Tailor` and sent to the LLM shall contain: the full job description text, the resume text, the tech stack, the GitHub URL (if non-null), and the portfolio URL (if non-null).

**Validates: Requirements 2.1, 2.2, 2.4, 2.5**

---

### Property 5: Draft_Service never calls the Gmail send endpoint

*For any* job listing and any generated email body, invoking `Draft_Service.push_to_draft()` shall result in exactly one call to the Gmail Drafts `create` endpoint and zero calls to the Gmail `messages.send` endpoint or any SMTP socket.

**Validates: Requirements 3.3**

---

### Property 6: Draft creation updates job status to Draft Created

*For any* job listing in `Pending AI` or any other non-final status, after `Draft_Service.push_to_draft()` returns successfully, the persisted `Job_Status` in the database shall be exactly `Draft Created`.

**Validates: Requirements 3.4**

---

### Property 7: Draft "To" field matches application email

*For any* job listing with a non-null `application_email`, the Gmail draft created by `Draft_Service` shall have its "To" header set to exactly that email address.

**Validates: Requirements 3.7**

---

### Property 8: JobCard renders all required fields

*For any* `JobListing` object, the rendered `JobCard` component shall contain the Job Title, Company Name, Application Deadline, and Job_Status in its output.

**Validates: Requirements 4.2**

---

### Property 9: StatusBadge uses distinct styling per status

*For any* two distinct `Job_Status` values, the `StatusBadge` component shall render different visual styling (CSS class or color) for each — no two statuses share the same badge appearance.

**Validates: Requirements 4.3**

---

### Property 10: API key masking preserves last 4 characters

*For any* LLM API key string of length ≥ 4, the masked form returned by the backend shall end with exactly the same last 4 characters as the original key, and all characters preceding those 4 shall be replaced with a uniform masking character (e.g., `*`).

**Validates: Requirements 5.7**

---

### Property 11: Data persistence round-trip

*For any* `JobListing`, `GeneratedEmail`, or `UserProfile` object, writing it to the database and reading it back shall yield an object with all fields equal to the original (including all nullable fields).

**Validates: Requirements 7.1, 7.2, 7.3**

---

### Property 12: Token store encrypt-decrypt round-trip

*For any* OAuth2 token dictionary, encrypting it with `TokenStore.save()` and then decrypting it with `TokenStore.load()` shall yield a dictionary equal to the original. Furthermore, the bytes written to disk shall not be parseable as plain-text JSON.

**Validates: Requirements 8.1**

---

### Property 13: API key never appears in log output

*For any* LLM API key string, executing any code path that handles that key (profile save, prompt construction, error handling) shall produce no log records that contain the key value as a substring.

**Validates: Requirements 8.3**

---

## Error Handling

### Scraper

- **Network/timeout failure**: Each board scraper wraps its Playwright operations in a retry loop with a maximum of 3 attempts. On exhaustion, the error is logged with board name, URL, and exception, and processing continues with the next board (Requirement 1.8).
- **Partial failures**: A failed board does not abort the session; successfully scraped listings from other boards are still persisted.
- **Playwright context cleanup**: The browser context is wrapped in an `async with` block to ensure it is torn down even on unhandled exceptions.

### AI_Tailor

- **LLM API error (4xx/5xx)**: The error is caught, logged (without the API key), the job listing remains in `Pending AI` status, and a structured error payload is returned to the API endpoint for display in the Dashboard (Requirement 2.7).
- **Empty or malformed LLM response**: Treated as an API error — the generated text is validated for non-empty content before being persisted.
- **Rate limiting**: Exponential backoff with jitter is applied for HTTP 429 responses.

### Draft_Service

- **Authentication error (401/403)**: The backend returns HTTP 401 to the frontend, which presents the re-authentication flow (Requirement 3.5).
- **Non-auth Gmail API error**: The error is logged and returned as a 502 to the frontend; the job listing status remains unchanged (Requirement 3.6).
- **Token expiry**: `google-auth` handles automatic token refresh using the stored refresh token. If refresh fails (revoked token), the service falls back to the authentication error path.

### Frontend

- **API errors**: All API calls are wrapped in React Query's `onError` callbacks, which trigger toast notifications (e.g., using `react-hot-toast`). No unhandled promise rejections reach the user.
- **Loading states**: The "Push to Gmail Drafts" and "Generate" buttons are disabled and show a spinner while the corresponding API call is in flight (Requirement 6.4).

---

## Testing Strategy

KaziBot's testing strategy uses a dual approach: example-based unit/integration tests for concrete scenarios, and property-based tests for universal correctness properties.

### Property-Based Testing

**Library**: [Hypothesis](https://hypothesis.readthedocs.io/) (Python) — the standard PBT library for the Python ecosystem.

**Configuration**: Each property test uses `@settings(max_examples=100)` to run a minimum of 100 randomly generated inputs.

**Tag format**: Each property test is annotated with a comment:
`# Feature: kazibot, Property N: <property_text>`

Property tests cover:

| Test | Property | Tag |
|------|----------|-----|
| `test_scraper_deduplication` | Deduplication preserves uniqueness | Property 1 |
| `test_scraper_field_completeness` | All required fields extracted | Property 2 |
| `test_scraper_delay_invariant` | Inter-request delay in [3, 7]s | Property 3 |
| `test_ai_prompt_completeness` | Prompt includes all profile fields | Property 4 |
| `test_draft_service_no_send` | Never calls send endpoint | Property 5 |
| `test_status_transition_on_draft_created` | Status becomes Draft Created | Property 6 |
| `test_draft_to_field_matches_email` | Draft To field matches application email | Property 7 |
| `test_job_card_renders_required_fields` | JobCard renders all required fields | Property 8 |
| `test_status_badge_distinct_styling` | StatusBadge distinct per status | Property 9 |
| `test_api_key_masking` | Masking preserves last 4 chars | Property 10 |
| `test_data_persistence_round_trip` | Data round-trip equality | Property 11 |
| `test_token_store_round_trip` | Encrypt-decrypt round-trip | Property 12 |
| `test_api_key_not_logged` | API key absent from all log output | Property 13 |

### Unit Tests (Example-Based)

- **Scraper**: Mock Playwright page objects; assert parsed fields match fixture HTML.
- **AI_Tailor**: Mock the LLM HTTP client; assert prompt construction and response handling.
- **Draft_Service**: Mock the Gmail API client; assert draft payload structure (headers, body, To field).
- **Status transitions**: Verify all valid and invalid status change paths against the ORM layer.
- **Profile masking**: Concrete examples — key of length 4, length 8, exactly 4 chars.

### Integration Tests

- **Database**: Spin up an in-memory SQLite database; test full CRUD cycles, unique constraint enforcement, and status transitions end-to-end.
- **Scraper → Database pipeline**: Run a scraper against a local HTML fixture served by an embedded HTTP server; verify persistence and deduplication.
- **AI → Database**: Full flow with a mock LLM response persisted to `generated_email` and status checked.
- **Draft_Service → Gmail API**: Use the Gmail API test sandbox (or a mock HTTP server) to verify draft creation without network calls.

### Frontend Tests

- **React Testing Library**: Example-based tests for `JobCard`, `StatusBadge`, and form components.
- **Vitest**: Unit test runner co-located with source files.
- **API client tests**: Mock `fetch` with `msw` (Mock Service Worker) to test React Query integration and loading/error states.

### Security-Focused Tests

- Assert that no API key appears in log output for any code path.
- Assert that `Draft_Service` never constructs a request to the Gmail send endpoint URL.
- Assert that token files written to disk are not valid UTF-8 JSON (i.e., are encrypted).
