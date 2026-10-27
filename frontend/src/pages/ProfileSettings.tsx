import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import { fetchProfile, updateProfile } from "../api/profile";
import { getGmailAuthUrl } from "../api/drafts";
import LoadingSpinner from "../components/LoadingSpinner";

export default function ProfileSettings() {
  const queryClient = useQueryClient();

  const { data: profile, isLoading } = useQuery({
    queryKey: ["profile"],
    queryFn: fetchProfile,
  });

  const [resumeMarkdown, setResumeMarkdown] = useState("");
  const [techStack, setTechStack] = useState("");
  const [githubUrl, setGithubUrl] = useState("");
  const [portfolioUrl, setPortfolioUrl] = useState("");
  const [llmProvider, setLlmProvider] = useState<"openai" | "anthropic">("openai");
  const [apiKey, setApiKey] = useState("");
  const [keyMasked, setKeyMasked] = useState(false);

  // Populate form when profile is loaded
  useEffect(() => {
    if (profile) {
      setResumeMarkdown(profile.resume_markdown ?? "");
      setTechStack((profile.tech_stack ?? []).join(", "));
      setGithubUrl(profile.github_url ?? "");
      setPortfolioUrl(profile.portfolio_url ?? "");
      setLlmProvider((profile.llm_provider as "openai" | "anthropic") ?? "openai");
      if (profile.llm_api_key_masked) {
        setApiKey(profile.llm_api_key_masked);
        setKeyMasked(true);
      }
    }
  }, [profile]);

  const saveMutation = useMutation({
    mutationFn: () => {
      const payload: Record<string, unknown> = {
        resume_markdown: resumeMarkdown || undefined,
        tech_stack: techStack
          ? techStack.split(",").map((s) => s.trim()).filter(Boolean)
          : undefined,
        github_url: githubUrl || undefined,
        portfolio_url: portfolioUrl || undefined,
        llm_provider: llmProvider,
      };
      // Only send the key if the user typed a new value (not the masked form)
      if (apiKey && !keyMasked) {
        payload.llm_api_key = apiKey;
      }
      return updateProfile(payload);
    },
    onSuccess: (data) => {
      toast.success("Profile saved successfully.");
      queryClient.invalidateQueries({ queryKey: ["profile"] });
      // Mask the key after save
      if (data.llm_api_key_masked) {
        setApiKey(data.llm_api_key_masked);
        setKeyMasked(true);
      }
    },
    onError: (err: Error) => {
      toast.error(`Save failed: ${err.message}`);
    },
  });

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <LoadingSpinner size="lg" label="Loading profile…" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <h1 className="text-lg font-semibold text-gray-900">Profile Settings</h1>

      {/* Resume */}
      <section className="space-y-2">
        <label
          htmlFor="resume"
          className="block text-sm font-medium text-gray-700"
        >
          Resume (Markdown)
        </label>
        <textarea
          id="resume"
          rows={10}
          value={resumeMarkdown}
          onChange={(e) => setResumeMarkdown(e.target.value)}
          placeholder="Paste your resume in Markdown format…"
          className="w-full rounded border border-gray-300 p-3 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-400 resize-y"
        />
      </section>

      {/* Tech Stack */}
      <section className="space-y-2">
        <label
          htmlFor="techStack"
          className="block text-sm font-medium text-gray-700"
        >
          Tech Stack (comma-separated)
        </label>
        <input
          id="techStack"
          type="text"
          value={techStack}
          onChange={(e) => setTechStack(e.target.value)}
          placeholder="Python, React, TypeScript, PostgreSQL…"
          className="w-full rounded border border-gray-300 px-3 py-2 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-400"
        />
      </section>

      {/* GitHub URL */}
      <section className="space-y-2">
        <label
          htmlFor="github"
          className="block text-sm font-medium text-gray-700"
        >
          GitHub Profile URL
        </label>
        <input
          id="github"
          type="url"
          value={githubUrl}
          onChange={(e) => setGithubUrl(e.target.value)}
          placeholder="https://github.com/your-username"
          className="w-full rounded border border-gray-300 px-3 py-2 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-400"
        />
      </section>

      {/* Portfolio URL */}
      <section className="space-y-2">
        <label
          htmlFor="portfolio"
          className="block text-sm font-medium text-gray-700"
        >
          Portfolio / Behance URL
        </label>
        <input
          id="portfolio"
          type="url"
          value={portfolioUrl}
          onChange={(e) => setPortfolioUrl(e.target.value)}
          placeholder="https://behance.net/your-username or https://yourportfolio.com"
          className="w-full rounded border border-gray-300 px-3 py-2 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-400"
        />
      </section>

      {/* LLM Provider */}
      <section className="space-y-2">
        <label
          htmlFor="llmProvider"
          className="block text-sm font-medium text-gray-700"
        >
          LLM Provider
        </label>
        <select
          id="llmProvider"
          value={llmProvider}
          onChange={(e) => setLlmProvider(e.target.value as "openai" | "anthropic")}
          className="w-full rounded border border-gray-300 px-3 py-2 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-400"
        >
          <option value="openai">OpenAI (GPT-4o-mini)</option>
          <option value="anthropic">Anthropic (Claude Haiku)</option>
        </select>
      </section>

      {/* API Key */}
      <section className="space-y-2">
        <label
          htmlFor="apiKey"
          className="block text-sm font-medium text-gray-700"
        >
          LLM API Key
        </label>
        <input
          id="apiKey"
          type={keyMasked ? "text" : "password"}
          value={apiKey}
          onChange={(e) => {
            setApiKey(e.target.value);
            setKeyMasked(false);
          }}
          onFocus={() => {
            if (keyMasked) {
              setApiKey("");
              setKeyMasked(false);
            }
          }}
          placeholder="sk-… or enter new key to update"
          className="w-full rounded border border-gray-300 px-3 py-2 text-sm font-mono text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-400"
          autoComplete="new-password"
        />
        {keyMasked && (
          <p className="text-xs text-gray-400">
            API key is set. Click the field to update it.
          </p>
        )}
      </section>

      {/* Save button */}
      <button
        onClick={() => saveMutation.mutate()}
        disabled={saveMutation.isPending}
        className="flex w-full items-center justify-center gap-2 rounded-md bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60 transition"
        aria-busy={saveMutation.isPending}
      >
        {saveMutation.isPending && <LoadingSpinner size="sm" />}
        Save Profile
      </button>

      {/* Gmail Connect */}
      <div className="rounded-lg border border-gray-200 p-4 flex items-center justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-gray-800">Gmail Integration</p>
          <p className="text-xs text-gray-500">
            Connect your Gmail account to push cover letters as drafts.
          </p>
        </div>
        <a
          href={getGmailAuthUrl()}
          className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition whitespace-nowrap"
        >
          Connect Gmail
        </a>
      </div>
    </div>
  );
}
