import { ErrorBoundary } from "@/components/ErrorBoundary";
import { Layout } from "@/components/Layout";
import { ThemeProvider } from "@/components/theme-provider";
import { Skeleton } from "@/components/ui/skeleton";
import { Toaster } from "@/components/ui/sonner";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "framer-motion";
import { Suspense, lazy } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";

const Landing = lazy(() => import("@/routes/index"));
const Analysis = lazy(() => import("@/routes/analysis"));
const About = lazy(() => import("@/routes/about"));

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

function RouteFallback() {
  return (
    <div className="space-y-4 pt-6">
      <Skeleton className="mx-auto h-10 w-2/3" />
      <Skeleton className="h-48 w-full" />
    </div>
  );
}

export function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider>
        <QueryClientProvider client={queryClient}>
          <MotionConfig reducedMotion="user">
            <BrowserRouter>
              <Layout>
                <Suspense fallback={<RouteFallback />}>
                  <Routes>
                    <Route path="/" element={<Landing />} />
                    <Route path="/analysis/:id" element={<Analysis />} />
                    <Route path="/about" element={<About />} />
                  </Routes>
                </Suspense>
              </Layout>
            </BrowserRouter>
          </MotionConfig>
          <Toaster />
        </QueryClientProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}
