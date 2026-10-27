import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";
import { fetchJobs, updateJobStatus, triggerScrape } from "../api/jobs";
import JobCard from "../components/JobCard";
import LoadingSpinner from "../components/LoadingSpinner";

export default function JobFeed() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const {
    data: jobs = [],
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["jobs"],
    queryFn: () => fetchJobs(),
  });

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: "applied" | "skipped" }) =>
      updateJobStatus(id, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (err: Error) => {
      toast.error(err.message);
    },
  });

  const scrapeMutation = useMutation({
    mutationFn: triggerScrape,
    onSuccess: (data) => {
      toast.success(data.message);
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (err: Error) => {
      toast.error(`Scrape failed: ${err.message}`);
    },
  });

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-gray-900">Job Feed</h1>
        <button
          onClick={() => scrapeMutation.mutate()}
          disabled={scrapeMutation.isPending}
          className="flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60 transition"
          aria-busy={scrapeMutation.isPending}
        >
          {scrapeMutation.isPending && <LoadingSpinner size="sm" />}
          Run Scraper
        </button>
      </div>

      {/* States */}
      {isLoading && (
        <div className="flex justify-center py-16">
          <LoadingSpinner size="lg" label="Loading jobs…" />
        </div>
      )}

      {isError && (
        <p className="text-center text-sm text-red-500 py-8">
          Failed to load job listings. Make sure the backend is running.
        </p>
      )}

      {!isLoading && !isError && jobs.length === 0 && (
        <p className="text-center text-sm text-gray-400 py-16">
          No job listings yet. Click "Run Scraper" to fetch jobs.
        </p>
      )}

      {/* Grid */}
      {jobs.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {jobs.map((job) => (
            <JobCard
              key={job.id}
              job={job}
              onClick={(id) => navigate(`/review/${id}`)}
              onApply={(id) => statusMutation.mutate({ id, status: "applied" })}
              onSkip={(id) => statusMutation.mutate({ id, status: "skipped" })}
            />
          ))}
        </div>
      )}
    </div>
  );
}
