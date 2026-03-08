export type CaseState = "pending_ai_assessment" | "ai_assessed" | "operator_processed";
export type UrgencyClass = "non-urgent" | "uncertain" | "urgent";
export type RecommendedAction = "operator_callback" | "community_response" | "ambulance_dispatch";

export interface AudioMetadata {
  filename: string;
  content_type: string;
  size_bytes: number;
  stored_path: string;
  uploaded_at: string;
}

export interface CaseMetadata {
  case_id: string;
  profile_id: string;
  state: CaseState;
  created_at: string;
  updated_at: string;
}

export interface ResidentProfile {
  profile_id: string;
  name: string;
  age: number;
  postal_code: string;
  block: string;
  unit: string;
  preferred_language: string;
  preferred_dialect: string;
  emergency_contact: string;
  mobility_status: string;
  living_alone: boolean;
}

export interface ResidentContext {
  resident_profile: ResidentProfile;
  raw_medical_history: RawMedicalHistory | null;
  raw_call_history: RawCallHistory | null;
}

export interface RawMedicalHistory {
  profile_id: string;
  diagnoses: string[];
  allergies: string[];
  medications: string[];
  last_discharge_date: string | null;
  notes: string | null;
}

export interface DerivedMedicalFlags {
  high_fall_risk: boolean;
  cardio_risk: boolean;
  respiratory_risk: boolean;
  cognitive_risk: boolean;
  polypharmacy_risk: boolean;
  evidence: string[];
}

export interface RawCallHistory {
  profile_id: string;
  total_calls_last_30d: number;
  urgent_calls_last_30d: number;
  false_alarm_count_last_30d: number;
  last_call_outcome: string | null;
  recent_call_summaries: string[];
}

export interface DerivedHistoryFlags {
  frequent_caller: boolean;
  recent_urgent_pattern: boolean;
  repeated_false_alarms: boolean;
  escalation_trend: boolean;
  evidence: string[];
}

export interface SpeechResult {
  detected_language: string;
  detected_dialect: string;
  dialect_confidence: number;
  dialect_label: string;
  transcript_original: string;
  transcript_english: string;
  speech_confidence: number;
  evidence: string[];
}

export interface LanguageRoutingResult {
  primary_language: string;
  dialect_label: string;
  routing_hint: string;
  confidence: number;
  fallback_used: boolean;
  evidence: string[];
}

export interface TriageResult {
  urgency_class: UrgencyClass;
  recommended_action: RecommendedAction;
  reasoning: string;
  routing_hint: string;
  overall_confidence: number;
  stage_evidence: Record<string, unknown>;
}

export interface OperatorDecision {
  operator_id: string;
  chosen_action: RecommendedAction;
  notes: string | null;
  processed_at: string;
  overrides_ai: boolean;
}

export interface CaseDetail {
  metadata: CaseMetadata;
  audio_metadata: AudioMetadata;
  resident_profile: ResidentProfile;
  raw_medical_history: RawMedicalHistory;
  derived_medical_flags: DerivedMedicalFlags | null;
  raw_call_history: RawCallHistory;
  derived_history_flags: DerivedHistoryFlags | null;
  speech_result: SpeechResult | null;
  language_routing_result: LanguageRoutingResult | null;
  triage_result: TriageResult | null;
  summary_text: string | null;
  operator_decision: OperatorDecision | null;
}

export interface CaseListItem {
  case_id: string;
  profile_id: string;
  resident_name: string;
  postal_code: string;
  block: string;
  unit: string;
  state: CaseState;
  created_at: string;
  updated_at: string;
  urgency_class: UrgencyClass | null;
  recommended_action: RecommendedAction | null;
  overall_confidence: number | null;
  routing_hint: string | null;
  operator_action: RecommendedAction | null;
}

export interface OperatorDecisionPayload {
  operator_id: string;
  chosen_action: RecommendedAction;
  notes?: string;
}
