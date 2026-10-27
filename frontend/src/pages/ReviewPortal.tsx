import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import { fetchJob } from "../api/jobs";
import { generateEmail } from "../api/ai";
import { pushToDraft } from "../api/drafts";
import LoadingSpinner from "../components/LoadingSpinner";
import StatusBadge from "../components/StatusBadge";

function formatDeadline(deadline: string | null): string {
  if (!deadline) return "No deadline";
  try {
    return new Date(deadline).toLocaleDateString("en-KE", {
      day: "numeric",
      month: "long",
      year: "numeric",
    });
  } catch {
    return deadline;
  }
}

export default function ReviewPortal() {
  const { id } = useParams<{ id: string }>();
  const jobId = Number(id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const {
    data: job,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => fetchJob(jobId),
    enabled: !isNaN(jobId),
  });

  const [emailBody, setEmailBody] = useState("");

  // Keep the editable body in sync with the fetched generated email
  useEffect(() => {
    if (job?.generated_email?.email_body) {
      setEmailBody(job.generated_email.email_body);
    }
  }, [job?.generated_email?.email_body]);

  const generateMutation = useMutation({
    mutationFn: () => generateEmail(jobId),
    onSuccess: (data) => {
      setEmailBody(data.email_body);
      toast.success("Cover letter generated!");
      queryClient.invalidateQueries({ queryKey: ["job", jobId] });
    },
    onError: (err: Error) => {
      toast.error(`Generation failed: ${err.message}`);
    },
  });

  const draftMutation = useMutation({
    mutationFn: () => pushToDraft(jobId),
    onSuccess: (data) => {
      toast.success(data.message);
      queryClient.invalidateQueries({ queryKey: ["job", jobId] });
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (err: Error) => {
      if (err.message.includes("401") || err.message.toLowerCase().includes("auth")) {
        toast.error("Gmail not connected. Please connect Gmail in Profile Settings.");
      } else {
        toast.error(`Draft failed: ${err.message}`);
      }
    },
  });

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <LoadingSpinner size="lg" label="Loading job…" />
      </div>
    );
  }

  if (isError || !job) {
    return (
      <div className="space-y-2 text-center py-16">
        <p className="text-red-500">Job not found or failed to load.</p>
        <button
          onClick={() => navigate("/")}
          className="text-sm text-blue-600 underline"
        >
          Back to Job Feed
        </button>
      </div>
    );
  }

  const currentStatus = draftMutation.isSuccess ? "draft_created" : job.status;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <button
            onClick={() => navigate("/")}
            className="mb-1 text-xs text-blue-600 hover:underline"
          >
            ← Back to Job Feed
          </button>
          <h1 className="text-xl font-bold text-gray-900">{job.title}</h1>
          <p className="text-sm text-gray-500">{job.company}</p>
          <p className="text-xs text-gray-400 mt-0.5">
            Deadline: {formatDeadline(job.deadline)}
          </p>
        </div>
        <StatusBadge status={currentStatus} />
      </div>

      {/* Two-panel layout */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Left: Job Description */}
        <section className="rounded-lg border border-gray-200 bg-white p-4">
          <h2 className="mb-2 text-sm font-semibold text-gray-700">
            Job Description
          </h2>
          <pre className="whitespace-pre-wrap text-xs text-gray-600 leading-relaxed max-h-[60vh] overflow-y-auto">
            {job.description || "No description available."}
          </pre>
        </section>

        {/* Right: Generated Email */}
        <section className="rounded-lg border border-gray-200 bg-white p-4 flex flex-col gap-3">
          <h2 className="text-sm font-semibold text-gray-700">
            Cover Letter Email
          </h2>

          {job.status === "pending_ai" && !job.generated_email && (
            <button
              onClick={() => generateMutation.mutate()}
              disabled={generateMutation.isPending}
              className="flex items-center justify-center gap-2 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60 transition"
              aria-busy={generateMutation.isPending}
            >
              {generateMutation.isPending && <LoadingSpinner size="sm" />}
              Generate Cover Letter
            </button>
          )}

          <textarea
            className="flex-1 min-h-[40vh] w-full rounded border border-gray-300 p-3 text-xs text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-400 resize-y"
            value={emailBody}
            onChange={(e) => setEmailBody(e.target.value)}
            placeholder="Click 'Generate Cover Letter' to create a personalised email…"
            aria-label="Generated cover letter email body"
          />

          <div className="flex gap-2">
            {job.generated_email && (
              <button
                onClick={() => generateMutation.mutate()}
                disabled={generateMutation.isPending}
                className="flex items-center gap-1.5 rounded border border-indigo-300 px-3 py-1.5 text-xs font-medium text-indigo-700 hover:bg-indigo-50 disabled:opacity-60 transition"
              >
                {generateMutation.isPending && <LoadingSpinner size="sm" />}
                Regenerate
              </button>
            )}

            <button
              onClick={() => draftMutation.mutate()}
              disabled={
                !emailBody.trim() ||
                draftMutation.isPending ||
                draftMutation.isSuccess
              }
              className="flex flex-1 items-center justify-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60 transition"
              aria-busy={draftMutation.isPending}
            >
              {draftMutation.isPending && <LoadingSpinner size="sm" />}
              {draftMutation.isSuccess
                ? "✓ Draft Created"
                : "Push to Gmail Drafts"}
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}
