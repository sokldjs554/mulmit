import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type Schemas = components["schemas"];

/**
 * Typed API client. Requests go to the same origin (`/api/*`), which the Next.js BFF route
 * forwards to the FastAPI service — so the httpOnly session cookie is first-party and the
 * browser never needs CORS.
 */
export const api = createClient<paths>({ baseUrl: "", credentials: "include" });

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function detailMessage(error: unknown): string {
  if (error && typeof error === "object" && "detail" in error) {
    const detail = (error as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: string };
      return first.msg ?? "입력값을 확인해 주세요";
    }
  }
  return "요청을 처리하지 못했습니다";
}

/** Unwrap an openapi-fetch result: return data or throw a typed ApiError. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error !== undefined || !result.response.ok) {
    throw new ApiError(result.response.status, detailMessage(result.error));
  }
  return result.data as T;
}

export function newIdempotencyKey(prefix: string): string {
  const random =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2);
  return `${prefix}-${random}`;
}
