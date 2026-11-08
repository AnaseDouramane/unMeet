import { InboxView } from "@/components/inbox/inbox-view";
import { PageHeader } from "@/components/ui/page-header";

export default function InboxPage() {
  return (
    <>
      <PageHeader
        title="Inbox"
        description="People asking for a tool like yours, or complaining about a competitor, right now."
      />
      <InboxView />
    </>
  );
}
