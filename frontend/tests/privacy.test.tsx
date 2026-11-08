import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

async function renderPage() {
  vi.resetModules();
  const { default: PrivacyPage } = await import("@/app/privacy/page");
  render(<PrivacyPage />);
}

describe("privacy notice", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("warns when the controller details are not configured", async () => {
    vi.stubEnv("NEXT_PUBLIC_CONTROLLER_NAME", "");
    vi.stubEnv("NEXT_PUBLIC_PRIVACY_CONTACT_EMAIL", "");
    await renderPage();

    expect(screen.getByRole("alert")).toHaveTextContent("Controller details are not configured");
    expect(screen.getByText(/\[controller not configured\]/)).toBeInTheDocument();
  });

  it("shows the controller, a mailto contact and the retention windows when configured", async () => {
    vi.stubEnv("NEXT_PUBLIC_CONTROLLER_NAME", "Acme Labs SRL");
    vi.stubEnv("NEXT_PUBLIC_PRIVACY_CONTACT_EMAIL", "privacy@acme.test");
    vi.stubEnv("NEXT_PUBLIC_RETENTION_NON_SIGNAL_DAYS", "14");
    await renderPage();

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText(/Acme Labs SRL/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "privacy@acme.test" })).toHaveAttribute(
      "href",
      "mailto:privacy@acme.test",
    );
    expect(screen.getByText(/deleted after 14 days/)).toBeInTheDocument();
    expect(screen.getByText(/deleted after 365 days/)).toBeInTheDocument();
  });

  it("explains how to ask for deletion and what is kept afterwards", async () => {
    await renderPage();
    expect(screen.getByText(/one-way hash/)).toBeInTheDocument();
    expect(screen.getByText(/never posts/)).toBeInTheDocument();
  });
});
