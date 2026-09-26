import { describe, expect, it } from "vitest";

import { ApiError, newIdempotencyKey, retryTransient, unwrap } from "./client";

const response = (status: number) => new Response(null, { status });

describe("unwrap", () => {
  it("returns the data of a successful response", () => {
    expect(unwrap({ data: { ok: true }, response: response(200) })).toEqual({ ok: true });
  });

  it("throws the API's own message with the status", () => {
    const run = () => unwrap({ error: { detail: "크레딧이 모자라요" }, response: response(402) });
    expect(run).toThrow(ApiError);
    expect(run).toThrow("크레딧이 모자라요");
    try {
      run();
    } catch (e) {
      expect((e as ApiError).status).toBe(402);
    }
  });

  it("reads the first message of a validation error list", () => {
    const error = { detail: [{ msg: "이메일 형식이 아니에요", loc: ["body", "email"] }] };
    expect(() => unwrap({ error, response: response(422) })).toThrow("이메일 형식이 아니에요");
  });

  it("falls back to a plain sentence when the body has no detail", () => {
    expect(() => unwrap({ error: "Bad Gateway", response: response(502) })).toThrow("요청을 처리하지 못했어요");
  });
});

describe("newIdempotencyKey", () => {
  it("is prefixed and different every time", () => {
    const a = newIdempotencyKey("brief");
    const b = newIdempotencyKey("brief");
    expect(a).toMatch(/^brief-/);
    expect(a).not.toBe(b);
  });
});

describe("retryTransient", () => {
  it("retries a dropped connection and server failures", () => {
    expect(retryTransient(0, new TypeError("Failed to fetch"))).toBe(true);
    expect(retryTransient(0, new ApiError(500, "x"))).toBe(true);
    expect(retryTransient(0, new ApiError(502, "x"))).toBe(true); // the BFF could not reach the API
  });

  it("never retries an answer about the request itself", () => {
    for (const status of [400, 401, 402, 403, 404, 409, 422, 429]) {
      expect(retryTransient(0, new ApiError(status, "x"))).toBe(false);
    }
    expect(retryTransient(0, new Error("bug in our code"))).toBe(false);
  });

  it("gives up after two retries", () => {
    expect(retryTransient(1, new TypeError("Failed to fetch"))).toBe(true);
    expect(retryTransient(2, new TypeError("Failed to fetch"))).toBe(false);
  });
});
