"use client";

import { Fragment, FormEvent, useEffect, useMemo, useState } from "react";

import {
  createCaseIntake,
  fetchCases,
  fetchProfiles,
  setCaseOutcome,
  setOperatorAction
} from "@/lib/api";
import {
  CaseRecord,
  CaseIntakePayload,
  CustomProfileInput,
  OperatorAction,
  ProfileRecord,
  SeverityLevel
} from "@/types";

const CUSTOM_PROFILE_OPTION = "__custom__";

type BoolSelect = "true" | "false";

type CustomProfileFormState = {
  unit_block: string;
  resident_name: string;
  age: string;
  living_alone_flag: BoolSelect;
  mobility_status: string;
  mobility_status_custom: string;
  caregiver_available: BoolSelect;
  medical_age: string;
  medical_mobility_status: string;
  medical_mobility_status_custom: string;
  preexisting_conditions: string;
  medication_list: string;
  discharge_date: string;
  prior_falls_count: string;
  cognitive_status: string;
  cognitive_status_custom: string;
  calls_last_7d: string;
  calls_last_30d: string;
  false_alarm_rate: string;
  last_call_timestamp: string;
  average_call_duration: string;
};

const INITIAL_CUSTOM_PROFILE: CustomProfileFormState = {
  unit_block: "",
  resident_name: "",
  age: "70",
  living_alone_flag: "false",
  mobility_status: "assisted",
  mobility_status_custom: "",
  caregiver_available: "true",
  medical_age: "70",
  medical_mobility_status: "assisted",
  medical_mobility_status_custom: "",
  preexisting_conditions: "",
  medication_list: "",
  discharge_date: "",
  prior_falls_count: "0",
  cognitive_status: "clear",
  cognitive_status_custom: "",
  calls_last_7d: "0",
  calls_last_30d: "0",
  false_alarm_rate: "0",
  last_call_timestamp: "",
  average_call_duration: "0",
};

function toBool(value: BoolSelect): boolean {
  return value === "true";
}

function parseNonNegativeInt(raw: string): number | null {
  const value = Number(raw);
  if (!Number.isInteger(value) || value < 0) {
    return null;
  }
  return value;
}

function parseNonNegativeFloat(raw: string): number | null {
  const value = Number(raw);
  if (!Number.isFinite(value) || value < 0) {
    return null;
  }
  return value;
}

function parseDateTime(raw: string): string | null {
  const normalized = raw.trim();
  if (!normalized) {
    return null;
  }

  const parsed = new Date(normalized);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }

  return parsed.toISOString();
}

function parseDateOnly(raw: string): string | undefined {
  const normalized = raw.trim();
  if (!normalized) {
    return undefined;
  }
  const parsed = new Date(`${normalized}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) {
    return undefined;
  }
  return normalized;
}

function parseStringList(raw: string): string[] {
  return raw
    .replaceAll(";", ",")
    .replaceAll("|", ",")
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

function displayValue(value: string | number | null | undefined): string {
  if (value === null || value === undefined) {
    return "-";
  }

  if (typeof value === "string" && value.trim() === "") {
    return "-";
  }

  return String(value);
}

function displayLivingAlone(value: boolean | null | undefined): string {
  if (value === null || value === undefined) {
    return "-";
  }

  return value ? "Yes" : "No";
}

function displayDateTimeValue(value: string | null | undefined): string {
  if (!value || value.trim() === "") {
    return "-";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}

function formatConfidenceValue(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "-";
  }
  const clamped = Math.min(1, Math.max(0, value));
  return clamped.toFixed(2);
}

function actionLabel(action: OperatorAction): string {
  if (action === "ambulance_dispatch") {
    return "Dispatch Ambulance";
  }
  if (action === "operator_callback") {
    return "Operator Callback";
  }
  return "Community Response";
}

function actionConfirmationText(action: OperatorAction): string {
  if (action === "ambulance_dispatch") {
    return "Confirm operator action: Dispatch Ambulance?";
  }
  if (action === "operator_callback") {
    return "Confirm operator action: Operator Callback?";
  }
  return "Confirm operator action: Community Response?";
}

function renderCaseTableColGroup() {
  return (
    <colgroup>
      <col style={{ width: "190px" }} />
      <col style={{ width: "180px" }} />
      <col style={{ width: "80px" }} />
      <col style={{ width: "110px" }} />
      <col style={{ width: "90px" }} />
      <col style={{ width: "130px" }} />
      <col style={{ width: "120px" }} />
      <col style={{ width: "130px" }} />
      <col style={{ width: "190px" }} />
    </colgroup>
  );
}

function actionButtonClass(action: OperatorAction): string {
  if (action === "ambulance_dispatch") {
    return "action-ambulance";
  }
  if (action === "operator_callback") {
    return "action-callback";
  }
  return "action-community";
}

function toFeatureLabel(key: string, sourceModule: string): string {
  const feature = key.replace(/_/g, " ");
  const source = sourceModule.replace(/_/g, " ");
  return `${feature} (${source})`;
}

function severityLabel(level: SeverityLevel): string {
  if (level === "high") {
    return "High";
  }
  if (level === "medium") {
    return "Medium";
  }
  return "Low";
}

function severityButtonClass(level: SeverityLevel): string {
  if (level === "high") {
    return "severity-high";
  }
  if (level === "medium") {
    return "severity-medium";
  }
  return "severity-low";
}

function severityConfirmationText(level: SeverityLevel): string {
  return `Confirm actual severity: ${severityLabel(level)}?`;
}

type FeatureBreakdownRow = {
  feature: string;
  confidence: string;
  reason: string;
};

export function NewCaseIntakeForm() {
  const [profiles, setProfiles] = useState<ProfileRecord[]>([]);
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [profileSelection, setProfileSelection] = useState("");
  const [selectedAudioFile, setSelectedAudioFile] = useState<File | null>(null);
  const [customProfile, setCustomProfile] =
    useState<CustomProfileFormState>(INITIAL_CUSTOM_PROFILE);
  const [submitting, setSubmitting] = useState(false);
  const [actingCaseId, setActingCaseId] = useState<string | null>(null);
  const [settingOutcomeCaseId, setSettingOutcomeCaseId] = useState<string | null>(null);
  const [expandedCaseId, setExpandedCaseId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [createdCase, setCreatedCase] = useState<CaseRecord | null>(null);
  const [fileInputKey, setFileInputKey] = useState(0);

  useEffect(() => {
    fetchProfiles()
      .then((rows) => {
        setProfiles(rows);
      })
      .catch((err: Error) => {
        setError(err.message);
      });

    fetchCases()
      .then((rows) => {
        setCases(rows);
      })
      .catch((err: Error) => {
        setError(err.message);
      });
  }, []);

  const isCustomProfile = profileSelection === CUSTOM_PROFILE_OPTION;

  const selectedProfile = useMemo(
    () => profiles.find((item) => item.profile_id === profileSelection),
    [profiles, profileSelection]
  );

  const profilesById = useMemo(
    () => new Map(profiles.map((profile) => [profile.profile_id, profile])),
    [profiles]
  );

  const aiAssessedCases = useMemo(
    () => cases.filter((item) => item.status === "processed"),
    [cases]
  );

  const pendingAIAssessmentCases = useMemo(
    () => cases.filter((item) => item.status === "unprocessed"),
    [cases]
  );

  const operatorProcessedCases = useMemo(
    () => cases.filter((item) => item.status === "operator_processed"),
    [cases]
  );

  function handleCustomFieldChange<K extends keyof CustomProfileFormState>(
    key: K,
    value: CustomProfileFormState[K]
  ) {
    setCustomProfile((current) => ({
      ...current,
      [key]: value,
    }));
  }

  function buildCustomProfilePayload(): CustomProfileInput | null {
    const residentName = customProfile.resident_name.trim();
    const age = parseNonNegativeInt(customProfile.age);
    const medicalAge = parseNonNegativeInt(customProfile.medical_age);
    const callsLast7d = parseNonNegativeInt(customProfile.calls_last_7d);
    const callsLast30d = parseNonNegativeInt(customProfile.calls_last_30d);
    const falseAlarmRate = parseNonNegativeFloat(customProfile.false_alarm_rate);
    const lastCallTimestamp = parseDateTime(customProfile.last_call_timestamp);
    const averageCallDuration = parseNonNegativeFloat(customProfile.average_call_duration);
    const priorFallsCount = parseNonNegativeInt(customProfile.prior_falls_count);
    const dischargeDate = parseDateOnly(customProfile.discharge_date);
    const mobilityStatus =
      customProfile.mobility_status === "other"
        ? customProfile.mobility_status_custom.trim()
        : customProfile.mobility_status;
    const medicalMobilityStatus =
      customProfile.medical_mobility_status === "other"
        ? customProfile.medical_mobility_status_custom.trim()
        : customProfile.medical_mobility_status;
    const cognitiveStatus =
      customProfile.cognitive_status === "other"
        ? customProfile.cognitive_status_custom.trim()
        : customProfile.cognitive_status;
    const preexistingConditions = parseStringList(customProfile.preexisting_conditions);
    const medicationList = parseStringList(customProfile.medication_list);

    if (!residentName) {
      setError("Enter resident name for custom profile.");
      return null;
    }
    if (!mobilityStatus) {
      setError("Enter a mobility status for custom profile.");
      return null;
    }
    if (age === null || age > 130) {
      setError("Custom age must be an integer from 0 to 130.");
      return null;
    }
    if (medicalAge === null || medicalAge > 130) {
      setError("Medical history age must be an integer from 0 to 130.");
      return null;
    }
    if (callsLast7d === null || callsLast30d === null) {
      setError("Call count fields must be non-negative integers.");
      return null;
    }
    if (priorFallsCount === null) {
      setError("Prior falls count must be a non-negative integer.");
      return null;
    }
    if (lastCallTimestamp === null) {
      setError("Last call timestamp is required and must be a valid date/time.");
      return null;
    }
    if (!medicalMobilityStatus) {
      setError("Enter a medical mobility status for custom profile.");
      return null;
    }
    if (!cognitiveStatus) {
      setError("Enter a cognitive status for custom profile.");
      return null;
    }
    if (
      falseAlarmRate === null ||
      falseAlarmRate > 1 ||
      averageCallDuration === null
    ) {
      setError(
        "False alarm rate must be 0 to 1, and average call duration (seconds) must be non-negative."
      );
      return null;
    }

    return {
      unit_patient_information: {
        unit_block: customProfile.unit_block.trim() || undefined,
        resident_name: residentName,
        age,
        living_alone_flag: toBool(customProfile.living_alone_flag),
        mobility_status: mobilityStatus,
        caregiver_available: toBool(customProfile.caregiver_available),
      },
      medical_history: {
        age: medicalAge,
        mobility_status: medicalMobilityStatus,
        preexisting_conditions: preexistingConditions,
        medication_list: medicationList,
        discharge_date: dischargeDate,
        prior_falls_count: priorFallsCount,
        cognitive_status: cognitiveStatus,
      },
      historical_call_history: {
        calls_last_7d: callsLast7d,
        calls_last_30d: callsLast30d,
        false_alarm_rate: falseAlarmRate,
        last_call_timestamp: lastCallTimestamp,
        average_call_duration: averageCallDuration,
      },
    };
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setCreatedCase(null);

    if (!profileSelection) {
      setError("Select a profile or choose custom profile.");
      setSubmitting(false);
      return;
    }

    if (!selectedAudioFile) {
      setError("Choose an audio file before creating the case.");
      setSubmitting(false);
      return;
    }

    const payload: CaseIntakePayload = {
      intake_artifacts: [
        {
          name: selectedAudioFile.name,
          file_type: selectedAudioFile.type || "audio/unknown",
        },
      ],
    };

    if (isCustomProfile) {
      const customPayload = buildCustomProfilePayload();
      if (!customPayload) {
        setSubmitting(false);
        return;
      }
      payload.custom_profile = customPayload;
    } else {
      payload.profile_id = profileSelection;
    }

    try {
      const created = await createCaseIntake(payload);
      setCreatedCase(created);
      setCases((current) => {
        const exists = current.some((item) => item.case_id === created.case_id);
        const next = exists
          ? current.map((item) => (item.case_id === created.case_id ? created : item))
          : [...current, created];
        return next.sort(
          (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
        );
      });

      setSelectedAudioFile(null);
      setFileInputKey((value) => value + 1);
      if (isCustomProfile) {
        setProfileSelection(created.profile_id);
        setCustomProfile(INITIAL_CUSTOM_PROFILE);
        fetchProfiles()
          .then((rows) => setProfiles(rows))
          .catch((err: Error) => setError(err.message));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create case.");
    } finally {
      setSubmitting(false);
    }
  }

  async function onSelectOperatorAction(caseId: string, action: OperatorAction) {
    setError(null);
    setActingCaseId(caseId);
    const previousCase = cases.find((item) => item.case_id === caseId);
    const optimisticUpdatedAt = new Date().toISOString();

    setCases((current) =>
      current.map((item) =>
        item.case_id === caseId
          ? {
              ...item,
              status: "operator_processed",
              operator_action: action,
              actual_action: action,
              last_updated_at: optimisticUpdatedAt,
            }
          : item
      )
    );

    try {
      const updatedCase = await setOperatorAction(caseId, action);
      setCases((current) =>
        current.map((item) => (item.case_id === updatedCase.case_id ? updatedCase : item))
      );
    } catch (err) {
      if (previousCase) {
        setCases((current) =>
          current.map((item) => (item.case_id === previousCase.case_id ? previousCase : item))
        );
      }
      setError(err instanceof Error ? err.message : "Unable to set operator action.");
    } finally {
      setActingCaseId(null);
    }
  }

  async function onSelectActualSeverity(caseId: string, actualSeverity: SeverityLevel) {
    setError(null);
    setSettingOutcomeCaseId(caseId);

    try {
      const updatedCase = await setCaseOutcome(caseId, { actual_severity: actualSeverity });
      setCases((current) =>
        current.map((item) => (item.case_id === updatedCase.case_id ? updatedCase : item))
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to set actual severity.");
    } finally {
      setSettingOutcomeCaseId(null);
    }
  }

  function toggleCaseExpansion(caseId: string) {
    setExpandedCaseId((current) => (current === caseId ? null : caseId));
  }

  function buildFeatureBreakdownRows(item: CaseRecord): FeatureBreakdownRow[] {
    const factors = item.score_result?.factors ?? [];

    if (factors.length > 0) {
      const ranked = [...factors].sort((a, b) => Math.abs(b.weight) - Math.abs(a.weight));
      const maxAbsWeight = Math.max(...ranked.map((factor) => Math.abs(factor.weight)));

      return ranked.map((factor) => ({
        feature: toFeatureLabel(factor.key, factor.source_module),
        confidence:
          maxAbsWeight > 0
            ? formatConfidenceValue(Math.abs(factor.weight) / maxAbsWeight)
            : "-",
        reason: `${displayValue(factor.evidence)} (${
          factor.direction === "risk_up" ? "increases severity" : "reduces severity"
        })`,
      }));
    }

    const fallbackRows: FeatureBreakdownRow[] = [];
    const topReasons = item.top_contributing_reasons ?? [];
    topReasons.forEach((reason, index) => {
      fallbackRows.push({
        feature: `Top factor ${index + 1}`,
        confidence: "-",
        reason: displayValue(reason),
      });
    });

    const speechCues = item.audio_module?.speech_cues;
    if (speechCues && speechCues.length > 0) {
      fallbackRows.push({
        feature: "Audio speech cues",
        confidence: formatConfidenceValue(item.audio_module?.speech_distress_score),
        reason: speechCues.join(", "),
      });
    }

    const nonSpeechCues = item.audio_module?.non_speech_cues;
    if (nonSpeechCues && nonSpeechCues.length > 0) {
      fallbackRows.push({
        feature: "Audio non-speech cues",
        confidence: formatConfidenceValue(item.audio_module?.non_speech_distress_score),
        reason: nonSpeechCues.join(", "),
      });
    }

    if (item.audio_module?.estimated_emergency_type) {
      fallbackRows.push({
        feature: "Estimated emergency type",
        confidence: "-",
        reason: item.audio_module.estimated_emergency_type,
      });
    }

    if (item.false_alarm_probability !== null && item.false_alarm_probability !== undefined) {
      fallbackRows.push({
        feature: "False alarm probability (call history)",
        confidence: formatConfidenceValue(item.false_alarm_probability),
        reason: "Estimated from recent call behavior and historical false-alarm rate.",
      });
    }

    if (fallbackRows.length === 0) {
      fallbackRows.push({
        feature: "Feature assessment",
        confidence: "-",
        reason: "No model feature breakdown available yet.",
      });
    }

    return fallbackRows;
  }

  function renderFeatureBreakdown(item: CaseRecord) {
    const rows = buildFeatureBreakdownRows(item);

    return (
      <div className="feature-breakdown-wrap">
        <table className="feature-breakdown-table">
          <thead>
            <tr>
              <th>Feature name</th>
              <th>Feature confidence (0-1)</th>
              <th>Reasons why</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`${item.case_id}-feature-${index}`}>
                <td>{row.feature}</td>
                <td>{row.confidence}</td>
                <td>{row.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  function renderOperatorActionButtons(caseId: string) {
    const actions: OperatorAction[] = [
      "operator_callback",
      "community_response",
      "ambulance_dispatch"
    ];

    return (
      <div className="operator-actions">
        {actions.map((action) => (
          <button
            key={action}
            type="button"
            className={`secondary-btn ${actionButtonClass(action)}`}
            onClick={(event) => {
              event.stopPropagation();
              const confirmed = window.confirm(actionConfirmationText(action));
              if (!confirmed) {
                return;
              }
              onSelectOperatorAction(caseId, action);
            }}
            disabled={actingCaseId === caseId}
          >
            {actingCaseId === caseId ? "Submitting..." : actionLabel(action)}
          </button>
        ))}
      </div>
    );
  }

  function renderActualSeverityButtons(item: CaseRecord) {
    const levels: SeverityLevel[] = ["high", "medium", "low"];
    const isSubmittingOutcome = settingOutcomeCaseId === item.case_id;

    return (
      <div className="actual-severity-section">
        <strong>Actual Severity</strong>
        <div className="severity-actions">
          {levels.map((level) => (
            <button
              key={level}
              type="button"
              className={`secondary-btn ${severityButtonClass(level)}`}
              onClick={(event) => {
                event.stopPropagation();
                const confirmed = window.confirm(severityConfirmationText(level));
                if (!confirmed) {
                  return;
                }
                onSelectActualSeverity(item.case_id, level);
              }}
              disabled={isSubmittingOutcome}
            >
              {isSubmittingOutcome ? "Saving..." : severityLabel(level)}
            </button>
          ))}
        </div>
        <div className="actual-severity-value">
          Recorded: {displayValue(item.actual_severity)}
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard-layout">
      <aside className="panel left-panel">
        <h2 className="section-title">Inputs</h2>

        <form onSubmit={onSubmit} className="intake-form">
          <label className="field">
            Profile
            <select
              value={profileSelection}
              onChange={(event) => setProfileSelection(event.target.value)}
              required
            >
              <option value="" disabled>
                Select a profile
              </option>
              <option value={CUSTOM_PROFILE_OPTION}>Custom profile</option>
              {profiles.map((profile) => (
                <option value={profile.profile_id} key={profile.profile_id}>
                  {profile.profile_id} - {displayValue(profile.unit_patient_information.resident_name)}
                </option>
              ))}
            </select>
          </label>

          {isCustomProfile ? (
            <div className="profile-card">
              <h3>Custom Profile</h3>
              <div className="profile-group">
                <strong>1. Unit / Patient information</strong>
                <div>Profile ID: generated automatically when case is created.</div>
                <label className="field">
                  Unit / Block
                  <input
                    value={customProfile.unit_block}
                    onChange={(event) =>
                      handleCustomFieldChange("unit_block", event.target.value)
                    }
                    placeholder="BLK-120A-08-122"
                  />
                </label>
                <label className="field">
                  Resident name
                  <input
                    value={customProfile.resident_name}
                    onChange={(event) =>
                      handleCustomFieldChange("resident_name", event.target.value)
                    }
                    placeholder="Resident name"
                    required={isCustomProfile}
                  />
                </label>
                <label className="field">
                  Age
                  <input
                    type="number"
                    min={0}
                    max={130}
                    value={customProfile.age}
                    onChange={(event) => handleCustomFieldChange("age", event.target.value)}
                    required={isCustomProfile}
                  />
                </label>
                <label className="field">
                  Living alone flag
                  <select
                    value={customProfile.living_alone_flag}
                    onChange={(event) =>
                      handleCustomFieldChange("living_alone_flag", event.target.value as BoolSelect)
                    }
                  >
                    <option value="true">true</option>
                    <option value="false">false</option>
                  </select>
                </label>
                <label className="field">
                  Mobility status
                  <select
                    value={customProfile.mobility_status}
                    onChange={(event) =>
                      handleCustomFieldChange("mobility_status", event.target.value)
                    }
                  >
                    <option value="independent">independent</option>
                    <option value="assisted">assisted</option>
                    <option value="limited">limited</option>
                    <option value="wheelchair">wheelchair</option>
                    <option value="bedridden">bedridden</option>
                    <option value="other">other</option>
                  </select>
                </label>
                {customProfile.mobility_status === "other" ? (
                  <label className="field">
                    Mobility status (custom)
                    <input
                      value={customProfile.mobility_status_custom}
                      onChange={(event) =>
                        handleCustomFieldChange("mobility_status_custom", event.target.value)
                      }
                      required={isCustomProfile && customProfile.mobility_status === "other"}
                    />
                  </label>
                ) : null}
                <label className="field">
                  Caregiver available
                  <select
                    value={customProfile.caregiver_available}
                    onChange={(event) =>
                      handleCustomFieldChange("caregiver_available", event.target.value as BoolSelect)
                    }
                  >
                    <option value="true">true</option>
                    <option value="false">false</option>
                  </select>
                </label>
              </div>

              <div className="profile-group">
                <strong>2. Medical history</strong>
                <label className="field">
                  Age
                  <input
                    type="number"
                    min={0}
                    max={130}
                    value={customProfile.medical_age}
                    onChange={(event) =>
                      handleCustomFieldChange("medical_age", event.target.value)
                    }
                    required={isCustomProfile}
                  />
                </label>
                <label className="field">
                  Mobility status
                  <select
                    value={customProfile.medical_mobility_status}
                    onChange={(event) =>
                      handleCustomFieldChange("medical_mobility_status", event.target.value)
                    }
                  >
                    <option value="independent">independent</option>
                    <option value="assisted">assisted</option>
                    <option value="limited">limited</option>
                    <option value="wheelchair">wheelchair</option>
                    <option value="bedridden">bedridden</option>
                    <option value="other">other</option>
                  </select>
                </label>
                {customProfile.medical_mobility_status === "other" ? (
                  <label className="field">
                    Mobility status (custom)
                    <input
                      value={customProfile.medical_mobility_status_custom}
                      onChange={(event) =>
                        handleCustomFieldChange("medical_mobility_status_custom", event.target.value)
                      }
                      required={isCustomProfile && customProfile.medical_mobility_status === "other"}
                    />
                  </label>
                ) : null}
                <label className="field">
                  Preexisting conditions (comma-separated)
                  <input
                    value={customProfile.preexisting_conditions}
                    onChange={(event) =>
                      handleCustomFieldChange("preexisting_conditions", event.target.value)
                    }
                  />
                </label>
                <label className="field">
                  Medication list (comma-separated)
                  <input
                    value={customProfile.medication_list}
                    onChange={(event) =>
                      handleCustomFieldChange("medication_list", event.target.value)
                    }
                  />
                </label>
                <label className="field">
                  Discharge date
                  <input
                    type="date"
                    value={customProfile.discharge_date}
                    onChange={(event) =>
                      handleCustomFieldChange("discharge_date", event.target.value)
                    }
                  />
                </label>
                <label className="field">
                  Prior falls count
                  <input
                    type="number"
                    min={0}
                    value={customProfile.prior_falls_count}
                    onChange={(event) =>
                      handleCustomFieldChange("prior_falls_count", event.target.value)
                    }
                    required={isCustomProfile}
                  />
                </label>
                <label className="field">
                  Cognitive status
                  <select
                    value={customProfile.cognitive_status}
                    onChange={(event) =>
                      handleCustomFieldChange("cognitive_status", event.target.value)
                    }
                  >
                    <option value="clear">clear</option>
                    <option value="mild_impairment">mild_impairment</option>
                    <option value="confused">confused</option>
                    <option value="dementia">dementia</option>
                    <option value="other">other</option>
                  </select>
                </label>
                {customProfile.cognitive_status === "other" ? (
                  <label className="field">
                    Cognitive status (custom)
                    <input
                      value={customProfile.cognitive_status_custom}
                      onChange={(event) =>
                        handleCustomFieldChange("cognitive_status_custom", event.target.value)
                      }
                      required={isCustomProfile && customProfile.cognitive_status === "other"}
                    />
                  </label>
                ) : null}
              </div>

              <div className="profile-group">
                <strong>3. Historical call history</strong>
                <label className="field">
                  Calls last 7d
                  <input
                    type="number"
                    min={0}
                    value={customProfile.calls_last_7d}
                    onChange={(event) =>
                      handleCustomFieldChange("calls_last_7d", event.target.value)
                    }
                    required={isCustomProfile}
                  />
                </label>
                <label className="field">
                  Calls last 30d
                  <input
                    type="number"
                    min={0}
                    value={customProfile.calls_last_30d}
                    onChange={(event) =>
                      handleCustomFieldChange("calls_last_30d", event.target.value)
                    }
                    required={isCustomProfile}
                  />
                </label>
                <label className="field">
                  False alarm rate
                  <input
                    type="number"
                    min={0}
                    max={1}
                    step={0.01}
                    value={customProfile.false_alarm_rate}
                    onChange={(event) =>
                      handleCustomFieldChange("false_alarm_rate", event.target.value)
                    }
                    required={isCustomProfile}
                  />
                </label>
                <label className="field">
                  Last call timestamp
                  <input
                    type="datetime-local"
                    value={customProfile.last_call_timestamp}
                    onChange={(event) =>
                      handleCustomFieldChange("last_call_timestamp", event.target.value)
                    }
                    required={isCustomProfile}
                  />
                </label>
                <label className="field">
                  Average call duration (seconds)
                  <input
                    type="number"
                    min={0}
                    max={20}
                    step={0.1}
                    value={customProfile.average_call_duration}
                    onChange={(event) =>
                      handleCustomFieldChange("average_call_duration", event.target.value)
                    }
                    required={isCustomProfile}
                  />
                </label>
              </div>
            </div>
          ) : null}

          <label className="field">
            Audio file
            <input
              key={fileInputKey}
              type="file"
              accept="audio/*"
              onChange={(event) => setSelectedAudioFile(event.target.files?.[0] ?? null)}
              required
            />
          </label>

          <button type="submit" className="primary-btn" disabled={submitting}>
            {submitting ? "Creating Case..." : "Create Intake Case"}
          </button>
        </form>

        {error ? (
          <p className="status error">
            <strong>Error:</strong> {error}
          </p>
        ) : null}

        {createdCase ? (
          <p className="status success">
            Case created: <strong>{createdCase.case_id}</strong> ({createdCase.status})
          </p>
        ) : null}

        {selectedProfile ? (
          <div className="profile-card">
            <h3>Selected Profile</h3>
            <div className="profile-group">
              <strong>1. Unit / Patient information</strong>
              <div>Unit / Block: {displayValue(selectedProfile.unit_patient_information.unit_block)}</div>
              <div>Resident name: {displayValue(selectedProfile.unit_patient_information.resident_name)}</div>
              <div>Age: {selectedProfile.unit_patient_information.age}</div>
              <div>Living alone flag: {String(selectedProfile.unit_patient_information.living_alone_flag)}</div>
              <div>Mobility status: {selectedProfile.unit_patient_information.mobility_status}</div>
              <div>Caregiver available: {String(selectedProfile.unit_patient_information.caregiver_available)}</div>
            </div>
            <div className="profile-group">
              <strong>2. Medical history</strong>
              <div>Age: {selectedProfile.medical_history.age}</div>
              <div>Mobility status: {displayValue(selectedProfile.medical_history.mobility_status)}</div>
              <div>
                Preexisting conditions:{" "}
                {selectedProfile.medical_history.preexisting_conditions.length > 0
                  ? selectedProfile.medical_history.preexisting_conditions.join(", ")
                  : "-"}
              </div>
              <div>
                Medication list:{" "}
                {selectedProfile.medical_history.medication_list.length > 0
                  ? selectedProfile.medical_history.medication_list.join(", ")
                  : "-"}
              </div>
              <div>
                Discharge date: {displayValue(selectedProfile.medical_history.discharge_date)}
              </div>
              <div>Prior falls count: {selectedProfile.medical_history.prior_falls_count}</div>
              <div>Cognitive status: {displayValue(selectedProfile.medical_history.cognitive_status)}</div>
              <div>Cardiac risk flag: {String(selectedProfile.medical_history.cardiac_risk_flag)}</div>
              <div>Fall risk flag: {String(selectedProfile.medical_history.fall_risk_flag)}</div>
              <div>Diabetes flag: {String(selectedProfile.medical_history.diabetes_flag)}</div>
              <div>
                Dementia/confusion risk flag:{" "}
                {String(selectedProfile.medical_history.dementia_confusion_risk_flag)}
              </div>
              <div>Recent discharge flag: {String(selectedProfile.medical_history.recent_discharge_flag)}</div>
            </div>
            <div className="profile-group">
              <strong>3. Historical call history</strong>
              <div>Calls last 7d: {selectedProfile.historical_call_history.calls_last_7d}</div>
              <div>Calls last 30d: {selectedProfile.historical_call_history.calls_last_30d}</div>
              <div>False alarm rate: {selectedProfile.historical_call_history.false_alarm_rate}</div>
              <div>
                Last call timestamp:{" "}
                {displayDateTimeValue(selectedProfile.historical_call_history.last_call_timestamp)}
              </div>
              <div>
                Average call duration (seconds):{" "}
                {selectedProfile.historical_call_history.average_call_duration}
              </div>
            </div>
          </div>
        ) : null}
      </aside>

      <section className="right-panel">
        <div className="panel hero-panel">
          <h1 className="hero-title">GovTech PAB AI Triage Prototype</h1>
          <p className="hero-subtle">
            Modular emergency triage intake with contextual profile and incident queue.
          </p>
        </div>

        <div className="panel cases-panel">
          <h2 className="section-title">AI-Assessed Cases</h2>
          <div className="table-wrap">
            <table className="cases-table">
              {renderCaseTableColGroup()}
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Resident name</th>
                  <th>Age</th>
                  <th>Living alone?</th>
                  <th>Fall risk?</th>
                  <th>Emergency type</th>
                  <th>Distress level</th>
                  <th>Confidence (0-1)</th>
                  <th>Recommended action</th>
                </tr>
              </thead>
              <tbody>
                {aiAssessedCases.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="empty-row">
                      No AI-assessed cases.
                    </td>
                  </tr>
                ) : (
                  aiAssessedCases.map((item) => {
                    const profile = profilesById.get(item.profile_id);
                    const unitInfo = profile?.unit_patient_information;
                    const isExpanded = expandedCaseId === item.case_id;
                    return (
                      <Fragment key={item.case_id}>
                        <tr
                          className={`case-row ${isExpanded ? "case-row-expanded" : ""}`}
                          onClick={() => toggleCaseExpansion(item.case_id)}
                        >
                          <td>{new Date(item.created_at).toLocaleString()}</td>
                          <td>{displayValue(unitInfo?.resident_name)}</td>
                          <td>{displayValue(unitInfo?.age)}</td>
                          <td>{displayLivingAlone(unitInfo?.living_alone_flag)}</td>
                          <td>{displayLivingAlone(profile?.medical_history.fall_risk_flag)}</td>
                          <td>{displayValue(item.emergency_type)}</td>
                          <td>{displayValue(item.distress_level)}</td>
                          <td>{displayValue(item.confidence)}</td>
                          <td>{displayValue(item.recommended_action)}</td>
                        </tr>
                        {isExpanded ? (
                          <tr className="expanded-row">
                            <td colSpan={9}>
                              <div className="expanded-grid">
                                {renderFeatureBreakdown(item)}
                                <div className="operator-action-section">
                                  {renderOperatorActionButtons(item.case_id)}
                                </div>
                              </div>
                            </td>
                          </tr>
                        ) : null}
                      </Fragment>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          <h2 className="section-title table-subtitle">Pending AI-Assessment</h2>
          <div className="table-wrap">
            <table className="cases-table">
              {renderCaseTableColGroup()}
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Resident name</th>
                  <th>Age</th>
                  <th>Living alone?</th>
                  <th>Fall risk?</th>
                  <th>Emergency type</th>
                  <th>Distress level</th>
                  <th>Confidence (0-1)</th>
                  <th>Recommended action</th>
                </tr>
              </thead>
              <tbody>
                {pendingAIAssessmentCases.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="empty-row">
                      No pending AI-assessment cases.
                    </td>
                  </tr>
                ) : (
                  pendingAIAssessmentCases.map((item) => {
                    const profile = profilesById.get(item.profile_id);
                    const unitInfo = profile?.unit_patient_information;
                    const isExpanded = expandedCaseId === item.case_id;

                    return (
                      <Fragment key={item.case_id}>
                        <tr
                          className={`case-row ${isExpanded ? "case-row-expanded" : ""}`}
                          onClick={() => toggleCaseExpansion(item.case_id)}
                        >
                          <td>{new Date(item.created_at).toLocaleString()}</td>
                          <td>{displayValue(unitInfo?.resident_name)}</td>
                          <td>{displayValue(unitInfo?.age)}</td>
                          <td>{displayLivingAlone(unitInfo?.living_alone_flag)}</td>
                          <td>{displayLivingAlone(profile?.medical_history.fall_risk_flag)}</td>
                          <td>{displayValue(item.emergency_type)}</td>
                          <td>{displayValue(item.distress_level)}</td>
                          <td>{displayValue(item.confidence)}</td>
                          <td>{displayValue(item.recommended_action)}</td>
                        </tr>
                        {isExpanded ? (
                          <tr className="expanded-row">
                            <td colSpan={9}>
                              <div className="expanded-grid">
                                {renderFeatureBreakdown(item)}
                                <div className="operator-action-section">
                                  {renderOperatorActionButtons(item.case_id)}
                                </div>
                              </div>
                            </td>
                          </tr>
                        ) : null}
                      </Fragment>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          <h2 className="section-title table-subtitle">Operator Processed</h2>
          <div className="table-wrap">
            <table className="cases-table">
              {renderCaseTableColGroup()}
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Resident name</th>
                  <th>Age</th>
                  <th>Living alone?</th>
                  <th>Fall risk?</th>
                  <th>Emergency type</th>
                  <th>Distress level</th>
                  <th>Confidence (0-1)</th>
                  <th>Chosen action</th>
                </tr>
              </thead>
              <tbody>
                {operatorProcessedCases.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="empty-row">
                      No operator processed cases.
                    </td>
                  </tr>
                ) : (
                  operatorProcessedCases.map((item) => {
                    const profile = profilesById.get(item.profile_id);
                    const unitInfo = profile?.unit_patient_information;
                    const isExpanded = expandedCaseId === item.case_id;

                    return (
                      <Fragment key={item.case_id}>
                        <tr
                          className={`case-row ${isExpanded ? "case-row-expanded" : ""}`}
                          onClick={() => toggleCaseExpansion(item.case_id)}
                        >
                          <td>{new Date(item.created_at).toLocaleString()}</td>
                          <td>{displayValue(unitInfo?.resident_name)}</td>
                          <td>{displayValue(unitInfo?.age)}</td>
                          <td>{displayLivingAlone(unitInfo?.living_alone_flag)}</td>
                          <td>{displayLivingAlone(profile?.medical_history.fall_risk_flag)}</td>
                          <td>{displayValue(item.emergency_type)}</td>
                          <td>{displayValue(item.distress_level)}</td>
                          <td>{displayValue(item.confidence)}</td>
                          <td>{displayValue(item.operator_action)}</td>
                        </tr>
                        {isExpanded ? (
                          <tr className="expanded-row">
                            <td colSpan={9}>
                              <div className="expanded-grid">
                                {renderFeatureBreakdown(item)}
                                <div className="operator-action-section">
                                  <strong>Chosen Action</strong>
                                  <div>{displayValue(item.operator_action)}</div>
                                  {renderActualSeverityButtons(item)}
                                </div>
                              </div>
                            </td>
                          </tr>
                        ) : null}
                      </Fragment>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  );
}
