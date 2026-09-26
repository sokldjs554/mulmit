// @vitest-environment node
import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GET, POST } from "./route";

// The BFF proxy is the only door from the browser to FastAPI: it decides which headers cross,
// keeps the session cookie first-party and turns an unreachable API into a readable error.

const upstream = vi.fn<typeof fetch>();

beforeEach(() => {
  vi.stubGlobal("fetch", upstream);
  vi.stubEnv("API_ORIGIN", "http://api.internal:8000");
});

afterEach(() => {
  upstream.mockReset();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

const ctx = (...path: string[]) => ({ params: Promise.resolve({ path }) });

function sent(): { url: URL; init: RequestInit & { headers: Headers } } {
  const [url, init] = upstream.mock.calls[0]!;
  return { url: new URL(String(url)), init: init as RequestInit & { headers: Headers } };
}

describe("BFF proxy", () => {
  it("forwards the path and query to the API origin read at request time", async () => {
    upstream.mockResolvedValue(Response.json({ items: [] }));
    const req = new NextRequest("http://localhost:3000/api/opportunities?stage=bid_notice&sort=soon");

    const res = await GET(req, ctx("opportunities"));

    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ items: [] });
    const { url, init } = sent();
    expect(url.origin).toBe("http://api.internal:8000");
    expect(url.pathname).toBe("/api/opportunities");
    expect(url.searchParams.get("stage")).toBe("bid_notice");
    expect(init.method).toBe("GET");
    expect(init.body).toBeUndefined();
  });

  it("encodes each path segment so a crafted id cannot walk to another route", async () => {
    upstream.mockResolvedValue(new Response(null, { status: 404 }));
    const req = new NextRequest("http://localhost:3000/api/opportunities/x");

    await GET(req, ctx("opportunities", "../admin"));

    expect(sent().url.pathname).toBe("/api/opportunities/..%2Fadmin");
  });

  it("passes the session cookie and the idempotency key, and nothing else", async () => {
    upstream.mockResolvedValue(Response.json({ id: 1 }, { status: 201 }));
    const req = new NextRequest("http://localhost:3000/api/opportunities/7/briefs", {
      method: "POST",
      headers: {
        cookie: "session=abc",
        "idempotency-key": "brief-click-1",
        "content-type": "application/json",
        host: "evil.example",
        "x-internal-admin": "1",
      },
      body: JSON.stringify({}),
    });

    const res = await POST(req, ctx("opportunities", "7", "briefs"));

    expect(res.status).toBe(201);
    const { headers } = sent().init;
    expect(headers.get("cookie")).toBe("session=abc");
    expect(headers.get("idempotency-key")).toBe("brief-click-1");
    expect(headers.get("content-type")).toBe("application/json");
    expect(headers.get("host")).toBeNull();
    expect(headers.get("x-internal-admin")).toBeNull();
  });

  it("hands every Set-Cookie back to the browser and drops other upstream headers", async () => {
    const headers = new Headers({ "content-type": "application/json", server: "uvicorn" });
    headers.append("set-cookie", "session=abc; HttpOnly; SameSite=Lax; Path=/");
    headers.append("set-cookie", "csrf=; Max-Age=0; Path=/");
    upstream.mockResolvedValue(new Response("{}", { status: 200, headers }));
    const req = new NextRequest("http://localhost:3000/api/auth/login", { method: "POST", body: "{}" });

    const res = await POST(req, ctx("auth", "login"));

    expect(res.headers.getSetCookie()).toEqual([
      "session=abc; HttpOnly; SameSite=Lax; Path=/",
      "csrf=; Max-Age=0; Path=/",
    ]);
    expect(res.headers.get("server")).toBeNull();
  });

  it("keeps Retry-After so the client can back off", async () => {
    upstream.mockResolvedValue(new Response("{}", { status: 429, headers: { "retry-after": "30" } }));
    const res = await GET(new NextRequest("http://localhost:3000/api/me"), ctx("me"));

    expect(res.status).toBe(429);
    expect(res.headers.get("retry-after")).toBe("30");
  });

  it("answers 502 with a readable message when the API cannot be reached", async () => {
    upstream.mockRejectedValue(new TypeError("fetch failed"));
    const res = await GET(new NextRequest("http://localhost:3000/api/me"), ctx("me"));

    expect(res.status).toBe(502);
    expect(await res.json()).toEqual({ detail: "서버에 연결하지 못했어요. 잠시 후 다시 시도해 주세요." });
  });

  it("returns an empty body for 204", async () => {
    upstream.mockResolvedValue(new Response(null, { status: 204 }));
    const res = await POST(
      new NextRequest("http://localhost:3000/api/auth/logout", { method: "POST" }),
      ctx("auth", "logout"),
    );

    expect(res.status).toBe(204);
    expect(await res.text()).toBe("");
  });
});
