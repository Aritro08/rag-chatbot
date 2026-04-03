import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, listDocuments, normalizeError } from "@/lib/api-client";

describe("api-client error handling", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("normalizes ApiError with status code", () => {
    const error = new ApiError(500, "boom");
    expect(normalizeError(error)).toBe("(500) boom");
  });

  it("uses backend detail when JSON error payload exists", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        return new Response(JSON.stringify({ detail: "backend exploded" }), {
          status: 500,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );

    await expect(listDocuments()).rejects.toMatchObject({
      name: "ApiError",
      status: 500,
      message: "backend exploded",
    });
  });
});
