import { proxyErrorResponse, proxyGet } from "@/lib/proxy";

export async function GET() {
  try {
    return await proxyGet("/chat-sessions");
  } catch (error) {
    return proxyErrorResponse(error);
  }
}
