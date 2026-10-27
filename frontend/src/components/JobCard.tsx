import type { JobListing } from "../types";
import StatusBadge from "./StatusBadge";

interface JobCardProps {
  job: JobListing;
  onSkip?: (id: number) => void;
  onApply?: (id: number) => void;
  onClick?: (id: number) => void;
}

function formatDeadline(deadline: string | null): string {
  if (!deadline) return "No deadline";
  try {
    return new Date(deadline).toLocaleDateString("en-KE", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  } catch {
    return deadline;
  }
}

export default function JobCard({
  job,
  onSkip,
  onApply,
  onClick,
}: JobCardProps) {
  return (
    <article
      className="flex flex-col gap-3 rounded-lg border border-gray-200 bg-white p-4 shadow-sm transition hover:shadow-md cursor-pointer"
      onClick={() => onClick?.(job.id)}
      aria-label={`${job.title} at ${job.company}`}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-gray-900 leading-snug">
            {job.title}
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">{job.company}</p>
        </div>
        <StatusBadge status={job.status} />
      </div>

      {/* Meta */}
      <div className="flex flex-wrap items-center gap-3 text-xs text-gray-400">
        <span>
          <span className="font-medium text-gray-600">Deadline:</span>{" "}
          {formatDeadline(job.deadline)}
        </span>
        <span className="capitalize">{job.board_source.replace(/_/g, " ")}</span>
      </div>

      {/* Actions */}
      {(onSkip || onApply) && (
        <div
          className="flex gap-2 pt-1"
          onClick={(e) => e.stopPropagation()}
        >
          {onApply && job.status !== "applied" && (
            <button
              onClick={() => onApply(job.id)}
              className="rounded px-2.5 py-1 text-xs font-medium text-green-700 border border-green-300 hover:bg-green-50 transition"
              aria-label={`Mark ${job.title} as applied`}
            >
              Applied
            </button>
          )}
          {onSkip && job.status !== "skipped" && (
            <button
              onClick={() => onSkip(job.id)}
              className="rounded px-2.5 py-1 text-xs font-medium text-gray-500 border border-gray-300 hover:bg-gray-50 transition"
              aria-label={`Skip ${job.title}`}
            >
              Skip
            </button>
          )}
        </div>
      )}
    </article>
  );
}
