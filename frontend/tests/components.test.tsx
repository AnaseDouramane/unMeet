import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({ default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a> }));

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(),
}));

import { ClusterFilters } from "@/components/clusters/cluster-filters";
import { KpiGrid } from "@/components/dashboard/kpi-grid";
import { TopOpportunities } from "@/components/dashboard/top-opportunities";
import { SearchForm } from "@/components/search/search-form";
import { api } from "@/lib/api";
import type { DashboardSummary, Opportunity } from "@/lib/types";

const summary: DashboardSummary = {
  total_problems: 12, total_clusters: 4, new_clusters: 2, rising_clusters: 1,
  stable_clusters: 1, falling_clusters: 0, source_count: 2,
  latest_run_id: 1, latest_run_created_at: "2025-01-01T00:00:00Z",
};

const opportunity: Opportunity = {
  cluster_id: 1, label: "Manual reporting", rank: 1, opportunity_score: 0.9,
  document_count: 8, growth_rate: 0.2, status: "rising", source_count: 2,
  average_problem_confidence: 0.8, keywords: ["reporting"],
};

describe("dashboard components", () => {
  beforeEach(() => { push.mockReset(); vi.restoreAllMocks(); });

  it("renders KPI values", () => {
    render(<KpiGrid summary={summary} />);
    expect(screen.getByText("Total problems")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("Sources")).toBeInTheDocument();
  });

  it("renders top opportunities and their status", () => {
    render(<TopOpportunities items={[opportunity]} />);
    expect(screen.getByText("Manual reporting")).toBeInTheDocument();
    expect(screen.getByText("rising")).toBeInTheDocument();
    expect(screen.getByText("#1")).toBeInTheDocument();
  });

  it("renders an empty opportunity state", () => {
    render(<TopOpportunities items={[]} />);
    expect(screen.getByText("No opportunities yet")).toBeInTheDocument();
  });

  it("updates cluster filter query parameters", () => {
    render(<ClusterFilters />);
    fireEvent.change(screen.getByLabelText("Filter by status"), { target: { value: "rising" } });
    expect(push).toHaveBeenCalledWith("/clusters?status=rising");
  });

  it("does not call search for an empty query", () => {
    const search = vi.spyOn(api, "search");
    render(<SearchForm />);
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(search).not.toHaveBeenCalled();
    expect(screen.getByText("Enter a search query before submitting.")).toBeInTheDocument();
  });

  it("renders semantic search results", async () => {
    vi.spyOn(api, "search").mockResolvedValue({ items: [{ id: 1, source: "reddit", title: "Manual work", body: "I copy data every day", url: "https://example.test", author: null, published_at: "2025-01-01T00:00:00Z", problem_confidence: 0.9 }] });
    render(<SearchForm />);
    fireEvent.change(screen.getByLabelText("Search problems"), { target: { value: "copy data" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(screen.getByText("Manual work")).toBeInTheDocument());
    expect(screen.getByText("reddit")).toBeInTheDocument();
  });
});
