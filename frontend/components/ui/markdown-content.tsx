import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";

interface MarkdownContentProps {
  content: string;
  className?: string;
}

export function MarkdownContent({ content, className }: MarkdownContentProps) {
  return (
    <div className={cn("markdown-content", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ className: linkClassName, ...props }) => (
            <a
              className={cn("font-medium text-sky-300 underline underline-offset-4 hover:text-sky-200", linkClassName)}
              target="_blank"
              rel="noopener noreferrer"
              {...props}
            />
          ),
          pre: ({ className: preClassName, ...props }) => (
            <pre
              className={cn(
                "overflow-x-auto rounded-lg border border-border/80 bg-background/60 p-3",
                preClassName,
              )}
              {...props}
            />
          ),
          code: ({ className: codeClassName, children, ...props }) => {
            const blockLike = !!codeClassName || String(children).includes("\n");
            if (!blockLike) {
              return (
                <code
                  className={cn(
                    "rounded-md border border-border/80 bg-background/70 px-1 py-0.5 font-mono text-[0.85em]",
                    codeClassName,
                  )}
                  {...props}
                >
                  {children}
                </code>
              );
            }

            return (
              <code className={cn("block font-mono text-[0.85em]", codeClassName)} {...props}>
                {children}
              </code>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
