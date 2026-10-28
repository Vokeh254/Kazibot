/**
 * Property-based tests for StatusBadge component.
 *
 * # Feature: kazibot, Property 9: StatusBadge uses distinct styling per status
 *
 * For any two distinct JobStatus values, the StatusBadge component shall render
 * different visual styling (CSS class) for each — no two statuses share the same
 * badge appearance.
 *
 * Validates: Requirements 4.3
 */

import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { fc, test } from "@fast-check/vitest";
import StatusBadge from "./StatusBadge";
import type { JobStatus } from "../types";

const ALL_STATUSES: JobStatus[] = [
  "pending_ai",
  "draft_created",
  "applied",
  "skipped",
];

// ── Helper: get the className string for a given status ──────────────────────

function getClassForStatus(status: JobStatus): string {
  const { container } = render(<StatusBadge status={status} />);
  const span = container.querySelector(`[data-status="${status}"]`);
  if (!span) throw new Error(`Badge for status "${status}" not found`);
  return span.className;
}

// ── Property 9: StatusBadge uses distinct styling per status ─────────────────

describe("StatusBadge — Property 9: distinct styling per status", () => {
  it("each of the four statuses has a unique className", () => {
    const classMap = new Map<JobStatus, string>();
    for (const status of ALL_STATUSES) {
      classMap.set(status, getClassForStatus(status));
    }

    // All four class strings must be distinct
    const uniqueClasses = new Set(classMap.values());
    expect(uniqueClasses.size).toBe(ALL_STATUSES.length);
  });

  // Property-based: for any two distinct statuses, their classes differ
  test.prop(
    [
      fc.constantFrom<JobStatus>(...ALL_STATUSES),
      fc.constantFrom<JobStatus>(...ALL_STATUSES),
    ],
    { numRuns: 50 }
  )(
    "# Feature: kazibot, Property 9: StatusBadge uses distinct styling per status — two distinct statuses always have different CSS classes",
    (statusA, statusB) => {
      // Only assert when the two statuses are different
      if (statusA === statusB) return;

      const classA = getClassForStatus(statusA);
      const classB = getClassForStatus(statusB);

      expect(classA).not.toBe(classB);
    }
  );

  it("renders the correct human-readable label for each status", () => {
    const labels: Record<JobStatus, string> = {
      pending_ai: "Pending AI",
      draft_created: "Draft Created",
      applied: "Applied",
      skipped: "Skipped",
    };

    for (const [status, label] of Object.entries(labels) as [JobStatus, string][]) {
      const { getByText } = render(<StatusBadge status={status} />);
      expect(getByText(label)).toBeInTheDocument();
    }
  });
});
