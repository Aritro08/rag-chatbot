import type { ChatSessionSummary } from "@/lib/types";
import { formatRelativeDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { MessageSquarePlus } from "lucide-react";

interface HistoryPanelProps {
  sessions: ChatSessionSummary[];
  activeSessionId: string | null;
  isLoading: boolean;
  isBusy: boolean;
  onNewChat: () => void;
  onSelectSession: (sessionId: string) => void;
}

export function HistoryPanel({
  sessions,
  activeSessionId,
  isLoading,
  isBusy,
  onNewChat,
  onSelectSession,
}: HistoryPanelProps) {
  return (
    <Card className="flex h-[80vh] min-h-[24rem] flex-col">
      <CardHeader className="space-y-3 border-b">
        <CardTitle className="text-base">Chat History</CardTitle>
        <Button onClick={onNewChat} variant="secondary" className="w-full gap-2" disabled={isBusy}>
          <MessageSquarePlus className="h-4 w-4" />
          New Chat
        </Button>
      </CardHeader>
      <CardContent className="min-h-0 flex-1 overflow-y-auto p-2">
        {isLoading ? (
          <div className="space-y-2 p-2">
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
          </div>
        ) : sessions.length ? (
          <ul className="space-y-1">
            {sessions.map((session) => {
              const isActive = session.session_id === activeSessionId;
              const label = session.user_query?.trim() || "Empty session";
              return (
                <li key={session.session_id}>
                  <button
                    type="button"
                    disabled={isBusy || isActive}
                    onClick={() => onSelectSession(session.session_id)}
                    className={[
                      "w-full rounded-lg border px-3 py-2 text-left text-sm transition",
                      isActive
                        ? "border-sky-500/60 bg-sky-500/10"
                        : "border-transparent bg-muted/35 hover:border-border hover:bg-muted/60",
                    ].join(" ")}
                  >
                    <p className="line-clamp-2 font-medium">{label}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{formatRelativeDate(session.created_at)}</p>
                  </button>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="px-2 py-4 text-sm text-muted-foreground">No past chats yet.</p>
        )}
      </CardContent>
    </Card>
  );
}
