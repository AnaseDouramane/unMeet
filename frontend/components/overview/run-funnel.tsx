"use client";

import { useState } from "react";

import type { OverviewRun } from "@/lib/types";

interface Step {
  label: string;
  value: number;
  help: string;
}

export function funnelSteps(run: OverviewRun): Step[] {
  const fresh = Math.max(run.acquired - run.skipped, 0);
  const judged = Math.max(fresh - run.gated_out, 0);
  return [
    { label: "Found", value: run.acquired, help: "Posts the search returned." },
    { label: "New", value: fresh, help: "Not seen in an earlier run." },
    { label: "Read by the AI", value: judged, help: "Close enough to a topic to be worth an AI check; the rest were dropped for free." },
    { label: "Someone with a need", value: run.problems, help: "The AI found a real problem or request in the post." },
    { label: "Matched a topic", value: run.matched, help: "The need fits one of your topics: these are in your inbox." },
  ];
}

/** One run, step by step: how many posts survived each stage. Single series, so no legend. */
export function RunFunnel({ run }: { run: OverviewRun }) {
  const steps = funnelSteps(run);
  const top = Math.max(steps[0].value, 1);
  const [hovered, setHovered] = useState<number | null>(null);

  return (
    <figure aria-label="Last run, step by step" className="m-0">
      <ol className="space-y-2">
        {steps.map((step, index) => {
          const share = step.value / top;
          return (
            <li
              key={step.label}
              className="relative grid grid-cols-[6.5rem_1fr_4rem] items-center gap-2 text-sm sm:grid-cols-[10rem_1fr_4.5rem] sm:gap-3"
              onMouseEnter={() => setHovered(index)}
              onMouseLeave={() => setHovered(null)}
              onFocus={() => setHovered(index)}
              onBlur={() => setHovered(null)}
              tabIndex={0}
            >
              <span className="text-slate-700">{step.label}</span>
              <span className="h-5 rounded bg-slate-100" aria-hidden="true">
                <span
                  className="block h-5 rounded-r bg-indigo-600"
                  style={{ width: `${Math.max(share * 100, step.value > 0 ? 1.5 : 0)}%` }}
                />
              </span>
              <span className="text-right font-semibold tabular-nums text-slate-900">
                {step.value}
                <span className="ml-1 text-xs font-normal text-slate-500">{index === 0 ? "" : `${Math.round(share * 100)}%`}</span>
              </span>
              {hovered === index && (
                <span role="tooltip" className="absolute bottom-full left-0 z-10 mb-1 max-w-xs rounded bg-slate-900 px-2 py-1 text-xs text-white shadow sm:left-40">
                  {step.value} of {steps[0].value} posts. {step.help}
                </span>
              )}
            </li>
          );
        })}
      </ol>
      <figcaption className="mt-3 text-xs text-slate-500">
        {run.llm_requests} AI request{run.llm_requests === 1 ? "" : "s"} for {steps[2].value} posts read
        {run.errors > 0 ? ` · ${run.errors} could not be read by the AI` : ""}. Percentages are of the posts found.
      </figcaption>
    </figure>
  );
}
