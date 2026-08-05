import { afterEach, describe, expect, it, vi } from "vitest";

import { API_BASE_URL, apiClient, buildApiUrl } from "./client";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("configured API base URL", () => {
  it("uses the development/test fallback outside production builds", () => {
    expect(API_BASE_URL).toBe("/api");
  });

  it("joins endpoint paths without requiring callers to know the base", () => {
    expect(buildApiUrl("/auth/session")).toBe("/api/auth/session");
    expect(buildApiUrl("auth/session")).toBe("/api/auth/session");
  });

  it("routes blob downloads through the same configured transport", async () => {
    const expectedBlob = new Blob(["orders"], { type: "text/csv" });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      blob: vi.fn().mockResolvedValue(expectedBlob),
    } as unknown as Response);

    const result = await apiClient.getBlob("/admin/orders/export.csv?status=pending");

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/admin/orders/export.csv?status=pending",
      expect.objectContaining({ method: "GET", credentials: "include" }),
    );
    expect(result).toBe(expectedBlob);
  });
});
