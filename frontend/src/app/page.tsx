"use client";

import { ChangeEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  createIntakeCase,
  deleteCase,
  getCaseDetail,
  getCaseAudioUrl,
  getResidentContext,
  listCasesByState,
  listResidents,
  processAiCase,
  submitOperatorDecision
} from "@/lib/api";
import {
  CaseDetail,
  CaseListItem,
  CaseState,
  RecommendedAction,
  ResidentContext,
  ResidentProfile,
  UrgencyClass
} from "@/lib/types";

type DetailTab = "overview" | "raw";
const CASE_QUEUE_ORDER: CaseState[] = ["ai_assessed", "pending_ai_assessment", "operator_processed"];

const OPERATOR_ID = "operator-console";

function stateLabel(state: CaseState): string {
  if (state === "pending_ai_assessment") {
    return "Pending AI Assessment";
  }
  if (state === "ai_assessed") {
    return "Pending Operator";
  }
  return "Operator Processed";
}

function urgencyTone(urgency: UrgencyClass | null | undefined): string {
  if (urgency === "urgent") {
    return "text-red-400";
  }
  if (urgency === "uncertain") {
    return "text-amber-300";
  }
  if (urgency === "non-urgent") {
    return "text-emerald-300";
  }
  return "text-slate-300";
}

function urgencyBar(urgency: UrgencyClass | null | undefined): string {
  if (urgency === "urgent") {
    return "bg-red-500";
  }
  if (urgency === "uncertain") {
    return "bg-amber-400";
  }
  if (urgency === "non-urgent") {
    return "bg-emerald-500";
  }
  return "bg-slate-500";
}

function featureTone(isElevated: boolean): string {
  return isElevated ? "text-amber-300" : "text-emerald-300";
}

function formatTime(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function formatAudioTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) {
    return "00:00";
  }
  const totalSeconds = Math.floor(seconds);
  const mins = Math.floor(totalSeconds / 60)
    .toString()
    .padStart(2, "0");
  const secs = (totalSeconds % 60).toString().padStart(2, "0");
  return `${mins}:${secs}`;
}

function confidenceScore(confidence: number | null | undefined): number {
  if (confidence == null) {
    return 0;
  }
  return Math.max(0, Math.min(100, Math.round(confidence * 100)));
}

function llmRiskScore(stageEvidence: Record<string, unknown> | null | undefined): number | null {
  if (!stageEvidence) {
    return null;
  }

  const direct = stageEvidence.llm_overall_risk_score;
  if (typeof direct === "number" && Number.isFinite(direct)) {
    return Math.max(0, Math.min(100, Math.round(direct)));
  }

  const nested = stageEvidence.llm_assessment;
  if (nested && typeof nested === "object") {
    const score = (nested as Record<string, unknown>).overall_risk_score_0_to_100;
    if (typeof score === "number" && Number.isFinite(score)) {
      return Math.max(0, Math.min(100, Math.round(score)));
    }
  }

  return null;
}

function weightedRiskScore(stageEvidence: Record<string, unknown> | null | undefined): number | null {
  if (!stageEvidence) {
    return null;
  }

  const scoreCandidates = [stageEvidence.final_risk_score, stageEvidence.risk_score];
  for (const candidate of scoreCandidates) {
    if (typeof candidate !== "number" || !Number.isFinite(candidate)) {
      continue;
    }
    if (candidate <= 1.0) {
      return Math.max(0, Math.min(100, Math.round(candidate * 100)));
    }
    return Math.max(0, Math.min(100, Math.round(candidate)));
  }

  return null;
}

function compactActionLabel(action: RecommendedAction | null | undefined): string {
  if (!action) {
    return "No Action";
  }
  if (action === "ambulance_dispatch") {
    return "Ambulance Dispatch";
  }
  if (action === "community_response") {
    return "Community Response";
  }
  return "Operator Callback";
}

function llmRecommendationTail(reasoning: string | null | undefined): string {
  if (!reasoning) {
    return "";
  }
  const marker = "llm risk score";
  const lowered = reasoning.toLowerCase();
  const markerIndex = lowered.indexOf(marker);
  if (markerIndex >= 0) {
    return reasoning.slice(markerIndex).replace(/^[\s;,.:-]+/, "").trim();
  }
  return reasoning.trim();
}

function toPointForm(summary: string | null | undefined): string[] {
  if (!summary) {
    return ["No AI summary generated yet."];
  }
  const lineSplit = summary
    .split(/\r?\n+/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line) => line.replace(/^[-*]\s+/, "").trim());
  if (lineSplit.length > 1) {
    return lineSplit;
  }
  return summary
    .split(/[\.;|]\s+/)
    .map((line) => line.trim().replace(/^[-*]\s+/, ""))
    .filter((line) => line.length > 0);
}

function hasMixedEnglishChinese(text: string): boolean {
  const hasLatin = /[A-Za-z]/.test(text);
  const hasCjk = /[\u4E00-\u9FFF]/.test(text);
  return hasLatin && hasCjk;
}

export default function DashboardPage() {
  const [residents, setResidents] = useState<ResidentProfile[]>([]);
  const [casesByState, setCasesByState] = useState<Record<CaseState, CaseListItem[]>>({
    pending_ai_assessment: [],
    ai_assessed: [],
    operator_processed: []
  });

  const [selectedResidentId, setSelectedResidentId] = useState<string>("");
  const [selectedResidentContext, setSelectedResidentContext] = useState<ResidentContext | null>(null);
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const [selectedCase, setSelectedCase] = useState<CaseDetail | null>(null);
  const [selectedAudioFile, setSelectedAudioFile] = useState<File | null>(null);
  const [activeTab, setActiveTab] = useState<DetailTab>("overview");

  const [loadingResidents, setLoadingResidents] = useState<boolean>(true);
  const [loadingCases, setLoadingCases] = useState<boolean>(true);
  const [loadingCaseDetail, setLoadingCaseDetail] = useState<boolean>(false);
  const [creatingIntake, setCreatingIntake] = useState<boolean>(false);
  const [processingCase, setProcessingCase] = useState<boolean>(false);
  const [audioPlayError, setAudioPlayError] = useState<string>("");
  const [isAudioPlaying, setIsAudioPlaying] = useState<boolean>(false);
  const [audioCurrentTime, setAudioCurrentTime] = useState<number>(0);
  const [audioDuration, setAudioDuration] = useState<number>(0);
  const [residentError, setResidentError] = useState<string>("");
  const [residentContextError, setResidentContextError] = useState<string>("");
  const [casesError, setCasesError] = useState<string>("");
  const [clockText, setClockText] = useState<string>("--:--:--");
  const transcriptAudioRef = useRef<HTMLAudioElement | null>(null);
  const intakeAudioInputRef = useRef<HTMLInputElement | null>(null);

  const refreshResidents = useCallback(async () => {
    setLoadingResidents(true);
    setResidentError("");
    try {
      const payload = await listResidents();
      setResidents(payload);
      if (payload.length > 0) {
        setSelectedResidentId((current) => current || payload[0].profile_id);
      }
    } catch (error) {
      setResidentError(error instanceof Error ? error.message : "Failed to load resident profiles.");
    } finally {
      setLoadingResidents(false);
    }
  }, []);

  const refreshCases = useCallback(async () => {
    setLoadingCases(true);
    setCasesError("");
    try {
      const [pending, assessed, processed] = await Promise.all([
        listCasesByState("pending_ai_assessment"),
        listCasesByState("ai_assessed"),
        listCasesByState("operator_processed")
      ]);
      setCasesByState({
        pending_ai_assessment: pending,
        ai_assessed: assessed,
        operator_processed: processed
      });
    } catch (error) {
      setCasesError(error instanceof Error ? error.message : "Failed to load case queues.");
    } finally {
      setLoadingCases(false);
    }
  }, []);

  useEffect(() => {
    void refreshResidents();
    void refreshCases();
  }, [refreshCases, refreshResidents]);

  useEffect(() => {
    const updateClock = () => {
      setClockText(new Date().toLocaleTimeString());
    };
    updateClock();
    const timerId = setInterval(updateClock, 1000);
    return () => clearInterval(timerId);
  }, []);

  useEffect(() => {
    if (!selectedResidentId) {
      setSelectedResidentContext(null);
      setResidentContextError("");
      return;
    }

    let cancelled = false;
    const loadResidentContext = async () => {
      setResidentContextError("");
      try {
        const context = await getResidentContext(selectedResidentId);
        if (cancelled) {
          return;
        }
        setSelectedResidentContext(context);
      } catch (error) {
        if (cancelled) {
          return;
        }
        setSelectedResidentContext(null);
        setResidentContextError(error instanceof Error ? error.message : "Failed to load selected profile details.");
      }
    };

    void loadResidentContext();
    return () => {
      cancelled = true;
    };
  }, [selectedResidentId]);

  useEffect(() => {
    const audio = transcriptAudioRef.current;
    if (!audio) {
      return;
    }
    const syncDuration = () => {
      const duration = Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : 0;
      setAudioDuration(duration);
    };
    const syncCurrentTime = () => {
      const current = Number.isFinite(audio.currentTime) && audio.currentTime >= 0 ? audio.currentTime : 0;
      setAudioCurrentTime(current);
    };
    const onPlay = () => setIsAudioPlaying(true);
    const onPause = () => setIsAudioPlaying(false);
    const onEnded = () => {
      setIsAudioPlaying(false);
      syncCurrentTime();
    };
    const onError = () => {
      setIsAudioPlaying(false);
      setAudioPlayError("Unable to play this recording.");
    };

    audio.addEventListener("loadedmetadata", syncDuration);
    audio.addEventListener("durationchange", syncDuration);
    audio.addEventListener("timeupdate", syncCurrentTime);
    audio.addEventListener("play", onPlay);
    audio.addEventListener("pause", onPause);
    audio.addEventListener("ended", onEnded);
    audio.addEventListener("error", onError);
    return () => {
      audio.removeEventListener("loadedmetadata", syncDuration);
      audio.removeEventListener("durationchange", syncDuration);
      audio.removeEventListener("timeupdate", syncCurrentTime);
      audio.removeEventListener("play", onPlay);
      audio.removeEventListener("pause", onPause);
      audio.removeEventListener("ended", onEnded);
      audio.removeEventListener("error", onError);
    };
  }, [selectedCase?.metadata.case_id]);

  useEffect(() => {
    const audio = transcriptAudioRef.current;
    if (!audio) {
      return;
    }
    audio.pause();
    audio.currentTime = 0;
    setIsAudioPlaying(false);
    setAudioPlayError("");
    setAudioCurrentTime(0);
    setAudioDuration(0);
  }, [selectedCase?.metadata.case_id]);

  const orderedCaseQueue = useMemo(() => {
    return CASE_QUEUE_ORDER.flatMap((state) => casesByState[state]);
  }, [casesByState]);

  useEffect(() => {
    if (!selectedCaseId && orderedCaseQueue.length > 0) {
      setSelectedCaseId(orderedCaseQueue[0].case_id);
    }
  }, [orderedCaseQueue, selectedCaseId]);

  useEffect(() => {
    if (!selectedCaseId) {
      setSelectedCase(null);
      return;
    }

    let cancelled = false;
    const loadCase = async () => {
      setLoadingCaseDetail(true);
      setCasesError("");
      try {
        const detail = await getCaseDetail(selectedCaseId);
        if (cancelled) {
          return;
        }
        setSelectedCase(detail);
        setSelectedResidentId(detail.resident_profile.profile_id);
      } catch (error) {
        if (cancelled) {
          return;
        }
        setCasesError(error instanceof Error ? error.message : "Failed to load selected case detail.");
      } finally {
        if (!cancelled) {
          setLoadingCaseDetail(false);
        }
      }
    };

    void loadCase();
    return () => {
      cancelled = true;
    };
  }, [selectedCaseId]);

  const selectedCaseConfidenceScore = confidenceScore(selectedCase?.triage_result?.overall_confidence);
  const selectedStageEvidence =
    (selectedCase?.triage_result?.stage_evidence as Record<string, unknown> | undefined) ?? null;
  const selectedCaseRiskScore = weightedRiskScore(selectedStageEvidence) ?? llmRiskScore(selectedStageEvidence);
  const selectedCaseScore = selectedCaseRiskScore ?? selectedCaseConfidenceScore;
  const audioTimelineMax = audioDuration > 0 ? audioDuration : 1;
  const audioTimelineValue = audioDuration > 0 ? Math.min(audioCurrentTime, audioDuration) : 0;
  const selectedResidentProfile = useMemo(() => {
    const fromContext = selectedResidentContext?.resident_profile;
    if (fromContext && fromContext.profile_id === selectedResidentId) {
      return fromContext;
    }
    const fromList = residents.find((resident) => resident.profile_id === selectedResidentId);
    return fromList ?? selectedCase?.resident_profile ?? fromContext ?? null;
  }, [residents, selectedResidentId, selectedCase, selectedResidentContext]);
  const selectedResidentMedical = useMemo(() => {
    if (selectedResidentContext && selectedResidentContext.resident_profile.profile_id === selectedResidentId) {
      return selectedResidentContext.raw_medical_history;
    }
    if (!selectedCase || !selectedResidentProfile) {
      return null;
    }
    if (selectedCase.resident_profile.profile_id !== selectedResidentProfile.profile_id) {
      return null;
    }
    return selectedCase.raw_medical_history;
  }, [selectedCase, selectedResidentContext, selectedResidentId, selectedResidentProfile]);
  const fallRisk = selectedCase?.derived_medical_flags?.high_fall_risk ?? false;
  const cardiacRisk = selectedCase?.derived_medical_flags?.cardio_risk ?? false;
  const socialVulnerability = useMemo(() => {
    if (!selectedCase) {
      return false;
    }
    const mobility = selectedCase.resident_profile.mobility_status.trim().toLowerCase();
    return selectedCase.resident_profile.living_alone && mobility !== "independent";
  }, [selectedCase]);
  const dischargeDays = useMemo(() => {
    if (!selectedCase) {
      return null;
    }
    const dischargeRaw = selectedCase.raw_medical_history.last_discharge_date;
    if (!dischargeRaw) {
      return null;
    }
    const dischargeDate = new Date(dischargeRaw);
    const referenceDate = new Date(selectedCase.metadata.updated_at || selectedCase.metadata.created_at);
    if (Number.isNaN(dischargeDate.getTime()) || Number.isNaN(referenceDate.getTime())) {
      return null;
    }
    const elapsedMs = referenceDate.getTime() - dischargeDate.getTime();
    if (elapsedMs < 0) {
      return null;
    }
    return Math.floor(elapsedMs / (24 * 60 * 60 * 1000));
  }, [selectedCase]);
  const recentDischargeRisk = dischargeDays !== null && dischargeDays <= 30;
  const falseAlarmRatio = useMemo(() => {
    if (!selectedCase) {
      return 0;
    }
    const total = selectedCase.raw_call_history.total_calls_last_30d;
    if (total <= 0) {
      return 0;
    }
    return selectedCase.raw_call_history.false_alarm_count_last_30d / total;
  }, [selectedCase]);
  const falseAlarmRatioPct = Math.round(falseAlarmRatio * 100);
  const highFalseAlarmRatio = falseAlarmRatio >= 0.4;
  const falseAlarmCount = selectedCase?.raw_call_history.false_alarm_count_last_30d ?? 0;
  const totalCalls = selectedCase?.raw_call_history.total_calls_last_30d ?? 0;
  const displaySpeech = useMemo(() => {
    const speech = selectedCase?.speech_result;
    if (!speech) {
      return {
        language: "-",
        dialect: "-",
        mixed: false
      };
    }

    const mixed = hasMixedEnglishChinese(speech.transcript_original || "");
    if (mixed) {
      return {
        language: "English / Chinese",
        dialect: "Mixed",
        mixed: true
      };
    }

    return {
      language: speech.detected_language || "-",
      dialect: speech.dialect_label || "-",
      mixed: false
    };
  }, [selectedCase?.speech_result]);
  const derivedFeatureCards = useMemo(() => {
    const diagnoses = selectedCase?.raw_medical_history.diagnoses ?? [];
    const mobilityText = selectedCase?.resident_profile.mobility_status ?? "-";
    const hasDiagnosis = (needle: string): boolean =>
      diagnoses.some((diagnosis) => diagnosis.toLowerCase().includes(needle.toLowerCase()));

    const fallReason = (() => {
      if (!fallRisk) {
        return "No strong trigger";
      }
      if (hasDiagnosis("diabetes")) {
        return "Diabetes";
      }
      if (hasDiagnosis("osteoporosis")) {
        return "Osteoporosis";
      }
      return "High fall-risk feature";
    })();

    const cardiacReason = (() => {
      if (!cardiacRisk) {
        return "No cardiac trigger";
      }
      if (hasDiagnosis("atrial_fibrillation")) {
        return "Atrial fibrillation";
      }
      if (hasDiagnosis("hypertension")) {
        return "Hypertension";
      }
      return "Cardio-risk feature";
    })();

    const recentDischargeReason =
      dischargeDays === null ? "No discharge record" : `${dischargeDays} day(s) since discharge`;

    const socialReason = (() => {
      if (socialVulnerability) {
        return `Living alone + ${mobilityText}`;
      }
      if (!selectedCase?.resident_profile.living_alone) {
        return "Not living alone";
      }
      return "Independent mobility";
    })();

    const falseAlarmReason = `${falseAlarmCount}/${totalCalls} in 30d`;

    return [
      {
        label: "Fall Risk",
        value: fallRisk ? "Elevated" : "Low",
        valueTone: featureTone(fallRisk),
        reason: fallReason
      },
      {
        label: "Cardiac Risk",
        value: cardiacRisk ? "Elevated" : "Low",
        valueTone: featureTone(cardiacRisk),
        reason: cardiacReason
      },
      {
        label: "Recent Discharge Risk",
        value: recentDischargeRisk ? "Elevated" : "Low",
        valueTone: featureTone(recentDischargeRisk),
        reason: recentDischargeReason
      },
      {
        label: "Social Vulnerability",
        value: socialVulnerability ? "Elevated" : "Low",
        valueTone: featureTone(socialVulnerability),
        reason: socialReason
      },
      {
        label: "False Alarm Ratio",
        value: `${falseAlarmRatioPct}%`,
        valueTone: highFalseAlarmRatio ? "text-amber-300" : "text-emerald-300",
        reason: falseAlarmReason
      }
    ];
  }, [
    selectedCase,
    fallRisk,
    cardiacRisk,
    recentDischargeRisk,
    dischargeDays,
    socialVulnerability,
    falseAlarmRatioPct,
    highFalseAlarmRatio,
    falseAlarmCount,
    totalCalls,
    dischargeDays
  ]);

  async function handleCreateIntakeCase(): Promise<void> {
    if (!selectedResidentId || !selectedAudioFile) {
      return;
    }
    setCreatingIntake(true);
    setCasesError("");
    try {
      const created = await createIntakeCase(selectedResidentId, selectedAudioFile);
      setSelectedAudioFile(null);
      if (intakeAudioInputRef.current) {
        intakeAudioInputRef.current.value = "";
      }
      setSelectedCase(created);
      setSelectedCaseId(created.metadata.case_id);
      await refreshCases();

      setProcessingCase(true);
      try {
        const processed = await processAiCase(created.metadata.case_id);
        setSelectedCase(processed);
      } catch (error) {
        setCasesError(
          error instanceof Error
            ? `Case injected to Pending AI Assessment, but auto AI run failed: ${error.message}`
            : "Case injected to Pending AI Assessment, but auto AI run failed."
        );
      } finally {
        setProcessingCase(false);
      }

      await refreshCases();
    } catch (error) {
      setCasesError(error instanceof Error ? error.message : "Unable to inject case.");
    } finally {
      setCreatingIntake(false);
    }
  }

  async function handleOperatorAction(action: RecommendedAction): Promise<void> {
    if (!selectedCaseId) {
      return;
    }
    const actionLabel = compactActionLabel(action);
    const shouldProceed = window.confirm(
      `Confirm operator action for ${selectedCaseId}:\n${actionLabel}\n\nThis will finalize the case as operator processed.`
    );
    if (!shouldProceed) {
      return;
    }
    setProcessingCase(true);
    setCasesError("");
    try {
      const updated = await submitOperatorDecision(selectedCaseId, {
        operator_id: OPERATOR_ID,
        chosen_action: action,
        notes: `Chosen from triage console at ${new Date().toISOString()}`
      });
      setSelectedCase(updated);
      await refreshCases();
    } catch (error) {
      setCasesError(error instanceof Error ? error.message : "Failed to submit operator action.");
    } finally {
      setProcessingCase(false);
    }
  }

  async function handleDeleteCase(): Promise<void> {
    if (!selectedCaseId) {
      return;
    }
    const shouldDelete = window.confirm(`Remove case ${selectedCaseId}? This cannot be undone.`);
    if (!shouldDelete) {
      return;
    }

    setProcessingCase(true);
    setCasesError("");
    try {
      await deleteCase(selectedCaseId);
      setSelectedCase(null);
      setSelectedCaseId(null);
      await refreshCases();
    } catch (error) {
      setCasesError(error instanceof Error ? error.message : "Failed to remove case.");
    } finally {
      setProcessingCase(false);
    }
  }

  async function handleTranscriptAudioToggle(): Promise<void> {
    const audio = transcriptAudioRef.current;
    if (!audio) {
      return;
    }

    setAudioPlayError("");
    if (audio.paused) {
      try {
        if (audio.readyState === 0) {
          audio.load();
        }
        await audio.play();
      } catch {
        setAudioPlayError("Unable to play this recording.");
      }
      return;
    }
    audio.pause();
    audio.currentTime = 0;
    setAudioCurrentTime(0);
  }

  function handleTranscriptAudioSeek(event: ChangeEvent<HTMLInputElement>): void {
    const audio = transcriptAudioRef.current;
    if (!audio) {
      return;
    }
    const nextTime = Number(event.target.value);
    if (Number.isNaN(nextTime)) {
      return;
    }
    audio.currentTime = nextTime;
    setAudioCurrentTime(nextTime);
  }

  return (
    <main className="min-h-screen bg-[#02050d] text-slate-100">
      <header className="flex items-center justify-between border-b border-cyan-900/40 bg-[#030916] px-4 py-3 text-xs tracking-widest text-cyan-200/80">
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold tracking-wide text-cyan-100">PAB TRIAGE SYSTEM</span>
          <span className="text-cyan-600">| GOVTECH SINGAPORE</span>
          <span className="text-cyan-500">v1.0.0</span>
        </div>
        <div className="flex items-center gap-3 text-cyan-400/80">
          <span className="rounded border border-cyan-700/50 px-2 py-0.5">MOCK</span>
          <span>{clockText}</span>
        </div>
      </header>

      <div className="grid min-h-[calc(100vh-49px)] grid-cols-1 xl:grid-cols-[330px_330px_minmax(0,1fr)]">
        <aside className="border-r border-cyan-950/60 bg-[#030b19] p-4">
          <div className="rounded border border-cyan-900/60 bg-[#071428] p-2">
            <p className="mb-1.5 text-[11px] font-bold uppercase tracking-[0.24em] text-cyan-500">Injection Console</p>
            <label className="mb-1 block text-[11px] text-cyan-200/80">Profile</label>
            <select
              className="w-full rounded border border-cyan-800/80 bg-[#030d1f] px-3 py-1 text-sm text-cyan-100 outline-none focus:border-cyan-500"
              value={selectedResidentId}
              onChange={(event) => setSelectedResidentId(event.target.value)}
              disabled={creatingIntake || loadingResidents}
            >
              <option value="">{loadingResidents ? "Loading profiles..." : "Select profile"}</option>
              {residents.map((resident) => (
                <option key={resident.profile_id} value={resident.profile_id}>
                  {resident.name}
                </option>
              ))}
            </select>

            {!loadingResidents && residents.length === 0 ? (
              <p className="mt-1.5 rounded border border-amber-700/40 bg-amber-950/20 px-2 py-1 text-[11px] text-amber-300">
                No profiles available.
              </p>
            ) : null}
            {residentError ? (
              <div className="mt-1.5 rounded border border-red-700/40 bg-red-950/20 px-2 py-1 text-[11px] text-red-300">
                <p>{residentError}</p>
                <button
                  className="mt-1.5 rounded border border-red-600/60 bg-red-900/30 px-2 py-1 text-[11px] uppercase tracking-wider text-red-100"
                  onClick={() => void refreshResidents()}
                >
                  Retry Profiles
                </button>
              </div>
            ) : null}

            <label className="mb-1 mt-2 block text-[11px] text-cyan-200/80">Prerecorded Audio</label>
            <div className="rounded border border-dashed border-cyan-700/70 bg-[#030d1f] p-1.5">
              <input
                ref={intakeAudioInputRef}
                type="file"
                accept="audio/*"
                onChange={(event) => setSelectedAudioFile(event.target.files?.[0] ?? null)}
                className="w-full text-[11px] text-cyan-200 file:mr-2 file:rounded file:border-0 file:bg-cyan-700/20 file:px-2 file:py-1 file:text-cyan-100"
                disabled={creatingIntake}
              />
              <p className="mt-1.5 text-[11px] text-cyan-400/80">
                {selectedAudioFile ? `${selectedAudioFile.name} (${Math.round(selectedAudioFile.size / 1024)} KB)` : "No file chosen"}
              </p>
            </div>

            <button
              className="mt-2 w-full rounded bg-blue-600 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-white transition hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-cyan-900/60"
              onClick={() => void handleCreateIntakeCase()}
              disabled={!selectedResidentId || !selectedAudioFile || creatingIntake || processingCase}
            >
              {creatingIntake ? "Injecting..." : processingCase ? "Running AI..." : "Inject Case"}
            </button>
          </div>

          <div className="mt-4 rounded border border-cyan-900/60 bg-[#071428] p-4">
            <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.24em] text-cyan-500">Profile Details</p>
            <div className="space-y-2 text-xs text-cyan-200/90">
              {selectedResidentProfile ? (
                <>
                  <p>
                    <span className="text-cyan-500">Profile ID:</span> {selectedResidentProfile.profile_id}
                  </p>
                  <p>
                    <span className="text-cyan-500">Name:</span> {selectedResidentProfile.name}
                  </p>
                  <p>
                    <span className="text-cyan-500">Age:</span> {selectedResidentProfile.age}
                  </p>
                  <p>
                    <span className="text-cyan-500">Address:</span> {selectedResidentProfile.block} {selectedResidentProfile.unit}
                    {selectedResidentProfile.postal_code ? ` (S${selectedResidentProfile.postal_code})` : ""}
                  </p>
                  <p>
                    <span className="text-cyan-500">Language/Dialect:</span> {selectedResidentProfile.preferred_language} /{" "}
                    {selectedResidentProfile.preferred_dialect}
                  </p>
                  <p>
                    <span className="text-cyan-500">Living Alone:</span> {selectedResidentProfile.living_alone ? "Yes" : "No"}
                  </p>
                  <p>
                    <span className="text-cyan-500">Mobility:</span> {selectedResidentProfile.mobility_status}
                  </p>
                  <p>
                    <span className="text-cyan-500">Emergency Contact:</span> {selectedResidentProfile.emergency_contact}
                  </p>
                  <p>
                    <span className="text-cyan-500">Known Diagnoses:</span>{" "}
                    {selectedResidentMedical?.diagnoses.length ? selectedResidentMedical.diagnoses.join(", ") : "No profile data"}
                  </p>
                  <p>
                    <span className="text-cyan-500">Allergies:</span>{" "}
                    {selectedResidentMedical?.allergies.length ? selectedResidentMedical.allergies.join(", ") : "No profile data"}
                  </p>
                  <p>
                    <span className="text-cyan-500">Medications:</span>{" "}
                    {selectedResidentMedical?.medications.length ? selectedResidentMedical.medications.join(", ") : "No profile data"}
                  </p>
                  <p>
                    <span className="text-cyan-500">Last Discharge Date:</span> {selectedResidentMedical?.last_discharge_date ?? "-"}
                  </p>
                  {residentContextError ? <p className="text-red-300">{residentContextError}</p> : null}
                </>
              ) : (
                <p className="text-cyan-700">Select a profile to view details.</p>
              )}
            </div>
          </div>
        </aside>

        <section className="border-r border-cyan-950/60 bg-[#020914] p-3">
          <div className="rounded border border-cyan-900/60 bg-[#071428] p-2">
            <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.24em] text-cyan-500">Case Queue</p>
            <div className="space-y-3 text-xs">
              {CASE_QUEUE_ORDER.map((state) => (
                <div key={state} className="rounded border border-cyan-900/60 bg-[#030d1f] p-2.5">
                  <p className="mb-1 font-bold text-cyan-400/80">
                    {stateLabel(state)} ({casesByState[state].length})
                  </p>
                  <div className="space-y-1">
                    {casesByState[state].map((item) => (
                      <button
                        key={item.case_id}
                        className={`w-full rounded border px-2 py-1 text-left ${
                          selectedCaseId === item.case_id
                            ? "border-cyan-500/60 bg-cyan-900/20"
                            : "border-cyan-900/40 bg-[#030d1d] hover:border-cyan-700/70"
                        }`}
                        onClick={() => setSelectedCaseId(item.case_id)}
                      >
                        <p className="font-mono text-sm text-cyan-100">{item.case_id}</p>
                        <p className={`text-sm font-semibold ${urgencyTone(item.urgency_class)}`}>
                          {(item.urgency_class ?? "pending").toUpperCase()}
                        </p>
                      </button>
                    ))}
                    {casesByState[state].length === 0 ? <p className="text-[10px] text-cyan-700">No cases.</p> : null}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="bg-[#020815] p-4">
          {loadingCases || loadingCaseDetail ? (
            <div className="rounded border border-cyan-900/60 bg-[#071428] p-6 text-sm text-cyan-200/80">Loading triage console...</div>
          ) : selectedCase ? (
            <div className="space-y-4">
              <div className="rounded border border-cyan-900/50 bg-[#0a1423] p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-xs font-bold uppercase tracking-[0.2em] text-cyan-500">Case {selectedCase.metadata.case_id}</p>
                    <h2 className={`mt-1 text-3xl font-bold uppercase tracking-wide ${urgencyTone(selectedCase.triage_result?.urgency_class)}`}>
                      {selectedCase.triage_result?.urgency_class ?? "pending"}
                    </h2>
                    <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
                      <span className="font-bold uppercase tracking-[0.14em] text-cyan-500">Language/Dialect:</span>
                      <span className="text-cyan-100">
                        {displaySpeech.language} / {displaySpeech.dialect}
                      </span>
                      <span className="text-cyan-700">|</span>
                      <span className="font-bold uppercase tracking-[0.14em] text-cyan-500">State:</span>
                      <span className="text-cyan-100">{stateLabel(selectedCase.metadata.state)}</span>
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-5xl font-bold text-amber-300">{selectedCaseScore}</p>
                    <p className="text-xs text-cyan-500">
                      /100 {selectedCaseRiskScore != null ? "risk score" : "confidence"}
                    </p>
                  </div>
                </div>
                <div className="mt-3 h-1.5 overflow-hidden rounded bg-cyan-950">
                  <div className={`h-full ${urgencyBar(selectedCase.triage_result?.urgency_class)}`} style={{ width: `${selectedCaseScore}%` }} />
                </div>
              </div>

              <div className="flex gap-2 border-b border-cyan-950/70 pb-2 text-xs">
                {(["overview", "raw"] as const).map((tab) => (
                  <button
                    key={tab}
                    className={`rounded px-3 py-1.5 uppercase tracking-[0.12em] ${
                      activeTab === tab ? "bg-cyan-700/30 text-cyan-100" : "text-cyan-400/70 hover:text-cyan-200"
                    }`}
                    onClick={() => setActiveTab(tab)}
                  >
                    {tab}
                  </button>
                ))}
              </div>

              {activeTab === "overview" ? (
                <div className="space-y-3">
                  <div className="rounded border border-cyan-900/60 bg-[#071428] p-3">
                    <p className="mb-1 text-[11px] font-bold uppercase tracking-[0.18em] text-cyan-500">Transcript</p>
                    <audio
                      ref={transcriptAudioRef}
                      preload="metadata"
                      src={selectedCase ? getCaseAudioUrl(selectedCase.metadata.case_id) : undefined}
                    />
                    <div className="mt-0 grid gap-3 md:grid-cols-[minmax(0,1fr)_28%] xl:grid-cols-[minmax(0,1fr)_22%] md:items-start">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm text-cyan-100">[{displaySpeech.language}]</span>
                          <span className="text-sm text-cyan-100">{selectedCase.speech_result?.transcript_original ?? "-"}</span>
                        </div>
                        <p className="mt-1 text-sm text-cyan-300/90">"{selectedCase.speech_result?.transcript_english ?? "-"}"</p>
                      </div>
                      <div className="w-full md:-mt-4">
                        <div className="mb-0.5 flex justify-center">
                          <button
                            className="inline-flex h-7 w-7 items-center justify-center rounded border border-cyan-700/70 bg-cyan-900/30 text-cyan-100 hover:border-cyan-500/80 disabled:cursor-not-allowed disabled:opacity-60"
                            onClick={() => void handleTranscriptAudioToggle()}
                            type="button"
                            disabled={!selectedCase}
                            title={isAudioPlaying ? "Stop audio" : "Play audio"}
                            aria-label={isAudioPlaying ? "Stop audio" : "Play audio"}
                          >
                            {isAudioPlaying ? (
                              <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current" aria-hidden="true">
                                <rect x="7" y="7" width="10" height="10" rx="1.5" />
                              </svg>
                            ) : (
                              <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current" aria-hidden="true">
                                <path d="M8 6v12l10-6-10-6z" />
                              </svg>
                            )}
                          </button>
                        </div>
                        <div className="mb-0.5 flex items-center justify-between text-[11px] text-cyan-400/90">
                          <span>{formatAudioTime(audioTimelineValue)}</span>
                          <span>{formatAudioTime(audioDuration)}</span>
                        </div>
                        <input
                          type="range"
                          min={0}
                          max={audioTimelineMax}
                          step={0.1}
                          value={audioTimelineValue}
                          onChange={handleTranscriptAudioSeek}
                          className="w-full accent-cyan-400 disabled:cursor-not-allowed disabled:opacity-50"
                          disabled={!selectedCase || audioDuration <= 0}
                        />
                      </div>
                    </div>
                    {audioPlayError ? <p className="mt-2 text-xs text-red-300">{audioPlayError}</p> : null}
                  </div>
                  <div className="rounded border border-cyan-900/60 bg-[#071428] p-3">
                    <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.18em] text-cyan-500">Derived Features</p>
                    <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
                      {derivedFeatureCards.map((feature) => (
                        <div key={feature.label} className="min-h-16 rounded border border-cyan-800/60 bg-[#031022] p-2">
                          <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-cyan-500">{feature.label}</p>
                          <p className="mt-1 text-xs">
                            <span className={`font-semibold ${feature.valueTone}`}>{feature.value}</span>
                            <span className="text-cyan-300/85"> - ({feature.reason})</span>
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="rounded border border-cyan-900/60 bg-[#071428] p-3">
                    <p className="mb-1 text-[11px] font-bold uppercase tracking-[0.18em] text-cyan-500">Situation Summary</p>
                    <ul className="space-y-1 text-sm text-cyan-100">
                      {toPointForm(selectedCase.summary_text).map((point, index) => (
                        <li key={`${point}-${index}`} className="flex gap-2">
                          <span className="text-cyan-400">-</span>
                          <span>{point}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              ) : null}

              {activeTab === "raw" ? (
                <div className="space-y-3">
                  <div className="rounded border border-cyan-900/60 bg-[#071428] p-3">
                    <p className="mb-1 text-[11px] font-bold uppercase tracking-[0.18em] text-cyan-500">Raw Medical History</p>
                    <pre className="overflow-x-auto text-xs text-cyan-200">{JSON.stringify(selectedCase.raw_medical_history, null, 2)}</pre>
                  </div>
                  <div className="rounded border border-cyan-900/60 bg-[#071428] p-3">
                    <p className="mb-1 text-[11px] font-bold uppercase tracking-[0.18em] text-cyan-500">Raw Call History</p>
                    <pre className="overflow-x-auto text-xs text-cyan-200">{JSON.stringify(selectedCase.raw_call_history, null, 2)}</pre>
                  </div>
                  <div className="rounded border border-cyan-900/60 bg-[#071428] p-3">
                    <p className="mb-1 text-[11px] font-bold uppercase tracking-[0.18em] text-cyan-500">Fusion Evidence</p>
                    <pre className="overflow-x-auto text-xs text-cyan-200">
                      {JSON.stringify(selectedCase.triage_result?.stage_evidence ?? {}, null, 2)}
                    </pre>
                  </div>
                </div>
              ) : null}

              {activeTab === "overview" ? (
                <>
                  <div className="rounded border border-amber-800/50 bg-amber-950/10 p-3 text-center">
                    <p className="mb-1 text-[11px] font-bold uppercase tracking-[0.18em] text-amber-400">Operator Recommendation</p>
                    <p className="text-sm text-amber-100">
                      {selectedCase.triage_result
                        ? llmRecommendationTail(selectedCase.triage_result.reasoning)
                        : "Run triage analysis to generate recommendation."}
                    </p>
                  </div>

                  <div className="rounded border border-cyan-900/60 bg-[#071428] p-3">
                    <div className="grid grid-cols-3 gap-2">
                      <button
                        className="w-full rounded border border-blue-700/70 bg-blue-900/30 px-3 py-2 text-sm text-blue-100 disabled:cursor-not-allowed disabled:opacity-50"
                        onClick={() => void handleOperatorAction("operator_callback")}
                        disabled={selectedCase.metadata.state !== "ai_assessed" || processingCase}
                      >
                        Operator Callback
                      </button>
                      <button
                        className="w-full rounded border border-emerald-700/70 bg-emerald-900/30 px-3 py-2 text-sm text-emerald-100 disabled:cursor-not-allowed disabled:opacity-50"
                        onClick={() => void handleOperatorAction("community_response")}
                        disabled={selectedCase.metadata.state !== "ai_assessed" || processingCase}
                      >
                        Community Response
                      </button>
                      <button
                        className="w-full rounded border border-red-700/70 bg-red-900/30 px-3 py-2 text-sm text-red-100 disabled:cursor-not-allowed disabled:opacity-50"
                        onClick={() => void handleOperatorAction("ambulance_dispatch")}
                        disabled={selectedCase.metadata.state !== "ai_assessed" || processingCase}
                      >
                        Dispatch Ambulance
                      </button>
                    </div>
                    <button
                      className="mx-auto mt-3 block rounded border border-red-700/70 bg-red-900/20 px-4 py-2 text-sm font-semibold text-red-100 hover:bg-red-900/30 disabled:cursor-not-allowed disabled:opacity-50"
                      onClick={() => void handleDeleteCase()}
                      disabled={!selectedCaseId || processingCase}
                    >
                      Remove Case
                    </button>
                    {selectedCase.operator_decision ? (
                      <p className="mt-3 text-center text-xs text-cyan-200">
                        Operator decision: {compactActionLabel(selectedCase.operator_decision.chosen_action)} |{" "}
                        {formatTime(selectedCase.operator_decision.processed_at)}
                      </p>
                    ) : null}
                  </div>
                </>
              ) : null}
            </div>
          ) : (
            <div className="rounded border border-cyan-900/60 bg-[#071428] p-6 text-sm text-cyan-200/80">
              No case selected yet. Create an intake case to begin triage.
            </div>
          )}

          {casesError ? (
            <div className="mt-3 rounded border border-red-700/40 bg-red-950/30 px-3 py-2 text-xs text-red-300">
              <p>{casesError}</p>
              <button
                className="mt-2 rounded border border-red-600/60 bg-red-900/30 px-2 py-1 text-[11px] uppercase tracking-wider text-red-100"
                onClick={() => {
                  void refreshResidents();
                  void refreshCases();
                }}
              >
                Retry Connection
              </button>
            </div>
          ) : null}
        </section>
      </div>
    </main>
  );
}
