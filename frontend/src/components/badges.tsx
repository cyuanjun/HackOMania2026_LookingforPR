import { CaseState, RecommendedAction, UrgencyClass } from "@/lib/types";

function badgeClassName(tone: "neutral" | "danger" | "warning" | "success" | "calm"): string {
  if (tone === "danger") {
    return "bg-red-100 text-red-800 ring-red-200";
  }
  if (tone === "warning") {
    return "bg-amber-100 text-amber-800 ring-amber-200";
  }
  if (tone === "success") {
    return "bg-emerald-100 text-emerald-800 ring-emerald-200";
  }
  if (tone === "calm") {
    return "bg-blue-100 text-blue-800 ring-blue-200";
  }
  return "bg-slate-100 text-slate-700 ring-slate-200";
}

function Chip({ label, tone }: { label: string; tone: "neutral" | "danger" | "warning" | "success" | "calm" }) {
  return (
    <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${badgeClassName(tone)}`}>
      {label}
    </span>
  );
}

export function UrgencyChip({ urgency }: { urgency: UrgencyClass | null | undefined }) {
  if (!urgency) {
    return <Chip label="N/A" tone="neutral" />;
  }
  if (urgency === "urgent") {
    return <Chip label="Urgent" tone="danger" />;
  }
  if (urgency === "uncertain") {
    return <Chip label="Uncertain" tone="warning" />;
  }
  return <Chip label="Non-Urgent" tone="success" />;
}

export function ActionChip({ action }: { action: RecommendedAction | null | undefined }) {
  if (!action) {
    return <Chip label="N/A" tone="neutral" />;
  }
  if (action === "ambulance_dispatch") {
    return <Chip label="Ambulance Dispatch" tone="danger" />;
  }
  if (action === "operator_callback") {
    return <Chip label="Operator Callback" tone="calm" />;
  }
  return <Chip label="Community Response" tone="success" />;
}

export function StateChip({ state }: { state: CaseState }) {
  if (state === "pending_ai_assessment") {
    return <Chip label="Pending AI Assessment" tone="warning" />;
  }
  if (state === "ai_assessed") {
    return <Chip label="AI Assessed" tone="calm" />;
  }
  return <Chip label="Operator Processed" tone="success" />;
}

export function ConfidenceChip({ confidence }: { confidence: number | null | undefined }) {
  if (confidence == null) {
    return <Chip label="N/A" tone="neutral" />;
  }
  const label = `${Math.round(confidence * 100)}%`;
  if (confidence >= 0.75) {
    return <Chip label={label} tone="success" />;
  }
  if (confidence >= 0.6) {
    return <Chip label={label} tone="calm" />;
  }
  return <Chip label={label} tone="warning" />;
}

