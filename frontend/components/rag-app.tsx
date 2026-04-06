"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  deleteDocument,
  getChatSessionMessages,
  listChatSessions,
  listDocuments,
  normalizeError,
  streamChat,
  uploadDocument,
} from "@/lib/api-client";
import { parseSseStream } from "@/lib/sse";
import {
  DEFAULT_MODEL_NAME,
  type ModelName,
  type ThinkingKind,
  type ThinkingStatus,
  type ThinkingStreamEvent,
  type UiChatMessage,
  type UiThinkingStep,
} from "@/lib/types";
import { createMessageId, cn } from "@/lib/utils";
import { ChatPanel } from "@/components/chat-panel";
import { DocsPanel } from "@/components/docs-panel";
import { HistoryPanel } from "@/components/history-panel";
import { Button } from "@/components/ui/button";
import { MessageSquareText, X } from "lucide-react";
import { toast } from "sonner";

type MobilePanel = "history" | "docs" | null;

function toUiMessages(messages: Array<{ role: "user" | "assistant"; content: string; thinking_steps?: Array<{ key: string; kind: ThinkingKind; status: ThinkingStatus; title: string; detail?: string }> }>): UiChatMessage[] {
  return messages.map((message) => ({
    ...message,
    id: createMessageId(message.role),
    thinking_steps: message.thinking_steps
      ? message.thinking_steps.map((step) => ({
          id: createMessageId("think"),
          key: step.key,
          kind: step.kind,
          status: step.status,
          title: step.title,
          detail: step.detail,
        }))
      : undefined,
    show_thinking: message.thinking_steps && message.thinking_steps.length > 0 ? true : undefined,
    thinking_expanded: false,
  }));
}

function upsertThinkingStep(previous: UiThinkingStep[], event: ThinkingStreamEvent): UiThinkingStep[] {
  const index = previous.findIndex((step) => step.key === event.key);
  if (index >= 0) {
    const updated = [...previous];
    updated[index] = {
      ...updated[index],
      kind: event.kind,
      status: event.status,
      title: event.title,
      detail: event.detail,
    };
    return updated;
  }

  return [
    ...previous,
    {
      id: createMessageId("think"),
      key: event.key,
      kind: event.kind,
      status: event.status,
      title: event.title,
      detail: event.detail,
    },
  ];
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

export function RagApp() {
  const queryClient = useQueryClient();
  const [messages, setMessages] = useState<UiChatMessage[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [modelName, setModelName] = useState<ModelName>(DEFAULT_MODEL_NAME);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isLoadingSession, setIsLoadingSession] = useState(false);
  const [deletingFileId, setDeletingFileId] = useState<number | null>(null);
  const [mobilePanel, setMobilePanel] = useState<MobilePanel>(null);

  const sessionsQuery = useQuery({
    queryKey: ["chat-sessions"],
    queryFn: listChatSessions,
  });

  const docsQuery = useQuery({
    queryKey: ["documents"],
    queryFn: listDocuments,
  });

  const uploadMutation = useMutation({
    mutationFn: uploadDocument,
    onSuccess: (result) => {
      toast.success(result.message);
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
    onError: (error) => {
      toast.error(`Upload failed: ${normalizeError(error)}`);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteDocument,
    onSuccess: (result) => {
      toast.success(result.message);
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
    onError: (error) => {
      toast.error(`Delete failed: ${normalizeError(error)}`);
    },
  });

  const handleStartNewChat = () => {
    setActiveSessionId(null);
    setMessages([]);
    setMobilePanel(null);
  };

  const handleSessionSelect = async (sessionId: string) => {
    if (sessionId === activeSessionId || isStreaming) {
      return;
    }

    setMobilePanel(null);
    setIsLoadingSession(true);
    try {
      const sessionMessages = await getChatSessionMessages(sessionId);
      setActiveSessionId(sessionId);
      setMessages(toUiMessages(sessionMessages));
    } catch (error) {
      toast.error(`Failed to load session: ${normalizeError(error)}`);
    } finally {
      setIsLoadingSession(false);
    }
  };

  const handleSendPrompt = async (prompt: string) => {
    if (isStreaming || isLoadingSession) {
      return;
    }

    const userMessage: UiChatMessage = {
      id: createMessageId("user"),
      role: "user",
      content: prompt,
    };
    const assistantId = createMessageId("assistant");
    let aggregatedResponse = "";
    let streamDone = false;
    let recoverySessionId: string | null = activeSessionId;
    let thinkingAutoCollapsed = false;
    let lastTokenAt = 0;
    let stalledAfterPartial = false;
    const streamStartTime = Date.now();
    const MAX_STREAM_DURATION = 90_000; // 90 seconds maximum

    setMessages((previous) => [
      ...previous,
      userMessage,
      {
        id: assistantId,
        role: "assistant",
        content: "",
        thinking_steps: [],
        thinking_expanded: true,
        show_thinking: true,
      },
    ]);

    setIsStreaming(true);

    try {
      const response = await streamChat({
        question: prompt,
        model_name: modelName,
        ...(activeSessionId ? { session_id: activeSessionId } : {}),
      });

      if (!response.body) {
        throw new Error("Streaming response body is missing.");
      }

      for await (const event of parseSseStream(response.body)) {
        if (event.type === "start") {
          recoverySessionId = event.session_id;
          setActiveSessionId(event.session_id);
          continue;
        }

        if (event.type === "thinking") {
          setMessages((previous) =>
            previous.map((message) => {
              if (message.id !== assistantId) {
                return message;
              }

              const nextSteps = upsertThinkingStep(message.thinking_steps ?? [], event);
              const shouldShowThinking =
                message.show_thinking === true ||
                event.kind === "tool" ||
                event.key === "node:retriever_selector" ||
                event.key === "node:rag" ||
                event.key === "node:web";

              return {
                ...message,
                thinking_steps: nextSteps,
                show_thinking: shouldShowThinking,
              };
            }),
          );
          continue;
        }

        if (event.type === "ping") {
          // Only consider stalled if we have received at least one token
          // AND no token has arrived in the last 25 seconds
          if (lastTokenAt && Date.now() - lastTokenAt > 25_000) {
            stalledAfterPartial = true;
            // Don't break immediately - continue processing in case
            // done event arrives shortly after
          }

          // Safety check: force exit if stream has been running too long
          if (Date.now() - streamStartTime > MAX_STREAM_DURATION) {
            stalledAfterPartial = true;
            break; // Force exit after maximum duration
          }

          continue;
        }

        if (event.type === "token") {
          lastTokenAt = Date.now();
          aggregatedResponse += event.content;
          setMessages((previous) =>
            previous.map((message) =>
              message.id === assistantId
                ? {
                    ...message,
                    content: aggregatedResponse,
                    thinking_expanded:
                      !thinkingAutoCollapsed && message.show_thinking ? false : message.thinking_expanded,
                  }
                : message,
            ),
          );
          if (!thinkingAutoCollapsed) {
            thinkingAutoCollapsed = true;
          }
          continue;
        }

        if (event.type === "done") {
          streamDone = true;
          stalledAfterPartial = false; // Cancel stall status since we got done
          recoverySessionId = event.session_id;
          setActiveSessionId(event.session_id);
          queryClient.invalidateQueries({ queryKey: ["chat-sessions"] });
          break;
        }

        if (event.type === "error") {
          throw new Error(event.message);
        }
      }

      if (!aggregatedResponse.trim()) {
        setMessages((previous) =>
          previous.map((message) =>
            message.id === assistantId
              ? { ...message, content: "I apologise but I couldn't generate a response this time." }
              : message,
          ),
        );
      }

      if (!streamDone) {
        // Give a short grace period for any in-flight events to arrive
        // before triggering recovery
        if (stalledAfterPartial) {
          await sleep(500);
        }

        // If we have a substantial partial response (more than 50 chars),
        // prioritize showing that rather than triggering recovery
        const hasSubstantialResponse = aggregatedResponse.trim().length > 50;

        try {
          if (!recoverySessionId) {
            const latestSessions = await listChatSessions();
            const ordered = [...latestSessions].sort(
              (left, right) =>
                new Date(right.created_at).getTime() - new Date(left.created_at).getTime(),
            );
            const match = ordered.find(
              (session) => (session.user_query ?? "").trim().toLowerCase() === prompt.trim().toLowerCase(),
            );
            recoverySessionId = (match ?? ordered[0])?.session_id ?? null;
          }

          if (recoverySessionId) {
            let recovered = false;
            // Increase retry attempts and delay for better recovery chances
            for (let attempt = 0; attempt < 8; attempt += 1) {
              const recoveredMessages = await getChatSessionMessages(recoverySessionId);
              if (recoveredMessages.length > 0) {
                const lastMessage = recoveredMessages[recoveredMessages.length - 1];
                // Only use recovered message if it's actually complete
                // or if we don't have a substantial partial response
                if (!hasSubstantialResponse ||
                    (lastMessage.role === "assistant" && lastMessage.content.trim().length > aggregatedResponse.trim().length)) {
                  setMessages(toUiMessages(recoveredMessages));
                  setActiveSessionId(recoverySessionId);
                  queryClient.invalidateQueries({ queryKey: ["chat-sessions"] });
                  recovered = true;
                  if (stalledAfterPartial) {
                    toast.message("Recovered from a stalled stream and synced the final response.");
                  }
                }
                break;
              }
              await sleep(500);
            }

            if (!recovered && !aggregatedResponse.trim()) {
              setMessages((previous) =>
                previous.map((message) =>
                  message.id === assistantId
                    ? { ...message, content: "Response stream disconnected before completion." }
                    : message,
                ),
              );
            }
          }
        } catch {
          // Keep the streamed partial response if sync-back fails.
        }
      }
    } catch (error) {
      toast.error(`Chat request failed: ${normalizeError(error)}`);
      setMessages((previous) =>
        previous.map((message) =>
          message.id === assistantId
            ? {
                ...message,
                content: "I apologise but I couldn't generate a response this time.",
                thinking_steps: [
                  ...(message.thinking_steps ?? []),
                  {
                    id: createMessageId("think"),
                    key: `error:${Date.now()}`,
                    kind: "system",
                    status: "error",
                    title: "Streaming Error",
                    detail: normalizeError(error),
                  },
                ],
                show_thinking: message.show_thinking === true,
                thinking_expanded: message.show_thinking === true ? true : message.thinking_expanded,
              }
            : message,
        ),
      );
    } finally {
      setIsStreaming(false);
    }
  };

  const mobileSidePanel = mobilePanel ? (
    <div className="fixed inset-0 z-50 lg:hidden">
      <button
        type="button"
        className="absolute inset-0 bg-black/50 backdrop-blur-[1px]"
        onClick={() => setMobilePanel(null)}
        aria-label="Close panel"
      />
      <aside
        className={cn(
          "absolute top-0 h-full w-[88%] max-w-sm bg-background p-3 shadow-xl",
          mobilePanel === "history" ? "left-0" : "right-0",
        )}
      >
        <div className="mb-3 flex items-center justify-between">
          <p className="text-sm font-semibold">{mobilePanel === "history" ? "Chat History" : "Documents"}</p>
          <Button variant="ghost" size="icon" onClick={() => setMobilePanel(null)}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        {mobilePanel === "history" ? (
          <HistoryPanel
            sessions={sessionsQuery.data ?? []}
            activeSessionId={activeSessionId}
            isLoading={sessionsQuery.isLoading}
            isBusy={isStreaming || isLoadingSession}
            onNewChat={handleStartNewChat}
            onSelectSession={handleSessionSelect}
          />
        ) : (
          <DocsPanel
            docs={docsQuery.data ?? []}
            isLoading={docsQuery.isLoading}
            isUploading={uploadMutation.isPending}
            deletingFileId={deletingFileId}
            onUploadFile={(file) => uploadMutation.mutate(file)}
            onDeleteFile={(fileId) => {
              setDeletingFileId(fileId);
              deleteMutation.mutate(
                { file_id: fileId },
                {
                  onSettled: () => setDeletingFileId(null),
                },
              );
            }}
          />
        )}
      </aside>
    </div>
  ) : null;

  return (
    <div className="min-h-screen">
      <header className="border-b bg-background/90 backdrop-blur">
        <div className="mx-auto flex max-w-[1500px] items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2">
            <div className="rounded-lg bg-accent p-2 text-accent-foreground">
              <MessageSquareText className="h-4 w-4" />
            </div>
            <h1 className="text-base font-semibold">LangGraph RAG Chat</h1>
          </div>
          <div className="flex items-center gap-2 lg:hidden">
            <Button variant="outline" size="sm" onClick={() => setMobilePanel("history")}>
              History
            </Button>
            <Button variant="outline" size="sm" onClick={() => setMobilePanel("docs")}>
              Docs
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1500px] p-4">
        <section className="grid gap-4 lg:grid-cols-[18rem_minmax(0,1fr)_20rem]">
          <div className="hidden lg:block">
            <HistoryPanel
              sessions={sessionsQuery.data ?? []}
              activeSessionId={activeSessionId}
              isLoading={sessionsQuery.isLoading}
              isBusy={isStreaming || isLoadingSession}
              onNewChat={handleStartNewChat}
              onSelectSession={handleSessionSelect}
            />
          </div>

          <ChatPanel
            messages={messages}
            modelName={modelName}
            isStreaming={isStreaming}
            isLoadingSession={isLoadingSession}
            onToggleMessageThinking={(messageId) => {
              setMessages((previous) =>
                previous.map((message) =>
                  message.id === messageId
                    ? { ...message, thinking_expanded: !message.thinking_expanded }
                    : message,
                ),
              );
            }}
            onModelChange={setModelName}
            onSubmitPrompt={handleSendPrompt}
          />

          <div className="hidden lg:block">
            <DocsPanel
              docs={docsQuery.data ?? []}
              isLoading={docsQuery.isLoading}
              isUploading={uploadMutation.isPending}
              deletingFileId={deletingFileId}
              onUploadFile={(file) => uploadMutation.mutate(file)}
              onDeleteFile={(fileId) => {
                setDeletingFileId(fileId);
                deleteMutation.mutate(
                  { file_id: fileId },
                  {
                    onSettled: () => setDeletingFileId(null),
                  },
                );
              }}
            />
          </div>
        </section>
      </main>

      {mobileSidePanel}
    </div>
  );
}
