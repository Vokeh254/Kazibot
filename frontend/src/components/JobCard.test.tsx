/**
 * Property-based tests for JobCard component.
 *
 * # Feature: kazibot, Property 8: JobCard renders all required fields
 *
 * For any JobListing object, the rendered JobCard component shall contain
 * the Job Title, Company Name, Application Deadline, and Job_Status in its output.
 *
 * Validates: Requirements 4.2
 */

import { describe, afterEach } from "vitest";
import { render, cleanup, within } from "@testing-library/react";
import { fc, test } from "@fast-check/vitest";
import JobCard from "./JobCard";
import type { JobListing, JobStatus } from "../types";

// Cleanup DOM between each property run to avoid stale elements
afterEach(() => cleanup());

// ── Arbitraries ────────────────────────────────────────────────────────────

const jobStatusArb = fc.constantFrom<JobStatus>(
  "pending_ai",
  "draft_created",
  "applied",
  "skipped"
);

const jobListingArb = fc.record<JobListing>({
  id: fc.integer({ min: 1, max: 999999 }),
  title: fc.string({ minLength: 1, maxLength: 80 }).filter((s) => s.trim().length > 0),
  company: fc.string({ minLength: 1, maxLength: 80 }).filter((s) => s.trim().length > 0),
  description: fc.option(fc.string({ minLength: 1, maxLength: 500 }), { nil: null }),
  application_email: fc.option(fc.emailAddress(), { nil: null }),
  application_url: fc.option(fc.webUrl(), { nil: null }),
  deadline: fc.option(
    fc.date({ min: new Date("2025-01-01"), max: new Date("2027-12-31") })
      .map((d) => d.toISOString().split("T")[0]),
    { nil: null }
  ),
  status: jobStatusArb,
  board_source: fc.constantFrom("fuzu", "brighter_monday", "my_job_mag"),
  scraped_at: fc.date().map((d) => d.toISOString()),
  generated_email: fc.constant(null),
});

// ── Property 8: JobCard renders all required fields ────────────────────────

describe("JobCard — Property 8: renders all required fields", () => {
  test.prop([jobListingArb])(
    "# Feature: kazibot, Property 8: JobCard renders all required fields — title, company, deadline, and status badge are always present",
    (job) => {
      // Render into a fresh container each run; use `within` to scope queries
      const { container } = render(<JobCard job={job} />);
      const utils = within(container);

      // Title must appear in the rendered article
      const titleEl = utils.getByRole("heading", { level: 2 });
      expect(titleEl.textContent?.trim()).toBe(job.title.trim());

      // Company name must appear somewhere in the card's text content
      const article = utils.getByRole("article");
      expect(article.textContent).toContain(job.company.trim());

      // Status badge identified by data-status attribute
      const badge = container.querySelector(`[data-status="${job.status}"]`);
      expect(badge).not.toBeNull();

      // Deadline section always rendered
      expect(article.textContent).toMatch(/Deadline/i);

      // Clean up after each individual property example
      cleanup();
    }
  );
});
