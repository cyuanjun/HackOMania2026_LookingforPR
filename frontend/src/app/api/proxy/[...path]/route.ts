import { NextRequest, NextResponse } from "next/server";

const PROXY_TIMEOUT_MS = 30000;

function parseBackendOrigins(): string[] {
  const envRaw = process.env.BACKEND_API_ORIGIN ?? "";
  const envValues = envRaw
    .split(",")
    .map((item) => item.trim().replace(/\/+$/, ""))
    .filter(Boolean);

  const fallbackValues = [
    "http://127.0.0.1:8011",
    "http://127.0.0.1:8000",
    "http://localhost:8011",
    "http://localhost:8000"
  ];

  return Array.from(new Set([...envValues, ...fallbackValues]));
}

const BACKEND_ORIGINS = parseBackendOrigins();

type RouteParams = {
  params: Promise<{
    path?: string[];
  }>;
};

function buildBackendUrl(origin: string, request: NextRequest, pathSegments: string[] | undefined): string {
  const joinedPath = (pathSegments ?? []).join("/");
  const search = request.nextUrl.search || "";
  return `${origin}/api/v1/${joinedPath}${search}`;
}

function isSafeMethod(method: string): boolean {
  return method === "GET" || method === "HEAD";
}

async function proxyRequest(request: NextRequest, pathSegments: string[] | undefined): Promise<NextResponse> {
  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("connection");
  headers.delete("content-length");

  const requestBody =
    request.method === "GET" || request.method === "HEAD" ? undefined : Buffer.from(await request.arrayBuffer());
  const safeMethod = isSafeMethod(request.method);
  let lastError: string | null = null;
  let lastResponse: Response | null = null;

  for (let index = 0; index < BACKEND_ORIGINS.length; index += 1) {
    const origin = BACKEND_ORIGINS[index];
    const backendUrl = buildBackendUrl(origin, request, pathSegments);
    const controller = new AbortController();
    const timeoutHandle = setTimeout(() => controller.abort("proxy timeout"), PROXY_TIMEOUT_MS);

    try {
      const upstream = await fetch(backendUrl, {
        method: request.method,
        headers,
        body: requestBody,
        redirect: "manual",
        signal: controller.signal
      });
      clearTimeout(timeoutHandle);

      lastResponse = upstream;
      const shouldFallback = safeMethod && !upstream.ok && index < BACKEND_ORIGINS.length - 1;
      if (shouldFallback) {
        continue;
      }

      const responseHeaders = new Headers(upstream.headers);
      responseHeaders.delete("transfer-encoding");
      return new NextResponse(upstream.body, {
        status: upstream.status,
        headers: responseHeaders
      });
    } catch (error) {
      clearTimeout(timeoutHandle);
      lastError = error instanceof Error ? error.message : "Unable to reach backend service.";
      if (!safeMethod || index === BACKEND_ORIGINS.length - 1) {
        break;
      }
    }
  }

  if (lastResponse) {
    const text = await lastResponse.text();
    return NextResponse.json(
      {
        detail: text || `Backend returned ${lastResponse.status} with no body.`
      },
      { status: lastResponse.status }
    );
  }

  return NextResponse.json(
    {
      detail: `Proxy error: ${lastError ?? "Unable to reach backend service."}. Tried: ${BACKEND_ORIGINS.join(", ")}`
    },
    { status: 502 }
  );
}

async function readPath(context: RouteParams): Promise<string[] | undefined> {
  const resolved = await context.params;
  return resolved.path;
}

export async function GET(request: NextRequest, context: RouteParams): Promise<NextResponse> {
  return proxyRequest(request, await readPath(context));
}

export async function POST(request: NextRequest, context: RouteParams): Promise<NextResponse> {
  return proxyRequest(request, await readPath(context));
}

export async function PUT(request: NextRequest, context: RouteParams): Promise<NextResponse> {
  return proxyRequest(request, await readPath(context));
}

export async function PATCH(request: NextRequest, context: RouteParams): Promise<NextResponse> {
  return proxyRequest(request, await readPath(context));
}

export async function DELETE(request: NextRequest, context: RouteParams): Promise<NextResponse> {
  return proxyRequest(request, await readPath(context));
}
