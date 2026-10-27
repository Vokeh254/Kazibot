const API_BASE = "/api";

export interface GenerateResult {
  job_id: number;
  email_body: string;
  message: string;
}

export async function generateEmail(jobId: number): Promise<GenerateResult> {
  const res = await fetch(`${API_BASE}/ai/generate/${jobId}`, {
    method: "POST",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `AI generation failed: ${res.statusText}`);
  }
  return res.json();
}
