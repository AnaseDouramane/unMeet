import { TopicManager } from "@/components/topics/topic-manager";
import { PageHeader } from "@/components/ui/page-header";

export default function TopicsPage() {
  return (
    <>
      <PageHeader
        title="Topics"
        description="Save a problem space once; new matching signals are collected and can be pushed to a webhook such as Clay."
      />
      <TopicManager />
    </>
  );
}
