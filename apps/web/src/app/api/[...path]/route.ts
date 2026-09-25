/**
 * Backend-for-frontend proxy: `/api/*` → FastAPI (`API_ORIGIN`, read at request time).
 *
 * Why not `rewrites` in next.config? Rewrites are resolved at build time, and the same image
 * is promoted from staging to production with a different API URL. Proxying here also keeps
 * the session cookie first-party and strips hop-by-hop headers explicitly.
 */
import type { NextRequest } from "next/server";

const API_ORIGIN = () => process.env.API_ORIGIN ?? "http://localhost:8000";
const FORWARD_REQUEST_HEADERS = [
  "content-type",
  "cookie",
  "authorization",
  "idempotency-key",
  "x-request-id",
  "accept",
];
const FORWARD_RESPONSE_HEADERS = ["content-type", "set-cookie", "x-request-id", "retry-after"];

async function proxy(request: NextRequest, ctx: RouteContext<"/api/[...path]">): Promise<Response> {
  const { path } = await ctx.params;
  const target = new URL(`/api/${path.map(encodeURIComponent).join("/")}`, API_ORIGIN());
  target.search = request.nextUrl.search;

  const headers = new Headers();
  for (const name of FORWARD_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const forwardedFor = request.headers.get("x-forwarded-for");
  if (forwardedFor) headers.set("x-forwarded-for", forwardedFor);

  const hasBody = !["GET", "HEAD"].includes(request.method);
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      redirect: "manual",
      cache: "no-store",
      signal: AbortSignal.timeout(60_000),
    });
  } catch {
    return Response.json({ detail: "서버에 연결하지 못했어요. 잠시 후 다시 시도해 주세요." }, { status: 502 });
  }

  const responseHeaders = new Headers();
  for (const name of FORWARD_RESPONSE_HEADERS) {
    if (name === "set-cookie") {
      for (const cookie of upstream.headers.getSetCookie()) responseHeaders.append(name, cookie);
      continue;
    }
    const value = upstream.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  const body = upstream.status === 204 ? null : await upstream.arrayBuffer();
  return new Response(body, { status: upstream.status, headers: responseHeaders });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const dynamic = "force-dynamic";
