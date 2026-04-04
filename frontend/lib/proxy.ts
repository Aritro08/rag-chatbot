import { NextResponse } from "next/server";

const DEFAULT_FASTAPI_BASE_URL = "http://localhost:8000";

function getFastApiBaseUrl(): string {
  const fromEnv = process.env.FASTAPI_BASE_URL?.trim();
  const base = fromEnv && fromEnv.length ? fromEnv : DEFAULT_FASTAPI_BASE_URL;
  return base.endsWith("/") ? base.slice(0, -1) : base;
}

function buildUpstreamUrl(path: string): string {
  const sanitizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${getFastApiBaseUrl()}${sanitizedPath}`;
}

function copyRelevantHeaders(source: Headers): Headers {
  const headers = new Headers();
  const contentType = source.get("content-type");
  const cacheControl = source.get("cache-control");
  const connection = source.get("connection");
  const xAccelBuffering = source.get("x-accel-buffering");

  if (contentType) headers.set("content-type", contentType);
  if (cacheControl) headers.set("cache-control", cacheControl);
  if (connection) headers.set("connection", connection);
  if (xAccelBuffering) headers.set("x-accel-buffering", xAccelBuffering);

  return headers;
}

export function proxyErrorResponse(error: unknown): NextResponse {
  const message = error instanceof Error ? error.message : "Unknown proxy error";
  return NextResponse.json({ detail: `Proxy error: ${message}` }, { status: 500 });
}

export async function proxyGet(path: string): Promise<NextResponse> {
  const upstream = await fetch(buildUpstreamUrl(path), {
    method: "GET",
    cache: "no-store",
  });

  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: copyRelevantHeaders(upstream.headers),
  });
}

export async function proxyJsonPost(request: Request, path: string): Promise<NextResponse> {
  const payload = await request.json();
  const upstream = await fetch(buildUpstreamUrl(path), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(payload),
    cache: "no-store",
  });

  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: copyRelevantHeaders(upstream.headers),
  });
}

export async function proxyMultipartPost(request: Request, path: string): Promise<NextResponse> {
  const formData = await request.formData();
  const upstream = await fetch(buildUpstreamUrl(path), {
    method: "POST",
    body: formData,
    cache: "no-store",
  });

  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: copyRelevantHeaders(upstream.headers),
  });
}

export async function proxySsePost(request: Request, path: string): Promise<NextResponse> {
  const payload = await request.json();
  const upstream = await fetch(buildUpstreamUrl(path), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(payload),
    cache: "no-store",
  });

  if (!upstream.ok) {
    const text = await upstream.text();
    return NextResponse.json({ detail: text || "Upstream streaming request failed" }, { status: upstream.status });
  }

  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
