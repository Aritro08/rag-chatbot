import { proxyErrorResponse, proxyJsonPost } from "@/lib/proxy";

export async function POST(request: Request) {
  try {
    return await proxyJsonPost(request, "/delete-doc");
  } catch (error) {
    return proxyErrorResponse(error);
  }
}
