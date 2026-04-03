import { proxyErrorResponse, proxyMultipartPost } from "@/lib/proxy";

export async function POST(request: Request) {
  try {
    return await proxyMultipartPost(request, "/upload-doc");
  } catch (error) {
    return proxyErrorResponse(error);
  }
}
