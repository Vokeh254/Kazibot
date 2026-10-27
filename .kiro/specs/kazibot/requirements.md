# Requirements Document

## Introduction

KaziBot is a semi-automated, Human-in-the-Loop job application assistant optimized for the Kenyan job market, focusing on IT entry-level roles, internships, and graphic design positions. The system scrapes job listings from Kenyan job boards, uses a Large Language Model (LLM) to generate personalized cover letter emails tailored to the user's profile, and saves the generated emails as Gmail Drafts for manual review and dispatch. KaziBot never sends emails autonomously — every application action requires explicit user approval.

---

## Glossary

- **KaziBot**: The overall semi-automated job application assistant system.
- **Scraper**: The Python component responsible for extracting job listings from Kenyan job boards using browser automation.
- **Job Board**: An external website listing job opportunities (e.g., Fuzu, BrighterMonday, MyJobMag).
- **Job Listing**: A single job post extracted by the Scraper, containing title, company, description, application target, and deadline.
- **AI_Tailor**: The Python component that interacts with the LLM API to generate personalized cover letter emails.
- **User_Profile**: The user-maintained set of data including resume text, tech stack, GitHub URL, portfolio/Behance URL, and target job categories.
- **Draft_Service**: The Python component that authenticates with the Gmail API via OAuth2 and creates email drafts in the user's Gmail account.
- **Draft**: A Gmail email draft created by Draft_Service, visible to the user in their Gmail Drafts folder, not yet sent.
- **Dashboard**: The React + TypeScript + Tailwind CSS frontend application.
- **Job_Feed**: The Dashboard view displaying all scraped job listings with their current status.
- **Review_Portal**: The Dashboard view showing a side-by-side display of a Job Listing and its AI-generated email, with an action to push the email to Gmail Drafts.
- **Profile_Settings**: The Dashboard view where the user manages their User_Profile and API credentials.
- **Job_Status**: The lifecycle state of a Job Listing — one of: `Pending AI`, `Draft Created`, `Applied`, or `Skipped`.
- **LLM**: A Large Language Model accessed via the OpenAI API or Anthropic API.
- **Database**: The persistence layer (SQLite or PostgreSQL managed via ORM) storing Job Listings, generated emails, and User_Profile data.
- **OAuth2**: The authorization protocol used to grant KaziBot scoped access to the user's Gmail account.

---

## Requirements

### Requirement 1: Job Scraping

**User Story:** As a job seeker, I want KaziBot to automatically collect job listings from Kenyan job boards, so that I do not have to manually search multiple sites.

#### Acceptance Criteria

1. THE Scraper SHALL extract the following fields from each Job Listing: Job Title, Company Name, Full Job Description, Application Email or Application URL, and Application Deadline.
2. WHEN the Scraper encounters a JavaScript-rendered job board page, THE Scraper SHALL use browser automation (Playwright or Selenium) to load and parse the page content.
3. WHEN the Scraper makes consecutive HTTP or browser requests to a Job Board, THE Scraper SHALL insert a randomized delay of between 3 and 7 seconds between each request.
4. THE Scraper SHALL send requests using a configurable custom User-Agent string to simulate a real browser session.
5. WHERE headless mode is disabled in configuration, THE Scraper SHALL launch the browser in a visible (headful) window.
6. THE Scraper SHALL support scraping from at least the following job boards: Fuzu, BrighterMonday, and MyJobMag.
7. WHEN a scraping session completes, THE Scraper SHALL persist all newly discovered Job Listings to the Database without duplicating existing records.
8. IF the Scraper fails to load a Job Board page after 3 retry attempts, THEN THE Scraper SHALL log the failure with the board name, URL, and error message, and continue processing remaining boards.
9. THE Scraper SHALL be structured as a modular framework where each Job Board is implemented as an independent, interchangeable scraper module.

---

### Requirement 2: AI Cover Letter Tailoring

**User Story:** As a job seeker, I want KaziBot to generate a personalized cover letter email for each job, so that my application is contextually relevant and highlights my matching skills.

#### Acceptance Criteria

1. WHEN a Job Listing has a `Pending AI` status and the user triggers generation, THE AI_Tailor SHALL send a prompt to the configured LLM containing the full Job Description and the User_Profile data.
2. THE AI_Tailor SHALL include the following User_Profile fields in the prompt context: resume text, tech stack, GitHub URL, and portfolio or Behance URL.
3. THE AI_Tailor SHALL produce an output email that references specific skills from the User_Profile that match requirements stated in the Job Description.
4. WHERE a GitHub URL is present in the User_Profile, THE AI_Tailor SHALL include a reference to the GitHub URL in the generated email body.
5. WHERE a portfolio or Behance URL is present in the User_Profile, THE AI_Tailor SHALL include a reference to the portfolio URL in the generated email body.
6. THE AI_Tailor SHALL support configuration to use either the OpenAI API or the Anthropic API as the LLM provider.
7. IF the LLM API returns an error response, THEN THE AI_Tailor SHALL log the error, retain the Job Listing in `Pending AI` status, and surface an error message to the Dashboard.
8. THE AI_Tailor SHALL interact with the LLM using a structured prompt template that is stored separately from business logic code, allowing prompt updates without code changes.

---

### Requirement 3: Gmail Draft Creation

**User Story:** As a job seeker, I want KaziBot to save generated cover letters as Gmail Drafts, so that I can review and send them manually with full control over every application.

#### Acceptance Criteria

1. WHEN the user clicks "Push to Gmail Drafts" in the Review_Portal, THE Draft_Service SHALL create a new email Draft in the authenticated user's Gmail account containing the AI-generated cover letter as the email body.
2. THE Draft_Service SHALL authenticate with the Gmail API using the OAuth2 protocol and SHALL only request the `gmail.compose` scope.
3. THE Draft_Service SHALL NOT send any email via SMTP or via the Gmail API send endpoint under any circumstance.
4. WHEN a Draft is successfully created in Gmail, THE Draft_Service SHALL update the corresponding Job Listing's Job_Status to `Draft Created` in the Database.
5. IF the Gmail API returns an authentication error, THEN THE Draft_Service SHALL prompt the user to re-authenticate via the OAuth2 flow.
6. IF the Gmail API returns a non-authentication error when creating a Draft, THEN THE Draft_Service SHALL log the error and display an error notification in the Dashboard without changing the Job Listing's Job_Status.
7. WHEN a Draft is created, THE Draft_Service SHALL pre-populate the Draft's "To" field with the application email address extracted from the Job Listing, where one is available.

---

### Requirement 4: Job Feed Dashboard View

**User Story:** As a job seeker, I want a visual feed of all scraped jobs with their application status, so that I can track my pipeline at a glance.

#### Acceptance Criteria

1. THE Job_Feed SHALL display all Job Listings stored in the Database as individual cards.
2. THE Job_Feed SHALL display the following fields on each job card: Job Title, Company Name, Application Deadline, and Job_Status.
3. THE Job_Feed SHALL render each job card with a visual indicator that reflects the Job_Status, using distinct styling for each of the four statuses: `Pending AI`, `Draft Created`, `Applied`, and `Skipped`.
4. WHEN the user selects a Job Listing in the Job_Feed, THE Dashboard SHALL navigate to the Review_Portal view for that listing.
5. THE Job_Feed SHALL allow the user to mark a Job Listing's status as `Skipped`.
6. THE Job_Feed SHALL allow the user to mark a Job Listing's status as `Applied`.
7. WHEN the user triggers a new scrape, THE Job_Feed SHALL reflect newly added Job Listings without requiring a full page reload.

---

### Requirement 5: Profile Settings Dashboard View

**User Story:** As a job seeker, I want to manage my profile and credentials in the dashboard, so that the AI can generate accurate, personalized applications.

#### Acceptance Criteria

1. THE Profile_Settings SHALL provide an input area for the user to enter and save their resume text in Markdown format.
2. THE Profile_Settings SHALL provide an input field for the user to enter and save their tech stack as a list of skills.
3. THE Profile_Settings SHALL provide an input field for the user to enter and save their GitHub profile URL.
4. THE Profile_Settings SHALL provide an input field for the user to enter and save their portfolio or Behance URL.
5. THE Profile_Settings SHALL provide input fields for the user to enter and save the LLM API key for the selected provider (OpenAI or Anthropic).
6. WHEN the user saves changes in Profile_Settings, THE Dashboard SHALL persist the updated User_Profile to the Database.
7. THE Profile_Settings SHALL mask LLM API key values in the UI after they are saved, displaying only the last 4 characters.

---

### Requirement 6: Review Portal Dashboard View

**User Story:** As a job seeker, I want to review the AI-generated email alongside the original job description before sending it to Gmail Drafts, so that I can verify and edit the content before it becomes a draft.

#### Acceptance Criteria

1. THE Review_Portal SHALL display the full Job Description and the AI-generated email side by side in a two-panel layout.
2. THE Review_Portal SHALL provide an editable text area for the AI-generated email so the user can modify the content before pushing it to Gmail Drafts.
3. THE Review_Portal SHALL display a "Push to Gmail Drafts" button that, when clicked, sends the current email content to the Draft_Service.
4. WHEN the "Push to Gmail Drafts" button is clicked, THE Review_Portal SHALL disable the button and show a loading indicator until the Draft_Service returns a result.
5. WHEN the Draft_Service successfully creates a Draft, THE Review_Portal SHALL display a success notification and update the visible Job_Status to `Draft Created`.
6. THE Review_Portal SHALL display the Job Title, Company Name, and Application Deadline prominently above the two-panel layout.
7. THE Review_Portal SHALL provide a button to trigger AI generation for a Job Listing that is in `Pending AI` status.

---

### Requirement 7: Data Persistence

**User Story:** As a job seeker, I want all job listings, generated emails, and my profile to be stored persistently, so that my data survives application restarts and is available across sessions.

#### Acceptance Criteria

1. THE Database SHALL store each Job Listing with the following fields: Job Title, Company Name, Full Job Description, Application Email, Application URL, Application Deadline, Job_Status, and the timestamp of when the listing was scraped.
2. THE Database SHALL store each AI-generated email body associated with its corresponding Job Listing.
3. THE Database SHALL store the User_Profile data including resume text, tech stack, GitHub URL, portfolio URL, and LLM provider selection.
4. WHEN a Job Listing with an identical Job Title, Company Name, and Job Board source already exists in the Database, THE Database SHALL not create a duplicate record.
5. THE Database SHALL support both SQLite and PostgreSQL as interchangeable backend engines, configured via an environment variable.

---

### Requirement 8: Authentication and Security

**User Story:** As a job seeker, I want my credentials and Gmail access to be handled securely, so that my account and data are protected.

#### Acceptance Criteria

1. THE Draft_Service SHALL store OAuth2 tokens in an encrypted local token store, not in plain text files.
2. THE Profile_Settings SHALL transmit LLM API keys to the backend over HTTPS only.
3. THE KaziBot SHALL NOT log LLM API key values in application logs or error messages.
4. WHEN the OAuth2 access token expires, THE Draft_Service SHALL use the stored refresh token to obtain a new access token without requiring the user to re-authenticate manually.
5. THE KaziBot SHALL load sensitive configuration values (API keys, database credentials, OAuth2 client credentials) from environment variables or a `.env` file, not from source code.
