"use client";

import { FormEvent, useState } from "react";

import { ResidentProfile } from "@/lib/types";

interface IntakePanelProps {
  residents: ResidentProfile[];
  residentsLoading: boolean;
  submitting: boolean;
  onSubmit: (profileId: string, audioFile: File) => Promise<void>;
}

export function IntakePanel({ residents, residentsLoading, submitting, onSubmit }: IntakePanelProps) {
  const [selectedResidentId, setSelectedResidentId] = useState<string>("");
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [error, setError] = useState<string>("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (!selectedResidentId) {
      setError("Please choose a resident profile.");
      return;
    }
    if (!audioFile) {
      setError("Please upload a prerecorded audio file.");
      return;
    }
    try {
      await onSubmit(selectedResidentId, audioFile);
      setAudioFile(null);
      const input = event.currentTarget.elements.namedItem("audioFile") as HTMLInputElement | null;
      if (input) {
        input.value = "";
      }
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Failed to create intake case.");
    }
  }

  return (
    <aside className="rounded-2xl border border-slate-200 bg-panel p-5 shadow-panel">
      <h2 className="text-xl font-semibold text-ink">Create Intake Case</h2>
      <p className="mt-1 text-sm text-slate-600">
        Upload a prerecorded alert clip and associate it with a resident profile.
      </p>

      <form className="mt-4 space-y-4" onSubmit={handleSubmit}>
        <label className="block">
          <span className="mb-2 block text-sm font-semibold text-slate-700">Resident Profile</span>
          <select
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 focus:border-accent focus:outline-none"
            value={selectedResidentId}
            onChange={(event) => setSelectedResidentId(event.target.value)}
            disabled={submitting}
          >
            <option value="">
              {residentsLoading && residents.length === 0 ? "Loading profiles..." : "Select resident"}
            </option>
            {residents.map((resident) => (
              <option key={resident.profile_id} value={resident.profile_id}>
                {resident.name} ({resident.block} {resident.unit})
              </option>
            ))}
          </select>
          {!residentsLoading && residents.length === 0 ? (
            <p className="mt-2 text-xs text-amber-700">
              No resident profiles loaded. Check that backend is running and `NEXT_PUBLIC_API_BASE_URL` points to it.
            </p>
          ) : null}
        </label>

        <label className="block">
          <span className="mb-2 block text-sm font-semibold text-slate-700">Audio File (.wav, .mp3, .m4a)</span>
          <input
            id="audioFile"
            name="audioFile"
            type="file"
            accept="audio/*"
            className="block w-full cursor-pointer rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-slate-700 hover:file:bg-slate-200"
            onChange={(event) => setAudioFile(event.target.files?.[0] ?? null)}
            disabled={submitting}
          />
        </label>

        {error ? <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p> : null}

        <button
          type="submit"
          className="w-full rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-white hover:bg-teal-700 disabled:cursor-not-allowed disabled:opacity-60"
          disabled={submitting || residents.length === 0}
        >
          {submitting ? "Creating..." : "Create Intake Case"}
        </button>
      </form>
    </aside>
  );
}
