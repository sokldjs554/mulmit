"use client";

import * as Sentry from "@sentry/browser";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { useState, type ReactNode } from "react";

import { ApiError } from "@/lib/api/client";
import { ToastProvider } from "@/components/ui/toast";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
if (dsn && typeof window !== "undefined") {
  Sentry.init({ dsn, tracesSampleRate: 0.1, environment: process.env.NEXT_PUBLIC_ENV ?? "local" });
}

function makeClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        // Don't hammer the API on auth/validation errors; retry transient ones twice.
        retry: (count, error) =>
          !(error instanceof ApiError && error.status < 500) && count < 2,
      },
      mutations: {
        onError: (error) => {
          if (!(error instanceof ApiError) || error.status >= 500) Sentry.captureException(error);
        },
      },
    },
  });
}

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(makeClient);
  return (
    <QueryClientProvider client={client}>
      <ToastProvider>{children}</ToastProvider>
      {process.env.NODE_ENV === "development" ? (
        <ReactQueryDevtools initialIsOpen={false} buttonPosition="bottom-left" />
      ) : null}
    </QueryClientProvider>
  );
}
