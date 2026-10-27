const API_BASE = "/api";

export interface DraftResult {
  job_id: number;
  message: string;
  status: string;
}

export async function pushToDraft(jobId: number): Promise<DraftResult> {
  const res = await fetch(`${API_BASE}/drafts/${jobId}`, {
    method: "POST",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Draft creation failed: ${res.statusText}`);
  }
  return res.json();
}

export function getGmailAuthUrl(): string {
  return `${API_BASE}/auth/gmail`;
}
