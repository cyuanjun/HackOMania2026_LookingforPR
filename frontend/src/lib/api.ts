import {
  CaseIntakePayload,
  CaseOutcomePayload,
  CaseRecord,
  OperatorAction,
  ProfileRecord,
  TrainingRecord,
} from "@/types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

type ProfilesResponse = {
  data: {
    profiles: ProfileRecord[];
  };
};

type IntakeResponse = {
  data: {
    case: CaseRecord;
  };
};

type CasesResponse = {
  data: {
    cases: CaseRecord[];
  };
};

type TrainingRecordsResponse = {
  data: {
    training_records: TrainingRecord[];
  };
};

type CaseResponse = {
  data: {
    case: CaseRecord;
  };
};

export async function fetchProfiles(): Promise<ProfileRecord[]> {
  const response = await fetch(`${API_BASE_URL}/profiles`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Unable to fetch profiles.");
  }

  const json: ProfilesResponse = await response.json();
  return json.data.profiles;
}

export async function createCaseIntake(
  payload: CaseIntakePayload
): Promise<CaseRecord> {
  const response = await fetch(`${API_BASE_URL}/cases/intake`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Unable to create case intake.");
  }

  const json: IntakeResponse = await response.json();
  return json.data.case;
}

export async function fetchCases(): Promise<CaseRecord[]> {
  const response = await fetch(`${API_BASE_URL}/cases`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Unable to fetch cases.");
  }

  const json: CasesResponse = await response.json();
  return json.data.cases;
}

export async function processCase(caseId: string): Promise<CaseRecord> {
  const response = await fetch(`${API_BASE_URL}/cases/${caseId}/process`, {
    method: "POST"
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Unable to process case.");
  }

  const json: CaseResponse = await response.json();
  return json.data.case;
}

export async function setOperatorAction(
  caseId: string,
  action: OperatorAction
): Promise<CaseRecord> {
  const response = await fetch(`${API_BASE_URL}/cases/${caseId}/operator-action`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ action })
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Unable to set operator action.");
  }

  const json: CaseResponse = await response.json();
  return json.data.case;
}

export async function setCaseOutcome(
  caseId: string,
  payload: CaseOutcomePayload
): Promise<CaseRecord> {
  const response = await fetch(`${API_BASE_URL}/cases/${caseId}/outcome`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Unable to set case outcome.");
  }

  const json: CaseResponse = await response.json();
  return json.data.case;
}

export async function fetchTrainingRecords(): Promise<TrainingRecord[]> {
  const response = await fetch(`${API_BASE_URL}/cases/training-records`, {
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error("Unable to fetch training records.");
  }

  const json: TrainingRecordsResponse = await response.json();
  return json.data.training_records;
}
