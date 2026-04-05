import type { UiThinkingStep } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  LoaderCircle,
  Sparkles,
  Wrench,
  Workflow,
} from "lucide-react";

interface ThinkingTraceProps {
  steps: UiThinkingStep[];
  expanded: boolean;
  onToggle: () => void;
}

function StepIcon({ step }: { step: UiThinkingStep }) {
  if (step.status === "running") {
    return <LoaderCircle className="h-4 w-4 animate-spin text-sky-300" />;
  }
  if (step.status === "error") {
    return <AlertTriangle className="h-4 w-4 text-rose-300" />;
  }
  if (step.kind === "tool") {
    return <Wrench className="h-4 w-4 text-amber-300" />;
  }
  if (step.kind === "node") {
    return <Workflow className="h-4 w-4 text-cyan-300" />;
  }
  return <CheckCircle2 className="h-4 w-4 text-emerald-300" />;
}

export function ThinkingTrace({ steps, expanded, onToggle }: ThinkingTraceProps) {
  if (!steps.length) {
    return null;
  }

  const runningCount = steps.filter((step) => step.status === "running").length;

  return (
    <section className="rounded-lg bg-muted/30">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between px-3 py-2 text-left"
      >
        <span className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-sky-300" />
          <span className="text-sm font-medium">Thinking Process</span>
          <span className="text-xs text-muted-foreground">
            {steps.length} steps{runningCount ? ` • ${runningCount} running` : ""}
          </span>
        </span>
        {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
      </button>

      {expanded ? (
        <div className="max-h-52 overflow-y-auto border-t border-border/50 py-2">
          {steps.map((step, index) => {
            // Filter out technical details from the detail field
            const isTechnicalDetail = step.detail && (
              step.detail.startsWith("Input:") ||
              step.detail.startsWith("Output:") ||
              step.detail.startsWith("Route selected:") ||
              step.detail.startsWith("Web results ready:")
            );
            const showDetail = step.detail && !isTechnicalDetail;

            return (
              <div
                key={step.id}
                className={cn(
                  "flex items-start gap-2 px-3 py-1.5",
                  step.status === "running" ? "bg-sky-500/5" : "",
                  index !== steps.length - 1 && "border-b border-border/30"
                )}
              >
                <StepIcon step={step} />
                <div className="min-w-0 flex-1">
                  <p className="text-sm leading-snug">{step.title}</p>
                  {showDetail ? (
                    <p className="mt-0.5 text-xs text-muted-foreground">{step.detail}</p>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
