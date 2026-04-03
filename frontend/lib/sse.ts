import type { ChatStreamEvent } from "@/lib/types";

function parseEventChunk(chunk: string): ChatStreamEvent | null {
  const lines = chunk
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  const dataLines = lines
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trim());

  if (!dataLines.length) {
    return null;
  }

  const payloadText = dataLines.join("\n");
  try {
    const payload = JSON.parse(payloadText);
    if (typeof payload !== "object" || payload === null || !("type" in payload)) {
      return null;
    }
    return payload as ChatStreamEvent;
  } catch {
    return null;
  }
}

export async function* parseSseStream(
  stream: ReadableStream<Uint8Array>,
): AsyncGenerator<ChatStreamEvent, void, unknown> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      let boundary = buffer.match(/\r?\n\r?\n/);

      while (boundary?.index !== undefined) {
        const splitAt = boundary.index;
        const boundaryLength = boundary[0].length;
        const rawEvent = buffer.slice(0, splitAt);
        buffer = buffer.slice(splitAt + boundaryLength);
        const parsed = parseEventChunk(rawEvent);
        if (parsed) {
          yield parsed;
        }
        boundary = buffer.match(/\r?\n\r?\n/);
      }
    }

    buffer += decoder.decode();
    if (buffer.trim()) {
      const parsed = parseEventChunk(buffer);
      if (parsed) {
        yield parsed;
      }
    }
  } finally {
    reader.releaseLock();
  }
}
