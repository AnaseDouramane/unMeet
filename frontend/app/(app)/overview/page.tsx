import { OverviewView } from "@/components/overview/overview-view";
import { PageHeader } from "@/components/ui/page-header";

export default function OverviewPage() {
  return (
    <>
      <PageHeader title="Overview" description="What unMeet understood, what it searched, and what it found." />
      <OverviewView />
    </>
  );
}
