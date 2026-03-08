"use client";

import { CaseListItem, CaseState } from "@/lib/types";
import { ActionChip, ConfidenceChip, StateChip, UrgencyChip } from "@/components/badges";

interface CasesTableProps {
  title: string;
  cases: CaseListItem[];
  state: CaseState;
  loading: boolean;
  processingCaseId: string | null;
  onRowClick: (caseId: string) => void;
  onProcessAi: (caseId: string) => Promise<void>;
}

function formatDate(input: string): string {
  const date = new Date(input);
  return Number.isNaN(date.getTime()) ? input : date.toLocaleString();
}

export function CasesTable({
  title,
  cases,
  state,
  loading,
  processingCaseId,
  onRowClick,
  onProcessAi
}: CasesTableProps) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-panel shadow-panel">
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
        <h3 className="text-base font-bold text-ink">{title}</h3>
        <span className="text-xs text-slate-500">{cases.length} case(s)</span>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-xs font-bold uppercase tracking-wide text-slate-600">
            <tr>
              <th className="px-3 py-2 text-left">Case ID</th>
              <th className="px-3 py-2 text-left">Resident</th>
              <th className="px-3 py-2 text-left">State</th>
              <th className="px-3 py-2 text-left">Urgency</th>
              <th className="px-3 py-2 text-left">Action</th>
              <th className="px-3 py-2 text-left">Confidence</th>
              <th className="px-3 py-2 text-left">Updated</th>
              <th className="px-3 py-2 text-left">Controls</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {cases.length === 0 ? (
              <tr>
                <td className="px-3 py-4 text-slate-500" colSpan={8}>
                  {loading ? "Loading cases..." : "No cases in this queue."}
                </td>
              </tr>
            ) : (
              cases.map((item) => (
                <tr
                  key={item.case_id}
                  onClick={() => onRowClick(item.case_id)}
                  className="cursor-pointer transition hover:bg-skywash"
                >
                  <td className="px-3 py-3 font-mono text-xs text-slate-700">{item.case_id}</td>
                  <td className="px-3 py-3 text-slate-700">
                    <div className="font-medium">{item.resident_name}</div>
                    <div className="text-xs text-slate-500">
                      {item.profile_id} | {item.block} {item.unit}
                      {item.postal_code ? ` (S${item.postal_code})` : ""}
                    </div>
                  </td>
                  <td className="px-3 py-3">
                    <StateChip state={item.state} />
                  </td>
                  <td className="px-3 py-3">
                    <UrgencyChip urgency={item.urgency_class} />
                  </td>
                  <td className="px-3 py-3">
                    <ActionChip action={item.recommended_action ?? item.operator_action} />
                  </td>
                  <td className="px-3 py-3">
                    <ConfidenceChip confidence={item.overall_confidence} />
                  </td>
                  <td className="px-3 py-3 text-xs text-slate-600">{formatDate(item.updated_at)}</td>
                  <td className="px-3 py-3">
                    {state === "pending_ai_assessment" ? (
                      <button
                        className="rounded-md bg-slate-800 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
                        onClick={async (event) => {
                          event.stopPropagation();
                          await onProcessAi(item.case_id);
                        }}
                        disabled={processingCaseId === item.case_id}
                      >
                        {processingCaseId === item.case_id ? "Processing..." : "Run AI"}
                      </button>
                    ) : (
                      <span className="text-xs text-slate-500">View detail</span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
