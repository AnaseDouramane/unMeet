import { PageHeader } from "@/components/ui/page-header";
import { SettingsView } from "@/components/settings/settings-view";

export default function SettingsPage() {
  return (
    <>
      <PageHeader title="Settings" description="Your plan, team, API keys and where digests are sent." />
      <SettingsView />
    </>
  );
}
