import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({ default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a> }));

import { TopicManager } from "@/components/topics/topic-manager";
import { api, ApiClientError } from "@/lib/api";
import type { Topic } from "@/lib/types";

const topic: Topic = {
  id: 3,
  name: "CRM hygiene",
  description: "duplicate contacts in the CRM",
  intents: ["competitor_complaint"],
  products: ["HubSpot"],
  sources: [],
  min_severity: null,
  max_distance: 0.6,
  has_webhook: true,
  created_at: "2026-11-01T00:00:00Z",
  last_delivered_at: null,
};

describe("TopicManager", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists topics and creates a new one with the API key", async () => {
    const getTopics = vi.spyOn(api, "getTopics").mockResolvedValue({ items: [topic] });
    const createTopic = vi.spyOn(api, "createTopic").mockResolvedValue({ ...topic, id: 4, name: "Outbound" });
    render(<TopicManager />);
    expect(await screen.findByText("CRM hygiene")).toHaveAttribute("href", "/topics/3");

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Outbound" } });
    fireEvent.change(screen.getByLabelText("Products (comma separated)"), { target: { value: "Apollo, , Clay" } });
    fireEvent.change(screen.getByLabelText(/Phrases to search for/), { target: { value: " find leads , alternative to apollo " } });
    fireEvent.click(screen.getByLabelText("Looking for a solution"));
    fireEvent.change(screen.getByLabelText("API key"), { target: { value: "secret" } });
    fireEvent.click(screen.getByRole("button", { name: "Create topic" }));

    await waitFor(() =>
      expect(createTopic).toHaveBeenCalledWith(
        {
          name: "Outbound",
          description: undefined,
          intents: ["solution_search"],
          products: ["Apollo", "Clay"],
          keywords: ["find leads", "alternative to apollo"],
          webhook_url: undefined,
        },
        "secret",
      ),
    );
    expect(getTopics).toHaveBeenCalledTimes(2);
  });

  it("shows API validation errors next to the form", async () => {
    vi.spyOn(api, "getTopics").mockResolvedValue({ items: [] });
    vi.spyOn(api, "createTopic").mockRejectedValue(new ApiClientError("webhook_url must be an absolute https URL", 400));
    render(<TopicManager />);
    await screen.findByText("No topics yet");

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Bad hook" } });
    fireEvent.click(screen.getByRole("button", { name: "Create topic" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("webhook_url must be an absolute https URL");
  });
});
