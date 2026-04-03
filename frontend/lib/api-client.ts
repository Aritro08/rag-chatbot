import type {
  ChatMessage,
  ChatSessionSummary,
  DeleteFileRequest,
  DocumentInfo,
  QueryInput,
  QueryResponse,
} from "@/lib/types";

export class ApiError extends Error {
  status: number;
  payload: unknown;

  constructor(status: number, message: string, payload: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

async function parseError(response: Response): Promise<ApiError> {
  const contentType = response.headers.get("content-type") ?? "";
  let payload: unknown = null;
  let message = `Request failed with status ${response.status}`;

  try {
    if (contentType.includes("application/json")) {
      payload = await response.json();
      const detail =
        typeof payload === "object" && payload !== null && "detail" in payload
          ? String((payload as { detail: string }).detail)
          : null;
      const fallback =
        typeof payload === "object" && payload !== null && "message" in payload
          ? String((payload as { message: string }).message)
          : null;
      message = detail ?? fallback ?? message;
    } else {
      payload = await response.text();
      if (typeof payload === "string" && payload.trim()) {
        message = payload.trim();
      }
    }
  } catch {
    // Keep the default message when body parsing fails.
  }

  return new ApiError(response.status, message, payload);
}

async function request<T>(input: string, init?: RequestInit): Promise<T> {
  const response = await fetch(input, {
    ...init,
    cache: "no-store",
  });

  if (!response.ok) {
    throw await parseError(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return (await response.json()) as T;
  }
  return (await response.text()) as T;
}

export function normalizeError(error: unknown): string {
  if (error instanceof ApiError) {
    return `(${error.status}) ${error.message}`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Unexpected error";
}

export async function listDocuments(): Promise<DocumentInfo[]> {
  return request<DocumentInfo[]>("/api/list-docs");
}

export async function uploadDocument(file: File): Promise<{ message: string; file_id: number }> {
  const form = new FormData();
  form.append("file", file);

  return request<{ message: string; file_id: number }>("/api/upload-doc", {
    method: "POST",
    body: form,
  });
}

export async function deleteDocument(payload: DeleteFileRequest): Promise<{ message: string }> {
  return request<{ message: string }>("/api/delete-doc", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function listChatSessions(): Promise<ChatSessionSummary[]> {
  return request<ChatSessionSummary[]>("/api/chat-sessions");
}

export async function getChatSessionMessages(sessionId: string): Promise<ChatMessage[]> {
  return request<ChatMessage[]>(`/api/chat-sessions/${sessionId}`);
}

export async function sendChatMessage(input: QueryInput): Promise<QueryResponse> {
  return request<QueryResponse>("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export async function streamChat(input: QueryInput): Promise<Response> {
  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(input),
    cache: "no-store",
  });

  if (!response.ok) {
    throw await parseError(response);
  }

  return response;
}
