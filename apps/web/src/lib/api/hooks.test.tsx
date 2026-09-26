import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "./client";
import { useBuyCredits, useChangePlan, useCreateBrief } from "./hooks";

// Charged requests must reuse one Idempotency-Key across retries, or a retry after a lost
// response would charge again. These tests pin that down at the hook level.

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { mutations: { retryDelay: 0 } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const ok = (data: unknown) => ({ data, error: undefined, response: new Response(null, { status: 200 }) });
const failed = (status: number, detail: string) => ({
  data: undefined,
  error: { detail },
  response: new Response(null, { status }),
});

function mockPost() {
  return vi.spyOn(api, "POST");
}

function sentKeys(post: ReturnType<typeof mockPost>): string[] {
  return post.mock.calls.map(
    (call) => (call[1] as { params: { header: Record<string, string> } }).params.header["Idempotency-Key"]!,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("useCreateBrief", () => {
  it("retries a dropped connection with the same key", async () => {
    const post = mockPost()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(ok({ id: 1 }) as never);
    const { result } = renderHook(() => useCreateBrief(7), { wrapper });

    act(() => result.current.mutate("brief-click-1"));

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(sentKeys(post)).toEqual(["brief-click-1", "brief-click-1"]);
  });

  it("retries a server error with the same key", async () => {
    const post = mockPost()
      .mockResolvedValueOnce(failed(503, "잠시 후 다시 해 주세요") as never)
      .mockResolvedValueOnce(ok({ id: 1 }) as never);
    const { result } = renderHook(() => useCreateBrief(7), { wrapper });

    act(() => result.current.mutate("brief-click-1"));

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(sentKeys(post)).toEqual(["brief-click-1", "brief-click-1"]);
  });

  it("does not retry when the API says no (not enough credits)", async () => {
    const post = mockPost().mockResolvedValue(failed(402, "크레딧이 모자라요") as never);
    const { result } = renderHook(() => useCreateBrief(7), { wrapper });

    act(() => result.current.mutate("brief-click-1"));

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(post).toHaveBeenCalledTimes(1);
    expect(result.current.error).toBeInstanceOf(ApiError);
    expect((result.current.error as ApiError).message).toBe("크레딧이 모자라요");
  });

  it("stops after two retries", async () => {
    const post = mockPost().mockRejectedValue(new TypeError("Failed to fetch"));
    const { result } = renderHook(() => useCreateBrief(7), { wrapper });

    act(() => result.current.mutate("brief-click-1"));

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(sentKeys(post)).toEqual(["brief-click-1", "brief-click-1", "brief-click-1"]);
  });
});

describe("billing mutations", () => {
  it("keeps the plan-change key across a retry", async () => {
    const post = mockPost()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(ok({}) as never);
    const { result } = renderHook(() => useChangePlan(), { wrapper });

    act(() => result.current.mutate({ plan: "pro", idempotencyKey: "plan-click-1" }));

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(sentKeys(post)).toEqual(["plan-click-1", "plan-click-1"]);
  });

  it("keeps the credit-pack key across a retry", async () => {
    const post = mockPost()
      .mockResolvedValueOnce(failed(502, "서버에 연결하지 못했어요") as never)
      .mockResolvedValueOnce(ok({}) as never);
    const { result } = renderHook(() => useBuyCredits(), { wrapper });

    act(() => result.current.mutate({ pack: "p30", idempotencyKey: "pack-click-1" }));

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(sentKeys(post)).toEqual(["pack-click-1", "pack-click-1"]);
  });
});
