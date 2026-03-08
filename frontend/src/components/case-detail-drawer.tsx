"use client";

import { FormEvent, useEffect, useState } from "react";

import { ActionChip, ConfidenceChip, StateChip, UrgencyChip } from "@/components/badges";
import { CaseDetail, RecommendedAction } from "@/lib/types";

interface CaseDetailDrawerProps {
  open: boolean;
  loading: boolean;
  actionLoading: boolean;
  caseDetail: CaseDetail | null;
  onClose: () => void;
  onProcessAi: (caseId: string) => Promise<void>;
  onSubmitDecision: (caseId: string, action: RecommendedAction, notes: string) => Promise<void>;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4">
      <h4 className="text-sm font-bold uppercase tracking-wide text-slate-600">{title}</h4>
      <div className="mt-3 text-sm text-slate-700">{children}</div>
    </section>
  );
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs font-bold uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-sm text-slate-800">{value}</p>
    </div>
  );
}

function formatDate(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function listText(items: string[]): string {
  return items.length ? items.join(", ") : "-";
}

export function CaseDetailDrawer({
  open,
  loading,
  actionLoading,
  caseDetail,
  onClose,
  onProcessAi,
  onSubmitDecision
}: CaseDetailDrawerProps) {
  const [decisionAction, setDecisionAction] = useState<RecommendedAction>("operator_callback");
  const [decisionNotes, setDecisionNotes] = useState("");

  useEffect(() => {
    if (!caseDetail?.triage_result) {
      return;
    }
    setDecisionAction(caseDetail.triage_result.recommended_action);
    setDecisionNotes("");
  }, [caseDetail?.metadata.case_id, caseDetail?.triage_result?.recommended_action]);

  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="flex-1 bg-slate-900/40" onClick={onClose} />
      <aside className="h-full w-full max-w-2xl overflow-y-auto border-l border-slate-200 bg-slate-50 p-5 shadow-2xl">
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h3 className="text-lg font-bold text-ink">Case Details</h3>
            {caseDetail ? (
              <p className="text-sm text-slate-600">
                {caseDetail.metadata.case_id} | {caseDetail.resident_profile.name}
              </p>
            ) : null}
          </div>
          <button
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100"
            onClick={onClose}
          >
            Close
          </button>
        </div>

        {loading || !caseDetail ? (
          <p className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-600">Loading case detail...</p>
        ) : (
          <DrawerBody
            detail={caseDetail}
            actionLoading={actionLoading}
            decisionAction={decisionAction}
            decisionNotes={decisionNotes}
            onDecisionActionChange={setDecisionAction}
            onDecisionNotesChange={setDecisionNotes}
            onProcessAi={onProcessAi}
            onSubmitDecision={onSubmitDecision}
          />
        )}
      </aside>
    </div>
  );
}

interface DrawerBodyProps {
  detail: CaseDetail;
  actionLoading: boolean;
  decisionAction: RecommendedAction;
  decisionNotes: string;
  onDecisionActionChange: (action: RecommendedAction) => void;
  onDecisionNotesChange: (notes: string) => void;
  onProcessAi: (caseId: string) => Promise<void>;
  onSubmitDecision: (caseId: string, action: RecommendedAction, notes: string) => Promise<void>;
}

function DrawerBody({
  detail,
  actionLoading,
  decisionAction,
  decisionNotes,
  onDecisionActionChange,
  onDecisionNotesChange,
  onProcessAi,
  onSubmitDecision
}: DrawerBodyProps) {
  return (
    <div className="space-y-4">
      <Section title="Case Overview">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Case ID" value={detail.metadata.case_id} />
          <Field label="State" value={<StateChip state={detail.metadata.state} />} />
          <Field label="Urgency" value={<UrgencyChip urgency={detail.triage_result?.urgency_class} />} />
          <Field
            label="Action"
            value={<ActionChip action={detail.triage_result?.recommended_action ?? detail.operator_decision?.chosen_action} />}
          />
          <Field label="Confidence" value={<ConfidenceChip confidence={detail.triage_result?.overall_confidence} />} />
          <Field label="Updated" value={formatDate(detail.metadata.updated_at)} />
        </div>
      </Section>

      <Section title="Audio Metadata">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Filename" value={detail.audio_metadata.filename} />
          <Field label="Content Type" value={detail.audio_metadata.content_type} />
          <Field label="Size (bytes)" value={detail.audio_metadata.size_bytes.toString()} />
          <Field label="Uploaded At" value={formatDate(detail.audio_metadata.uploaded_at)} />
          <Field label="Stored Path" value={detail.audio_metadata.stored_path} />
        </div>
      </Section>

      <Section title="Resident Profile">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Profile ID" value={detail.resident_profile.profile_id} />
          <Field label="Name" value={detail.resident_profile.name} />
          <Field label="Age" value={detail.resident_profile.age.toString()} />
          <Field label="Postal Code" value={detail.resident_profile.postal_code || "-"} />
          <Field label="Block" value={detail.resident_profile.block || "-"} />
          <Field label="Unit" value={detail.resident_profile.unit || "-"} />
          <Field label="Preferred Language" value={detail.resident_profile.preferred_language} />
          <Field label="Preferred Dialect" value={detail.resident_profile.preferred_dialect} />
          <Field label="Mobility" value={detail.resident_profile.mobility_status} />
          <Field label="Living Alone" value={detail.resident_profile.living_alone ? "Yes" : "No"} />
          <Field label="Emergency Contact" value={detail.resident_profile.emergency_contact} />
        </div>
      </Section>

      <Section title="Raw Medical History">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Diagnoses" value={listText(detail.raw_medical_history.diagnoses)} />
          <Field label="Allergies" value={listText(detail.raw_medical_history.allergies)} />
          <Field label="Medications" value={listText(detail.raw_medical_history.medications)} />
          <Field label="Last Discharge Date" value={detail.raw_medical_history.last_discharge_date ?? "-"} />
          <Field label="Notes" value={detail.raw_medical_history.notes ?? "-"} />
        </div>
      </Section>

      <Section title="Derived Medical Features">
        {detail.derived_medical_flags ? (
          <div className="grid grid-cols-2 gap-3">
            <Field label="High Fall Risk" value={String(detail.derived_medical_flags.high_fall_risk)} />
            <Field label="Cardio Risk" value={String(detail.derived_medical_flags.cardio_risk)} />
            <Field label="Respiratory Risk" value={String(detail.derived_medical_flags.respiratory_risk)} />
            <Field label="Cognitive Risk" value={String(detail.derived_medical_flags.cognitive_risk)} />
            <Field label="Polypharmacy Risk" value={String(detail.derived_medical_flags.polypharmacy_risk)} />
            <Field label="Evidence" value={listText(detail.derived_medical_flags.evidence)} />
          </div>
        ) : (
          <p className="text-sm text-slate-500">Not generated yet.</p>
        )}
      </Section>

      <Section title="Raw Call History">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Total Calls (30d)" value={detail.raw_call_history.total_calls_last_30d.toString()} />
          <Field label="Urgent Calls (30d)" value={detail.raw_call_history.urgent_calls_last_30d.toString()} />
          <Field label="False Alarms (30d)" value={detail.raw_call_history.false_alarm_count_last_30d.toString()} />
          <Field label="Last Outcome" value={detail.raw_call_history.last_call_outcome ?? "-"} />
          <Field label="Recent Summaries" value={listText(detail.raw_call_history.recent_call_summaries)} />
        </div>
      </Section>

      <Section title="Derived History Features">
        {detail.derived_history_flags ? (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Frequent Caller" value={String(detail.derived_history_flags.frequent_caller)} />
            <Field label="Recent Urgent Pattern" value={String(detail.derived_history_flags.recent_urgent_pattern)} />
            <Field label="Repeated False Alarms" value={String(detail.derived_history_flags.repeated_false_alarms)} />
            <Field label="Escalation Trend" value={String(detail.derived_history_flags.escalation_trend)} />
            <Field label="Evidence" value={listText(detail.derived_history_flags.evidence)} />
          </div>
        ) : (
          <p className="text-sm text-slate-500">Not generated yet.</p>
        )}
      </Section>

      <Section title="Non-Verbal Audio Results">
        <div className="min-h-20 rounded border border-slate-200 bg-slate-100" />
      </Section>

      <Section title="Speech and Language Results">
        {detail.speech_result ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Detected Language" value={detail.speech_result.detected_language} />
              <Field label="Detected Dialect" value={detail.speech_result.detected_dialect} />
              <Field label="Dialect Label" value={detail.speech_result.dialect_label} />
              <Field label="Speech Confidence" value={detail.speech_result.speech_confidence.toFixed(3)} />
              <Field label="Dialect Confidence" value={detail.speech_result.dialect_confidence.toFixed(3)} />
            </div>
            <Field label="Transcript (Original)" value={detail.speech_result.transcript_original} />
            <Field label="Transcript (English)" value={detail.speech_result.transcript_english} />
            {detail.language_routing_result ? (
              <div className="grid grid-cols-2 gap-3">
                <Field label="Routing Hint" value={detail.language_routing_result.routing_hint} />
                <Field label="Fallback Used" value={String(detail.language_routing_result.fallback_used)} />
                <Field label="Routing Confidence" value={detail.language_routing_result.confidence.toFixed(3)} />
                <Field label="Routing Evidence" value={listText(detail.language_routing_result.evidence)} />
              </div>
            ) : null}
          </div>
        ) : (
          <p className="text-sm text-slate-500">Not generated yet.</p>
        )}
      </Section>

      <Section title="Triage Result">
        {detail.triage_result ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Urgency" value={<UrgencyChip urgency={detail.triage_result.urgency_class} />} />
              <Field label="Recommended Action" value={<ActionChip action={detail.triage_result.recommended_action} />} />
              <Field label="Overall Confidence" value={<ConfidenceChip confidence={detail.triage_result.overall_confidence} />} />
              <Field label="Routing Hint" value={detail.triage_result.routing_hint} />
            </div>
            <Field label="Reasoning" value={detail.triage_result.reasoning} />
            <Field label="Summary" value={detail.summary_text ?? "-"} />
          </div>
        ) : (
          <p className="text-sm text-slate-500">AI assessment has not run yet.</p>
        )}
      </Section>

      <Section title="Operator Decision">
        {detail.operator_decision ? (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Operator ID" value={detail.operator_decision.operator_id} />
            <Field label="Chosen Action" value={<ActionChip action={detail.operator_decision.chosen_action} />} />
            <Field label="Overrides AI" value={String(detail.operator_decision.overrides_ai)} />
            <Field label="Processed At" value={formatDate(detail.operator_decision.processed_at)} />
            <Field label="Notes" value={detail.operator_decision.notes ?? "-"} />
          </div>
        ) : detail.metadata.state === "pending_ai_assessment" ? (
          <button
            className="rounded-md bg-slate-800 px-3 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
            onClick={() => onProcessAi(detail.metadata.case_id)}
            disabled={actionLoading}
          >
            {actionLoading ? "Processing..." : "Run AI Assessment"}
          </button>
        ) : detail.metadata.state === "ai_assessed" ? (
          <form
            className="space-y-3"
            onSubmit={async (event: FormEvent<HTMLFormElement>) => {
              event.preventDefault();
              await onSubmitDecision(detail.metadata.case_id, decisionAction, decisionNotes);
            }}
          >
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-slate-700">Chosen Action</span>
              <select
                className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
                value={decisionAction}
                onChange={(event) => onDecisionActionChange(event.target.value as RecommendedAction)}
                disabled={actionLoading}
              >
                <option value="operator_callback">operator_callback</option>
                <option value="community_response">community_response</option>
                <option value="ambulance_dispatch">ambulance_dispatch</option>
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-slate-700">Decision Notes</span>
              <textarea
                className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
                rows={3}
                value={decisionNotes}
                onChange={(event) => onDecisionNotesChange(event.target.value)}
                placeholder="Explain final operator choice..."
                disabled={actionLoading}
              />
            </label>
            <button
              type="submit"
              className="rounded-md bg-accent px-3 py-2 text-sm font-semibold text-white hover:bg-teal-700 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={actionLoading}
            >
              {actionLoading ? "Submitting..." : "Submit Operator Decision"}
            </button>
          </form>
        ) : (
          <p className="text-sm text-slate-500">No further action required.</p>
        )}
      </Section>
    </div>
  );
}
