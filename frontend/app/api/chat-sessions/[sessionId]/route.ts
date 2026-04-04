import { proxyErrorResponse, proxyGet } from "@/lib/proxy";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ sessionId: string }> },
) {
  try {
    const { sessionId } = await params;
    return await proxyGet(`/chat-sessions/${encodeURIComponent(sessionId)}`);
  } catch (error) {
    return proxyErrorResponse(error);
  }
}
