import { useEffect, useRef, useState, type FormEvent } from "react";
import { MODEL_OPTIONS, type ModelName, type UiChatMessage } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { MarkdownContent } from "@/components/ui/markdown-content";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { ThinkingTrace } from "@/components/thinking-trace";
import { SendHorizontal } from "lucide-react";

interface ChatPanelProps {
  messages: UiChatMessage[];
  modelName: ModelName;
  isStreaming: boolean;
  isLoadingSession: boolean;
  onToggleMessageThinking: (messageId: string) => void;
  onModelChange: (modelName: ModelName) => void;
  onSubmitPrompt: (prompt: string) => Promise<void>;
}

export function ChatPanel({
  messages,
  modelName,
  isStreaming,
  isLoadingSession,
  onToggleMessageThinking,
  onModelChange,
  onSubmitPrompt,
}: ChatPanelProps) {
  const [prompt, setPrompt] = useState("");
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const value = prompt.trim();
    if (!value || isStreaming || isLoadingSession) {
      return;
    }
    setPrompt("");
    await onSubmitPrompt(value);
  };

  return (
    <Card className="flex h-[80vh] min-h-[24rem] flex-col border-0 bg-card/50 shadow-md rounded-lg">
      <CardContent className="flex h-full min-h-0 flex-1 flex-col gap-4 p-4">
        <div className="min-h-0 flex-1 overflow-y-auto rounded-lg bg-muted/20 p-3">
          {isLoadingSession ? (
            <div className="space-y-3">
              <Skeleton className="h-14 w-2/3" />
              <Skeleton className="ml-auto h-20 w-4/5" />
              <Skeleton className="h-16 w-3/4" />
            </div>
          ) : messages.length ? (
            <div className="space-y-3">
              {messages.map((message) => {
                const isUser = message.role === "user";
                return (
                  <div
                    key={message.id}
                    className={[
                      "rounded-2xl px-4 py-3 text-sm leading-relaxed animate-fade-in",
                      isUser
                        ? "ml-auto w-fit max-w-[90%] bg-primary/90 text-primary-foreground"
                        : "max-w-[90%] bg-muted/40 text-foreground",
                    ].join(" ")}
                  >
                    {isUser ? (
                      <p className="whitespace-pre-wrap">{message.content}</p>
                    ) : (
                      <div className="space-y-3">
                        {message.show_thinking && (message.thinking_steps?.length ?? 0) > 0 ? (
                          <ThinkingTrace
                            steps={message.thinking_steps ?? []}
                            expanded={message.thinking_expanded ?? false}
                            onToggle={() => onToggleMessageThinking(message.id)}
                          />
                        ) : null}
                        {message.content ? (
                          <MarkdownContent content={message.content} />
                        ) : isStreaming ? (
                          <p className="text-xs text-muted-foreground">Generating answer...</p>
                        ) : null}
                      </div>
                    )}
                  </div>
                );
              })}
              <div ref={endRef} />
            </div>
          ) : (
            <div className="flex h-full items-center justify-center text-center text-sm text-muted-foreground">
              Ask a question to start a new chat session.
            </div>
          )}
        </div>

        <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-2 md:grid-cols-[1fr_11rem_auto]">
          <Input
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="Ask a question..."
            disabled={isStreaming || isLoadingSession}
            autoComplete="off"
            className="h-12 rounded-xl"
          />
          <Select
            value={modelName}
            onChange={(event) => onModelChange(event.target.value as ModelName)}
            disabled={isStreaming || isLoadingSession}
            className="h-12 rounded-xl"
          >
            {MODEL_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
          <Button
            type="submit"
            disabled={!prompt.trim() || isStreaming || isLoadingSession}
            className="h-12 rounded-xl gap-2"
          >
            <SendHorizontal className="h-4 w-4" />
            {isStreaming ? "Sending..." : "Send"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
