export type ProfileRecord = {
  profile_id: string;
  unit_patient_information: {
    unit_block?: string;
    resident_name?: string;
    age: number;
    living_alone_flag: boolean;
    mobility_status: string;
    caregiver_available: boolean;
  };
  medical_history: {
    cardiac_risk_flag: boolean;
    fall_risk_flag: boolean;
    diabetes_flag: boolean;
    dementia_risk_flag: boolean;
    recent_discharge_flag: boolean;
  };
  historical_call_history: {
    calls_last_7d: number;
    calls_last_30d: number;
    false_alarm_rate: number;
    last_call_timestamp: string;
    average_call_duration: number;
  };
};

export type IntakeArtifactInput = {
  name: string;
  file_type: string;
  notes?: string;
};

export type OperatorAction =
  | "operator_callback"
  | "community_response"
  | "ambulance_dispatch";

export type SeverityLevel = "high" | "medium" | "low";

export type CaseIntakePayload = {
  profile_id?: string;
  custom_profile?: CustomProfileInput;
  intake_artifacts: IntakeArtifactInput[];
};

export type CaseOutcomePayload = {
  actual_severity: SeverityLevel;
  actual_action?: OperatorAction;
  actual_false_alarm?: boolean;
  actual_emergency_type?: string;
  notes?: string;
};

export type CustomProfileInput = {
  profile_id?: string;
  unit_patient_information: {
    unit_block?: string;
    resident_name?: string;
    age: number;
    living_alone_flag: boolean;
    mobility_status: string;
    caregiver_available: boolean;
  };
  medical_history: {
    cardiac_risk_flag: boolean;
    fall_risk_flag: boolean;
    diabetes_flag: boolean;
    dementia_risk_flag: boolean;
    recent_discharge_flag: boolean;
  };
  historical_call_history: {
    calls_last_7d: number;
    calls_last_30d: number;
    false_alarm_rate: number;
    last_call_timestamp: string;
    average_call_duration: number;
  };
};

export type CaseRecord = {
  case_id: string;
  profile_id: string;
  status: "unprocessed" | "processed" | "operator_processed";
  emergency_type?: string;
  distress_level?: SeverityLevel;
  confidence?: number;
  false_alarm_probability?: number;
  recommended_action?: string;
  operator_action?: OperatorAction;
  actual_severity?: SeverityLevel;
  actual_action?: OperatorAction;
  actual_false_alarm?: boolean;
  actual_emergency_type?: string;
  outcome_notes?: string;
  outcome_recorded_at?: string;
  top_contributing_reasons?: string[];
  score_result?: {
    score: number;
    recommended_priority: 1 | 2 | 3;
    recommended_action: OperatorAction;
    confidence: number;
    factors: Array<{
      key: string;
      evidence: string;
      direction: "risk_up" | "risk_down";
      weight: number;
      source_module: string;
    }>;
  };
  audio_module?: {
    speech_cues?: string[];
    non_speech_cues?: string[];
    speech_distress_score?: number;
    non_speech_distress_score?: number;
    estimated_emergency_type?: string;
  };
  created_at: string;
  last_updated_at?: string;
};

export type TrainingRecord = {
  case_id: string;
  profile_id: string;
  unit_patient_information: ProfileRecord["unit_patient_information"];
  medical_history: ProfileRecord["medical_history"];
  historical_call_history: ProfileRecord["historical_call_history"];
  audio_module?: CaseRecord["audio_module"];
  predicted_emergency_type?: string;
  predicted_severity?: SeverityLevel;
  predicted_action?: OperatorAction;
  predicted_confidence?: number;
  predicted_false_alarm_probability?: number;
  predicted_top_contributing_reasons: string[];
  predicted_at: string;
  actual_severity?: SeverityLevel;
  actual_action?: OperatorAction;
  actual_false_alarm?: boolean;
  actual_emergency_type?: string;
  outcome_notes?: string;
  outcome_recorded_at?: string;
};
