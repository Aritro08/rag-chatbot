import { proxyErrorResponse, proxyGet } from "@/lib/proxy";

export async function GET() {
  try {
    return await proxyGet("/list-docs");
  } catch (error) {
    return proxyErrorResponse(error);
  }
}
