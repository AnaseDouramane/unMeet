import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiClientError } from "@/lib/api";

describe("API client", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("maps API responses and sends query parameters", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://api.test");
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [] }) });
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.getOpportunities(5, "rising")).resolves.toEqual({ items: [] });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.objectContaining({ href: "http://api.test/api/v1/opportunities?limit=5&status=rising" }),
      expect.objectContaining({ cache: "no-store" }),
    );
  });

  it("returns a safe client error for non-2xx API responses", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://api.test");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({ message: "Unavailable", code: "database_unavailable" }) }));

    await expect(api.getSummary()).rejects.toMatchObject<ApiClientError>({
      message: "Unavailable",
      status: 503,
      code: "database_unavailable",
    });
  });
});
