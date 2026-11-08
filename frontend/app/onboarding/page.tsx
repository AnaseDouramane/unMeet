import { OnboardingWizard } from "@/components/onboarding/onboarding-wizard";
import { PageHeader } from "@/components/ui/page-header";

export default function OnboardingPage() {
  return (
    <>
      <PageHeader title="Set up from your website" description="Paste your URL: we propose what to monitor, you confirm." />
      <OnboardingWizard />
    </>
  );
}
