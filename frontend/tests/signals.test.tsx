import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SignalCard } from "@/components/signals/signal-card";
import { SignalFeed } from "@/components/signals/signal-feed";
import { api, buildUrl } from "@/lib/api";
import type { Signal } from "@/lib/types";

const signal: Signal = {
  id: 1,
  source: "hackernews",
  title: "Re: Ask HN: CRM hygiene",
  url: "https://news.ycombinator.com/item?id=1",
  author: "dana",
  published_at: "2026-11-02T09:30:00Z",
  intent: "competitor_complaint",
  pain_quote: "HubSpot dedupe misses half our duplicates",
  products_mentioned: ["HubSpot"],
  severity: 2,
  confidence: 0.9,
  similarity: 0.83,
};

describe("signals", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
  });

  it("shows the quote, intent, product, severity and source link", () => {
    render(<SignalCard signal={signal} />);

    expect(screen.getByText("“HubSpot dedupe misses half our duplicates”")).toBeInTheDocument();
    expect(screen.getByText("Competitor complaint")).toBeInTheDocument();
    expect(screen.getByText("HubSpot")).toBeInTheDocument();
    expect(screen.getByText("Severity 2 of 3")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open original" })).toHaveAttribute("href", signal.url);
  });

  it("explains why a signal matches the topic when the model gave a reason", () => {
    render(<SignalCard signal={{ ...signal, relevance_reason: "Cleans duplicate contacts by hand." }} />);

    expect(screen.getByText("Cleans duplicate contacts by hand.")).toBeInTheDocument();
    expect(screen.getByText("Why it matches:")).toBeInTheDocument();
  });

  it("shows no reason line without one", () => {
    render(<SignalCard signal={signal} />);

    expect(screen.queryByText("Why it matches:")).not.toBeInTheDocument();
  });

  it("falls back to the title when there is no grounded quote", () => {
    render(<SignalCard signal={{ ...signal, pain_quote: null }} />);

    expect(screen.getByText("Re: Ask HN: CRM hygiene")).toBeInTheDocument();
  });

  it("sends the selected filters to the API", async () => {
    const getSignals = vi.spyOn(api, "getSignals").mockResolvedValue({ items: [signal], limit: 50, offset: 0 });
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://api.test");
    render(<SignalFeed />);
    await screen.findByText("“HubSpot dedupe misses half our duplicates”");

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "crm duplicates" } });
    fireEvent.change(screen.getByLabelText("Product mentioned"), { target: { value: "HubSpot" } });
    fireEvent.click(screen.getByRole("button", { name: "Looking for a solution" }));
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));

    await waitFor(() =>
      expect(getSignals).toHaveBeenLastCalledWith({
        limit: 50,
        topic: "crm duplicates",
        product: ["HubSpot"],
        intent: ["solution_search"],
        min_severity: undefined,
      }),
    );
  });

  it("repeats array parameters in URLs", () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://api.test/");

    const url = buildUrl("/api/v1/signals", { intent: ["pain_point", "solution_search"], topic: "" });

    expect(url.toString()).toBe("http://api.test/api/v1/signals?intent=pain_point&intent=solution_search");
  });
});
