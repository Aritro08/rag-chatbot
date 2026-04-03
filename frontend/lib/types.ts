export type ModelName = "gpt-4o-mini" | "gpt-4o";

export interface QueryInput {
  question: string;
  session_id?: string;
  model_name: ModelName;
}

export interface QueryResponse {
  answer: string;
  session_id: string;
  model_name: ModelName;
}

export interface DocumentInfo {
  id: number;
  file_name: string;
  upload_timestamp: string;
}

export interface DeleteFileRequest {
  file_id: number;
}

export interface ChatSessionSummary {
  session_id: string;
  user_query: string | null;
  created_at: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface UiChatMessage extends ChatMessage {
  id: string;
  thinking_steps?: UiThinkingStep[];
  thinking_expanded?: boolean;
  show_thinking?: boolean;
}

export type ThinkingKind = "node" | "tool" | "system";
export type ThinkingStatus = "running" | "done" | "info" | "error";

export interface ThinkingStreamEvent {
  type: "thinking";
  key: string;
  kind: ThinkingKind;
  status: ThinkingStatus;
  title: string;
  detail?: string;
}

export interface UiThinkingStep {
  id: string;
  key: string;
  kind: ThinkingKind;
  status: ThinkingStatus;
  title: string;
  detail?: string;
}

export type ChatStreamEvent =
  | { type: "start"; session_id: string; model_name: ModelName }
  | ThinkingStreamEvent
  | { type: "ping" }
  | { type: "token"; content: string }
  | { type: "done"; session_id: string; model_name: ModelName }
  | { type: "error"; message: string };
