import { proxyErrorResponse, proxySsePost } from "@/lib/proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 300;

export async function POST(request: Request) {
  try {
    return await proxySsePost(request, "/chat/stream");
  } catch (error) {
    return proxyErrorResponse(error);
  }
}
