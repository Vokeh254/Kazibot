import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Link, NavLink } from "react-router-dom";
import { Toaster } from "react-hot-toast";

import JobFeed from "./pages/JobFeed";
import ReviewPortal from "./pages/ReviewPortal";
import ProfileSettings from "./pages/ProfileSettings";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000, // 30 s
      retry: 1,
    },
  },
});

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `text-sm font-medium transition hover:text-blue-600 ${
    isActive ? "text-blue-600" : "text-gray-600"
  }`;

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Toaster position="top-right" />

        <div className="flex min-h-screen flex-col bg-gray-50">
          {/* Navigation shell */}
          <header className="sticky top-0 z-10 border-b bg-white px-6 py-3 shadow-sm">
            <div className="mx-auto flex max-w-7xl items-center justify-between">
              <Link to="/" className="text-base font-bold text-blue-700">
                🤖 KaziBot
              </Link>
              <nav className="flex gap-6">
                <NavLink to="/" end className={navLinkClass}>
                  Job Feed
                </NavLink>
                <NavLink to="/profile" className={navLinkClass}>
                  Profile
                </NavLink>
              </nav>
            </div>
          </header>

          {/* Page content */}
          <main className="flex-1 p-6">
            <div className="mx-auto max-w-7xl">
              <Routes>
                <Route path="/" element={<JobFeed />} />
                <Route path="/review/:id" element={<ReviewPortal />} />
                <Route path="/profile" element={<ProfileSettings />} />
              </Routes>
            </div>
          </main>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
