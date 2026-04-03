import { describe, expect, it } from "vitest";
import { parseSseStream } from "@/lib/sse";
import type { ChatStreamEvent } from "@/lib/types";

function createStream(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
}

describe("parseSseStream", () => {
  it("parses token and done events across chunk boundaries", async () => {
    const stream = createStream([
      'data: {"type":"start","session_id":"abc","model_name":"gpt-4o-mini"}\n\n',
      'data: {"type":"thinking","key":"node:router","kind":"node","status":"running","title":"Route Query"}\n\n',
      'data: {"type":"token","content":"Hel',
      'lo"}\n\n',
      'data: {"type":"token","content":" world"}\n\n',
      'data: {"type":"done","session_id":"abc","model_name":"gpt-4o-mini"}\n\n',
    ]);

    const events: ChatStreamEvent[] = [];
    for await (const event of parseSseStream(stream)) {
      events.push(event);
    }

    expect(events).toEqual([
      { type: "start", session_id: "abc", model_name: "gpt-4o-mini" },
      { type: "thinking", key: "node:router", kind: "node", status: "running", title: "Route Query" },
      { type: "token", content: "Hello" },
      { type: "token", content: " world" },
      { type: "done", session_id: "abc", model_name: "gpt-4o-mini" },
    ]);
  });

  it("ignores malformed event payloads", async () => {
    const stream = createStream([
      "data: not-json\n\n",
      'data: {"type":"error","message":"bad"}\n\n',
    ]);

    const events: ChatStreamEvent[] = [];
    for await (const event of parseSseStream(stream)) {
      events.push(event);
    }

    expect(events).toEqual([{ type: "error", message: "bad" }]);
  });

  it("supports CRLF event delimiters", async () => {
    const stream = createStream([
      'data: {"type":"ping"}\r\n\r\n',
      'data: {"type":"token","content":"A"}\r\n\r\n',
      'data: {"type":"done","session_id":"s1","model_name":"gpt-4o-mini"}\r\n\r\n',
    ]);

    const events: ChatStreamEvent[] = [];
    for await (const event of parseSseStream(stream)) {
      events.push(event);
    }

    expect(events).toEqual([
      { type: "ping" },
      { type: "token", content: "A" },
      { type: "done", session_id: "s1", model_name: "gpt-4o-mini" },
    ]);
  });
});
