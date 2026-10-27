import type { JobStatus } from "../types";

interface StatusBadgeProps {
  status: JobStatus;
}

const statusStyles: Record<JobStatus, string> = {
  pending_ai:
    "bg-yellow-100 text-yellow-800 border border-yellow-300",
  draft_created:
    "bg-blue-100 text-blue-800 border border-blue-300",
  applied:
    "bg-green-100 text-green-800 border border-green-300",
  skipped:
    "bg-gray-100 text-gray-500 border border-gray-300",
};

const statusLabels: Record<JobStatus, string> = {
  pending_ai: "Pending AI",
  draft_created: "Draft Created",
  applied: "Applied",
  skipped: "Skipped",
};

export default function StatusBadge({ status }: StatusBadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${statusStyles[status]}`}
      data-status={status}
    >
      {statusLabels[status]}
    </span>
  );
}
