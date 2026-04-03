import { proxyErrorResponse, proxyGet } from "@/lib/proxy";

interface RouteContext {
  params: Promise<{ sessionId: string }>;
}

export async function GET(_request: Request, context: RouteContext) {
  try {
    const { sessionId } = await context.params;
    return await proxyGet(`/chat-sessions/${encodeURIComponent(sessionId)}`);
  } catch (error) {
    return proxyErrorResponse(error);
  }
}
