import { SignalFeed } from "@/components/signals/signal-feed";
import { PageHeader } from "@/components/ui/page-header";

export default function SignalsPage() {
  return (
    <>
      <PageHeader
        title="Signals"
        description="People describing a problem, asking for a tool or complaining about a product — with the exact quote and a link to reply."
      />
      <SignalFeed />
    </>
  );
}
