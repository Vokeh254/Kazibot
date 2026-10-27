// Shared TypeScript types — mirrors backend Pydantic schemas

export type JobStatus = "pending_ai" | "draft_created" | "applied" | "skipped";

export interface GeneratedEmail {
  id: number;
  email_body: string;
  created_at: string;
  updated_at: string;
}

export interface JobListing {
  id: number;
  title: string;
  company: string;
  description: string | null;
  application_email: string | null;
  application_url: string | null;
  deadline: string | null;
  status: JobStatus;
  board_source: string;
  scraped_at: string;
  generated_email: GeneratedEmail | null;
}

export interface UserProfile {
  id: number;
  resume_markdown: string | null;
  tech_stack: string[] | null;
  github_url: string | null;
  portfolio_url: string | null;
  llm_provider: string | null;
  llm_api_key_masked: string | null;
}

export interface UserProfileRequest {
  resume_markdown?: string;
  tech_stack?: string[];
  github_url?: string;
  portfolio_url?: string;
  llm_provider?: "openai" | "anthropic";
  llm_api_key?: string;
}
