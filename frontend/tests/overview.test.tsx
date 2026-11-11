import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OverviewView } from "@/components/overview/overview-view";
import { funnelSteps, RunFunnel } from "@/components/overview/run-funnel";
import { api, ApiClientError } from "@/lib/api";
import { saveCredential } from "@/lib/auth";
import type { Overview, OverviewRun } from "@/lib/types";

const run: OverviewRun = {
  source: "hackernews_topics",
  started_at: "2026-11-11T09:00:00Z",
  finished_at: "2026-11-11T09:01:35Z",
  duration_seconds: 95.4,
  status: "ok",
  acquired: 60,
  skipped: 0,
  gated_out: 8,
  llm_requests: 14,
  problems: 5,
  matched: 2,
  errors: 0,
  error: null,
};

const overview: Overview = {
  workspace: { name: "Prototype", plan: "team", website_url: "https://acme.test", product_summary: "Acme cleans CRM data." },
  inbox: { new: 2, relevant: 1, not_relevant: 0, replied: 0 },
  topics: [
    { id: 1, name: "CRM duplicates", description: "dupes", keywords: ["merge duplicate contacts"], products: ["HubSpot"], matched: 2, new: 2 },
    { id: 2, name: "Empty topic", description: null, keywords: [], products: [], matched: 0, new: 0 },
  ],
  runs: [run, { ...run, started_at: "2026-11-10T09:00:00Z", status: "error", error: "429 Too Many Requests", matched: 0 }],
  usage: { calls: 5, total_tokens: 2000, spent_usd: null, llm_budget_usd: 29 },
};

beforeEach(() => vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://api.test"));
afterEach(() => {
  window.sessionStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

describe("run funnel", () => {
  it("derives each step from the run", () => {
    expect(funnelSteps(run).map((step) => [step.label, step.value])).toEqual([
      ["Found", 60],
      ["New", 60],
      ["Read by the AI", 52],
      ["Someone with a need", 5],
      ["Matched a topic", 2],
    ]);
    expect(funnelSteps({ ...run, skipped: 70 })[1].value).toBe(0); // never negative
  });

  it("labels every bar with its number and share, and explains a step on hover", () => {
    render(<RunFunnel run={run} />);
    const matched = screen.getByText("Matched a topic").closest("li") as HTMLElement;
    expect(within(matched).getByText("2")).toBeInTheDocument();
    expect(within(matched).getByText("3%")).toBeInTheDocument();
    fireEvent.mouseEnter(matched);
    expect(screen.getByRole("tooltip")).toHaveTextContent("2 of 60 posts. The need fits one of your topics");
    expect(screen.getByText(/14 AI requests for 52 posts read/)).toBeInTheDocument();
  });
});

describe("overview page", () => {
  it("shows what was understood, the inbox, the last search, topics and usage", async () => {
    vi.spyOn(api, "getOverview").mockResolvedValue(overview);
    render(<OverviewView />);

    expect(await screen.findByText("Acme cleans CRM data.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /New in inbox/ })).toHaveAttribute("href", "/inbox");
    expect(screen.getByRole("figure", { name: "Last run, step by step" })).toBeInTheDocument();
    expect(screen.getByText("merge duplicate contacts")).toBeInTheDocument();
    expect(screen.getByText("HubSpot")).toBeInTheDocument();
    expect(screen.getByText(/No phrases: nothing is searched/)).toBeInTheDocument();
    expect(screen.getByText("Unknown")).toBeInTheDocument(); // spend without prices is not shown as $0
    expect(screen.getByText("Error: 429 Too Many Requests")).toBeInTheDocument();
  });

  it("suggests what to try when the last search matched nothing", async () => {
    vi.spyOn(api, "getOverview").mockResolvedValue({ ...overview, runs: [{ ...run, matched: 0 }] });
    render(<OverviewView />);
    expect(await screen.findByText(/Nothing matched this time/)).toBeInTheDocument();
    expect(screen.getByText(/--days 365/)).toBeInTheDocument();
  });

  it("explains how to start when nothing has run, and shows a failed last run", async () => {
    vi.spyOn(api, "getOverview").mockResolvedValueOnce({ ...overview, runs: [], workspace: { ...overview.workspace, product_summary: null } });
    const { unmount } = render(<OverviewView />);
    expect(await screen.findByText(/No search has run yet/)).toBeInTheDocument();
    expect(screen.getByText(/No product description yet/)).toBeInTheDocument();
    unmount();

    vi.spyOn(api, "getOverview").mockResolvedValueOnce({ ...overview, runs: [{ ...run, status: "error", error: "provider down" }] });
    render(<OverviewView />);
    expect(await screen.findByRole("alert")).toHaveTextContent("provider down");
  });

  it("asks to connect on 401", async () => {
    vi.spyOn(api, "getOverview").mockRejectedValue(new ApiClientError("auth", 401));
    render(<OverviewView />);
    expect(await screen.findByRole("form", { name: "Connect" })).toBeInTheDocument();
  });

  it("asks for the workspace key when none is set, instead of silently showing another workspace", async () => {
    vi.spyOn(api, "getOverview").mockResolvedValue({ ...overview, workspace: { ...overview.workspace, name: "Default" } });
    const { unmount } = render(<OverviewView />);
    const banner = await screen.findByRole("region", { name: "Connect your workspace" });
    expect(banner).toHaveTextContent("empty Default workspace because no key is set");
    expect(within(banner).getByRole("form", { name: "Connect" })).toBeInTheDocument();
    unmount();

    saveCredential("um_abc_secret");
    vi.spyOn(api, "getWorkspace").mockResolvedValue({ id: 1, name: "Prototype", slug: "p", role: "owner", plan: { name: "team" } } as never);
    render(<OverviewView />);
    await screen.findByText("Acme cleans CRM data.");
    expect(screen.queryByRole("region", { name: "Connect your workspace" })).not.toBeInTheDocument();
  });

  it("says when every new post was too far from the topics for the AI to read", async () => {
    vi.spyOn(api, "getOverview").mockResolvedValue({
      ...overview,
      runs: [{ ...run, acquired: 3, gated_out: 3, llm_requests: 0, problems: 0, matched: 0 }],
    });
    render(<OverviewView />);
    expect(await screen.findByText(/All 3 new posts were too far from your topics/)).toBeInTheDocument();
  });
});
