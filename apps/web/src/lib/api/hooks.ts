"use client";

import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { api, newIdempotencyKey, unwrap, type Schemas } from "./client";

export const qk = {
  me: ["me"] as const,
  feed: (filters: FeedFilters) => ["feed", filters] as const,
  opportunity: (id: number) => ["opportunity", id] as const,
  profile: ["profile"] as const,
  institutions: ["institutions"] as const,
  categories: ["categories"] as const,
  alertRule: ["alerts", "rule"] as const,
  channels: ["alerts", "channels"] as const,
  notifications: ["alerts", "notifications"] as const,
  billing: ["billing"] as const,
  admin: {
    overview: ["admin", "overview"] as const,
    sources: ["admin", "sources"] as const,
    jobs: (status?: string) => ["admin", "jobs", status ?? "all"] as const,
    review: (status: string) => ["admin", "review", status] as const,
    llm: (days: number) => ["admin", "llm", days] as const,
    evals: ["admin", "evals"] as const,
    document: (id: number) => ["admin", "document", id] as const,
  },
};

// --- session ---------------------------------------------------------------------------------
export function useMe() {
  return useQuery({
    queryKey: qk.me,
    queryFn: async () => unwrap(await api.GET("/api/me")),
    retry: false,
    staleTime: 60_000,
  });
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas["LoginIn"]) =>
      unwrap(await api.POST("/api/auth/login", { body })),
    onSuccess: (me) => {
      qc.clear();
      qc.setQueryData(qk.me, me);
    },
  });
}

export function useSignup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas["SignupIn"]) =>
      unwrap(await api.POST("/api/auth/signup", { body })),
    onSuccess: (me) => {
      qc.clear();
      qc.setQueryData(qk.me, me);
    },
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      await api.POST("/api/auth/logout");
    },
    onSuccess: () => qc.clear(),
  });
}

// --- feed & opportunities ----------------------------------------------------------------------
export type FeedSort = "score" | "soon" | "recent";

export type FeedFilters = {
  stage?: string[];
  category?: string[];
  status?: string[];
  q?: string;
  sort?: FeedSort;
};

export function useFeed(filters: FeedFilters) {
  return useInfiniteQuery({
    queryKey: qk.feed(filters),
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam }) =>
      unwrap(
        await api.GET("/api/opportunities", {
          params: {
            query: {
              stage: filters.stage?.length ? filters.stage : undefined,
              category: filters.category?.length ? filters.category : undefined,
              status: filters.status?.length ? filters.status : undefined,
              q: filters.q || undefined,
              sort: filters.sort,
              cursor: pageParam,
              limit: 20,
            },
          },
        }),
      ),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    placeholderData: keepPreviousData,
  });
}

export function useOpportunity(id: number) {
  return useQuery({
    queryKey: qk.opportunity(id),
    queryFn: async () =>
      unwrap(
        await api.GET("/api/opportunities/{opportunity_id}", {
          params: { path: { opportunity_id: id } },
        }),
      ),
    enabled: Number.isFinite(id),
  });
}

type Feedback = Schemas["FeedbackIn"]["feedback"];

export function useFeedback(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (feedback: Feedback) => {
      const res = await api.POST("/api/opportunities/{opportunity_id}/feedback", {
        params: { path: { opportunity_id: id } },
        body: { feedback },
      });
      if (!res.response.ok) unwrap(res);
    },
    // Optimistic: the button reflects the choice immediately; roll back on error.
    onMutate: async (feedback) => {
      await qc.cancelQueries({ queryKey: qk.opportunity(id) });
      const previous = qc.getQueryData<Schemas["OpportunityDetail"]>(qk.opportunity(id));
      if (previous) qc.setQueryData(qk.opportunity(id), { ...previous, feedback });
      return { previous };
    },
    onError: (_err, _feedback, ctx) => {
      if (ctx?.previous) qc.setQueryData(qk.opportunity(id), ctx.previous);
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["feed"] });
    },
  });
}

export function useCreateBrief(id: number) {
  const qc = useQueryClient();
  return useMutation({
    // One idempotency key per click: a double-click or a network retry cannot charge twice.
    mutationFn: async (idempotencyKey?: string) =>
      unwrap(
        await api.POST("/api/opportunities/{opportunity_id}/briefs", {
          params: {
            path: { opportunity_id: id },
            header: { "Idempotency-Key": idempotencyKey ?? newIdempotencyKey("brief") },
          },
        }),
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: qk.opportunity(id) });
      void qc.invalidateQueries({ queryKey: qk.me });
      void qc.invalidateQueries({ queryKey: qk.billing });
    },
  });
}

// --- profile ---------------------------------------------------------------------------------
export function useProfile() {
  return useQuery({
    queryKey: qk.profile,
    queryFn: async () => unwrap(await api.GET("/api/profile")),
  });
}

export function useSaveProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas["ProfileIO"]) =>
      unwrap(await api.PUT("/api/profile", { body })),
    onSuccess: (profile) => {
      qc.setQueryData(qk.profile, profile);
      void qc.invalidateQueries({ queryKey: ["feed"] });
    },
  });
}

export function useInstitutions() {
  return useQuery({
    queryKey: qk.institutions,
    queryFn: async () => unwrap(await api.GET("/api/institutions")),
    staleTime: Infinity,
  });
}

export function useCategories() {
  return useQuery({
    queryKey: qk.categories,
    queryFn: async () => unwrap(await api.GET("/api/categories")),
    staleTime: Infinity,
  });
}

// --- alerts ----------------------------------------------------------------------------------
export function useAlertRule() {
  return useQuery({
    queryKey: qk.alertRule,
    queryFn: async () => unwrap(await api.GET("/api/alerts/rule")),
  });
}

export function useSaveAlertRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas["AlertRuleIO"]) =>
      unwrap(await api.PUT("/api/alerts/rule", { body })),
    onSuccess: (rule) => qc.setQueryData(qk.alertRule, rule),
  });
}

export function useChannels() {
  return useQuery({
    queryKey: qk.channels,
    queryFn: async () => unwrap(await api.GET("/api/alerts/channels")),
  });
}

export function useAddChannel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas["AlertChannelIn"]) =>
      unwrap(await api.POST("/api/alerts/channels", { body })),
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.channels }),
  });
}

export function useDeleteChannel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (channelId: number) => {
      const res = await api.DELETE("/api/alerts/channels/{channel_id}", {
        params: { path: { channel_id: channelId } },
      });
      if (!res.response.ok) unwrap(res);
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.channels }),
  });
}

export function useTestChannel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (channelId: number) =>
      unwrap(
        await api.POST("/api/alerts/channels/{channel_id}/test", {
          params: { path: { channel_id: channelId } },
        }),
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: qk.notifications });
      void qc.invalidateQueries({ queryKey: qk.channels });
    },
  });
}

export function useNotifications() {
  return useQuery({
    queryKey: qk.notifications,
    queryFn: async () => unwrap(await api.GET("/api/alerts/notifications")),
    refetchInterval: 15_000,
  });
}

// --- billing ---------------------------------------------------------------------------------
export function useBilling() {
  return useQuery({
    queryKey: qk.billing,
    queryFn: async () => unwrap(await api.GET("/api/billing")),
  });
}

function invalidateBilling(qc: ReturnType<typeof useQueryClient>) {
  void qc.invalidateQueries({ queryKey: qk.billing });
  void qc.invalidateQueries({ queryKey: qk.me });
}

export function useRegisterCard() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas["CardIn"]) =>
      unwrap(await api.POST("/api/billing/card", { body })),
    onSuccess: () => invalidateBilling(qc),
  });
}

export function useChangePlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (plan: Schemas["PlanChangeIn"]["plan"]) =>
      unwrap(
        await api.POST("/api/billing/plan", {
          body: { plan },
          params: { header: { "Idempotency-Key": newIdempotencyKey("plan") } },
        }),
      ),
    onSettled: () => invalidateBilling(qc),
  });
}

export function useBuyCredits() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (pack: string) =>
      unwrap(
        await api.POST("/api/billing/credits", {
          body: { pack },
          params: { header: { "Idempotency-Key": newIdempotencyKey("pack") } },
        }),
      ),
    onSettled: () => invalidateBilling(qc),
  });
}

// --- admin -------------------------------------------------------------------------------------
export function useAdminOverview() {
  return useQuery({
    queryKey: qk.admin.overview,
    queryFn: async () => unwrap(await api.GET("/api/admin/overview")),
    refetchInterval: 20_000,
  });
}

export function useAdminSources() {
  return useQuery({
    queryKey: qk.admin.sources,
    queryFn: async () => unwrap(await api.GET("/api/admin/sources")),
    refetchInterval: 20_000,
  });
}

export function useRunSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (key: string) =>
      unwrap(
        await api.POST("/api/admin/sources/{key}/run", {
          params: { path: { key } },
          body: {},
        }),
      ),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["admin"] }),
  });
}

export function useToggleSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ key, enabled }: { key: string; enabled: boolean }) =>
      unwrap(
        await api.PATCH("/api/admin/sources/{key}", {
          params: { path: { key } },
          body: { enabled },
        }),
      ),
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.admin.sources }),
  });
}

export function useAdminJobs(status?: string) {
  return useQuery({
    queryKey: qk.admin.jobs(status),
    queryFn: async () =>
      unwrap(await api.GET("/api/admin/jobs", { params: { query: { status, limit: 100 } } })),
    refetchInterval: 10_000,
  });
}

export function useRetryJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (runId: number) =>
      unwrap(
        await api.POST("/api/admin/jobs/{run_id}/retry", { params: { path: { run_id: runId } } }),
      ),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["admin", "jobs"] }),
  });
}

export function useReviewQueue(status: string) {
  return useQuery({
    queryKey: qk.admin.review(status),
    queryFn: async () =>
      unwrap(await api.GET("/api/admin/review", { params: { query: { status } } })),
  });
}

export function useDecideReview() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, body }: { id: number; body: Schemas["ReviewDecisionIn"] }) =>
      unwrap(
        await api.POST("/api/admin/review/{item_id}", { params: { path: { item_id: id } }, body }),
      ),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["admin"] }),
  });
}

export function useLlmUsage(days: number) {
  return useQuery({
    queryKey: qk.admin.llm(days),
    queryFn: async () =>
      unwrap(await api.GET("/api/admin/llm/usage", { params: { query: { days } } })),
    placeholderData: keepPreviousData,
  });
}

export function useEvals() {
  return useQuery({
    queryKey: qk.admin.evals,
    queryFn: async () => unwrap(await api.GET("/api/admin/evals")),
  });
}

export function useAdminDocument(id: number | null) {
  return useQuery({
    queryKey: qk.admin.document(id ?? -1),
    queryFn: async () =>
      unwrap(
        await api.GET("/api/admin/documents/{document_id}", {
          params: { path: { document_id: id as number } },
        }),
      ),
    enabled: id !== null,
  });
}
