import type { JobListing, JobStatus } from "../types";

const API_BASE = "/api";

export async function fetchJobs(status?: JobStatus): Promise<JobListing[]> {
  const url = status
    ? `${API_BASE}/jobs?status=${status}`
    : `${API_BASE}/jobs`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch jobs: ${res.statusText}`);
  return res.json();
}

export async function fetchJob(id: number): Promise<JobListing> {
  const res = await fetch(`${API_BASE}/jobs/${id}`);
  if (!res.ok) throw new Error(`Failed to fetch job ${id}: ${res.statusText}`);
  return res.json();
}

export async function updateJobStatus(
  id: number,
  status: "applied" | "skipped"
): Promise<JobListing> {
  const res = await fetch(`${API_BASE}/jobs/${id}/status`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (!res.ok) throw new Error(`Failed to update job status: ${res.statusText}`);
  return res.json();
}

export async function triggerScrape(): Promise<{ new_listings: number; message: string }> {
  const res = await fetch(`${API_BASE}/scrape`, { method: "POST" });
  if (!res.ok) throw new Error(`Scrape failed: ${res.statusText}`);
  return res.json();
}
