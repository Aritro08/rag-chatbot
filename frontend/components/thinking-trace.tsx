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
    <section className="rounded-xl border border-border/90 bg-card/60">
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
        <div className="max-h-52 space-y-2 overflow-y-auto border-t border-border/90 px-3 py-3">
          {steps.map((step) => (
            <div
              key={step.id}
              className={cn(
                "rounded-lg border px-3 py-2",
                step.status === "running" ? "border-sky-500/40 bg-sky-500/8" : "border-border/80 bg-muted/30",
              )}
            >
              <div className="flex items-start gap-2">
                <StepIcon step={step} />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium leading-snug">{step.title}</p>
                  {step.detail ? <p className="mt-1 text-xs text-muted-foreground">{step.detail}</p> : null}
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}
