import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ReportsPage from "@/app/(marketing)/reports/page";
import ReportPage from "@/app/(marketing)/reports/[id]/page";
import LandingPage from "@/app/(marketing)/page";
import { DemoForm } from "@/components/marketing/demo-form";
import { PlansTable } from "@/components/marketing/plans-table";
import { api, ApiClientError } from "@/lib/api";
import { FALLBACK_PLANS } from "@/lib/plans";
import type { DemoResult, Report } from "@/lib/types";

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://api.test");
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

const demo: DemoResult = {
  product_summary: "Acme cleans CRM duplicates.",
  competitors: ["Dedupely"],
  topics: ["CRM duplicates"],
  signals: [
    { source: "reddit", title: "Post 1", url: "https://x.test/1", published_at: "2026-11-02T09:30:00Z", quote: "I spend hours deduping", intent: "pain_point", similarity: 0.9 },
    { source: "hackernews", title: "Ask HN: dedupe tool?", url: "https://x.test/2", published_at: "2026-11-01T09:30:00Z", quote: null, intent: null, similarity: 0.7 },
  ],
};

function submit(url = "https://acme.test") {
  fireEvent.change(screen.getByLabelText("Your website"), { target: { value: url } });
  fireEvent.click(screen.getByRole("button", { name: "Show me real conversations" }));
}

describe("live demo", () => {
  it("shows what was understood and the real conversations, quoting when available and never authors", async () => {
    const run = vi.spyOn(api, "runDemo").mockResolvedValue(demo);
    render(<DemoForm />);
    submit("  https://acme.test ");

    expect(await screen.findByText(/Acme cleans CRM duplicates/)).toBeInTheDocument();
    expect(run).toHaveBeenCalledWith("https://acme.test");
    expect(screen.getByText("“I spend hours deduping”")).toBeInTheDocument();
    expect(screen.getByText("Ask HN: dedupe tool?")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Open original" })).toHaveLength(2);
    expect(screen.getByText(/Dedupely/)).toBeInTheDocument();
  });

  it("explains an empty dataset instead of showing nothing", async () => {
    vi.spyOn(api, "runDemo").mockResolvedValue({ ...demo, signals: [] });
    render(<DemoForm />);
    submit();
    expect(await screen.findByText(/no matching conversations in our current dataset/)).toHaveTextContent("CRM duplicates");
  });

  it("is honest when the demo is switched off, and shows other errors as they are", async () => {
    const run = vi.spyOn(api, "runDemo").mockRejectedValueOnce(new ApiClientError("off", 503, "demo_disabled"));
    render(<DemoForm />);
    submit();
    expect(await screen.findByRole("alert")).toHaveTextContent("not available right now");

    run.mockRejectedValueOnce(new ApiClientError("you reached the demo limit for this hour", 429, "rate_limited"));
    submit();
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("demo limit for this hour"));

    run.mockRejectedValueOnce(new Error("network"));
    submit();
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("could not be reached"));
  });
});

describe("pricing", () => {
  it("shows the built-in plans first and the live ones once loaded", async () => {
    let resolve: (plans: typeof FALLBACK_PLANS) => void = () => undefined;
    vi.spyOn(api, "getPlans").mockReturnValue(new Promise((r) => (resolve = r)));
    render(<PlansTable />);
    expect(screen.getByText("€49")).toBeInTheDocument();
    expect(screen.getByText("Free")).toBeInTheDocument();

    resolve([{ ...FALLBACK_PLANS[1], monthly_price_eur: 59 }]);
    expect(await screen.findByText("€59")).toBeInTheDocument();
    expect(screen.queryByText("€49")).not.toBeInTheDocument();
  });

  it("keeps the built-in plans when the API is down", async () => {
    vi.spyOn(api, "getPlans").mockRejectedValue(new Error("down"));
    render(<PlansTable />);
    await waitFor(() => expect(api.getPlans).toHaveBeenCalled());
    expect(screen.getByText("€149")).toBeInTheDocument();
    expect(screen.getByText("Slack and webhooks")).toBeInTheDocument();
  });
});

describe("landing page", () => {
  it("makes its claims in plain words and links to the demo, pricing and reports", () => {
    vi.spyOn(api, "getPlans").mockResolvedValue([]);
    render(<LandingPage />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Find the people asking for a tool like yours");
    expect(screen.getByRole("form", { name: "Live demo" })).toBeInTheDocument();
    expect(screen.getByText("Pricing")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Read the pain reports" })).toHaveAttribute("href", "/reports");
    expect(screen.getByRole("link", { name: "Get started" })).toHaveAttribute("href", "/onboarding");
    // Sources named on the page are the ones that exist.
    expect(screen.getByText(/Hacker News, Reddit, Stack Exchange and GitHub/)).toBeInTheDocument();
    expect(screen.queryByText(/Bluesky|LinkedIn/)).not.toBeInTheDocument();
  });
});

const report: Report = {
  cluster_id: 4,
  title: "Sales teams clean CRM duplicates by hand",
  status: "rising",
  growth_rate: 0.25,
  document_count: 12,
  source_count: 3,
  quotes: [{ source: "reddit", title: "t", url: "https://x.test/1", published_at: "2026-11-02T09:30:00Z", text: "I spend hours deduping" }],
};

describe("public pain reports", () => {
  it("lists reports with their evidence", async () => {
    vi.spyOn(api, "getReports").mockResolvedValue({ items: [report] });
    render(await ReportsPage());

    const link = screen.getByRole("link", { name: /Sales teams clean CRM duplicates/ });
    expect(link).toHaveAttribute("href", "/reports/4");
    expect(screen.getByText(/12 posts · 3 sources/)).toBeInTheDocument();
  });

  it("says so when nothing has enough evidence, and when the API fails", async () => {
    vi.spyOn(api, "getReports").mockResolvedValueOnce({ items: [] });
    const { unmount } = render(await ReportsPage());
    expect(screen.getByText(/No report has enough evidence yet/)).toBeInTheDocument();
    unmount();

    vi.spyOn(api, "getReports").mockRejectedValueOnce(new ApiClientError("The API could not be reached", undefined));
    render(await ReportsPage());
    expect(screen.getByRole("alert")).toHaveTextContent("could not be reached");
  });

  it("shows quotes as written, linked to the source, with a markdown export and no usernames", async () => {
    vi.spyOn(api, "getReport").mockResolvedValue(report);
    render(await ReportPage({ params: Promise.resolve({ id: "4" }) }));

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Sales teams clean CRM duplicates by hand");
    expect(screen.getByText("“I spend hours deduping”")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /reddit, / })).toHaveAttribute("href", "https://x.test/1");
    expect(screen.getByRole("link", { name: "Markdown version" })).toHaveAttribute("href", "http://api.test/api/v1/reports/4.md");
  });

  it("handles a missing report", async () => {
    vi.spyOn(api, "getReport").mockRejectedValue(new ApiClientError("gone", 404, "report_not_found"));
    render(await ReportPage({ params: Promise.resolve({ id: "99" }) }));
    expect(screen.getByRole("alert")).toHaveTextContent("does not exist");
  });
});
