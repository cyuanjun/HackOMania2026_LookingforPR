import {
  CaseDetail,
  CaseListItem,
  CaseState,
  OperatorDecisionPayload,
  ResidentContext,
  ResidentProfile
} from "@/lib/types";

const REQUEST_TIMEOUT_MS = 30000;

let preferredBase: string | null = null;
const DEFAULT_DIRECT_API_BASE = "http://127.0.0.1:8011/api/v1";

function normalizeBase(base: string): string {
  return base.replace(/\/+$/, "");
}

function buildBaseCandidates(): string[] {
  const fromEnv = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  const candidates = new Set<string>();

  if (fromEnv) {
    const normalized = normalizeBase(fromEnv);
    candidates.add(normalized);
    if (normalized.startsWith("http") && !normalized.endsWith("/api/v1")) {
      candidates.add(`${normalized}/api/v1`);
    }
  }

  candidates.add("/api/proxy");

  return Array.from(candidates);
}

const API_BASE_CANDIDATES = buildBaseCandidates();

function resolveDirectApiBase(): string {
  const fromEnv = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (fromEnv) {
    const normalized = normalizeBase(fromEnv);
    if (normalized.startsWith("http") && !normalized.endsWith("/api/v1")) {
      return `${normalized}/api/v1`;
    }
    return normalized;
  }
  return DEFAULT_DIRECT_API_BASE;
}

const DIRECT_API_BASE = resolveDirectApiBase();

function buildUrl(base: string, path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${base}${normalizedPath}`;
}

function orderedBases(): string[] {
  if (!preferredBase) {
    return API_BASE_CANDIDATES;
  }
  return [preferredBase, ...API_BASE_CANDIDATES.filter((base) => base !== preferredBase)];
}

function isSafeMethod(method?: string): boolean {
  const resolved = (method ?? "GET").toUpperCase();
  return resolved === "GET" || resolved === "HEAD";
}

function shouldFallbackOnStatus(status: number, safeMethod: boolean): boolean {
  if (!safeMethod) {
    return false;
  }
  return status === 404 || status >= 500;
}

function describeNetworkError(error: unknown): string {
  if (typeof error === "string") {
    const normalized = error.toLowerCase();
    if (normalized.includes("timeout") || normalized.includes("aborted")) {
      return "Request timed out while contacting backend. Ensure backend is running on port 8000.";
    }
    return "Unable to reach backend service. Ensure backend is running and reachable.";
  }
  if (error instanceof DOMException && error.name === "AbortError") {
    return "Request timed out while contacting backend. Ensure backend is running on port 8000.";
  }
  if (error instanceof Error) {
    const normalized = error.message.toLowerCase();
    if (normalized.includes("aborted")) {
      return "Request timed out while contacting backend. Ensure backend is running on port 8000.";
    }
    if (error.message.toLowerCase().includes("fetch")) {
      return "Unable to reach backend service. Ensure backend is running and reachable.";
    }
    return error.message;
  }
  return "Unable to reach backend service. Ensure backend is running and reachable.";
}

async function fetchWithTimeout(url: string, init?: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timeoutHandle = setTimeout(() => controller.abort("request timeout"), REQUEST_TIMEOUT_MS);
  try {
    return await fetch(url, {
      ...init,
      signal: controller.signal,
      cache: "no-store"
    });
  } finally {
    clearTimeout(timeoutHandle);
  }
}

async function readError(response: Response): Promise<string> {
  try {
    const json = (await response.json()) as { detail?: string; error?: string };
    return json.detail || json.error || `Request failed with status ${response.status}`;
  } catch {
    const text = await response.text();
    return text || `Request failed with status ${response.status}`;
  }
}

async function request(path: string, init?: RequestInit): Promise<Response> {
  const safeMethod = isSafeMethod(init?.method);
  const bases = safeMethod ? orderedBases() : [DIRECT_API_BASE];
  let lastNetworkError: string | null = null;

  for (let index = 0; index < bases.length; index += 1) {
    const base = bases[index];
    const url = buildUrl(base, path);

    try {
      const response = await fetchWithTimeout(url, init);
      if (response.ok) {
        preferredBase = base;
        return response;
      }

      if (shouldFallbackOnStatus(response.status, safeMethod) && index < bases.length - 1) {
        continue;
      }

      return response;
    } catch (error) {
      lastNetworkError = describeNetworkError(error);
      if (!safeMethod || index === bases.length - 1) {
        throw new Error(lastNetworkError);
      }
    }
  }

  throw new Error(lastNetworkError ?? "Unable to reach backend.");
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await request(path, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.headers ?? {})
    }
  });

  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return (await response.json()) as T;
}

export function listResidents(): Promise<ResidentProfile[]> {
  return requestJson<ResidentProfile[]>("/residents");
}

export function getResidentContext(profileId: string): Promise<ResidentContext> {
  return requestJson<ResidentContext>(`/residents/${encodeURIComponent(profileId)}/context`);
}

export function listCasesByState(state: CaseState): Promise<CaseListItem[]> {
  return requestJson<CaseListItem[]>(`/cases?state=${state}`);
}

export function getCaseDetail(caseId: string): Promise<CaseDetail> {
  return requestJson<CaseDetail>(`/cases/${caseId}`);
}

export function getCaseAudioUrl(caseId: string): string {
  return `/api/proxy/cases/${encodeURIComponent(caseId)}/audio`;
}

export async function createIntakeCase(profileId: string, audioFile: File): Promise<CaseDetail> {
  const formData = new FormData();
  formData.set("profile_id", profileId);
  formData.set("audio_file", audioFile);

  const response = await request("/cases/intake", {
    method: "POST",
    body: formData
  });

  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return (await response.json()) as CaseDetail;
}

export function processAiCase(caseId: string): Promise<CaseDetail> {
  return requestJson<CaseDetail>(`/cases/${caseId}/process-ai`, {
    method: "POST"
  });
}

export function submitOperatorDecision(caseId: string, payload: OperatorDecisionPayload): Promise<CaseDetail> {
  return requestJson<CaseDetail>(`/cases/${caseId}/operator-decision`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });
}

export async function deleteCase(caseId: string): Promise<void> {
  const response = await request(`/cases/${caseId}`, {
    method: "DELETE"
  });

  if (!response.ok) {
    throw new Error(await readError(response));
  }
}
