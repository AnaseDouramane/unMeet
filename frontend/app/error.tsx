"use client";

import { ErrorState } from "@/components/ui/states";

export default function Error({ reset }: { error: Error; reset: () => void }) {
  return <ErrorState message="Something went wrong while rendering this page." onRetry={reset} />;
}
