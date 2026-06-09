import { useState } from "react";
import axios from "axios";
import { Button } from "@/commons/components/ui/button";
import { Card } from "@/commons/components/ui/card";
import { Input } from "@/commons/components/ui/input";
import { Textarea } from "@/commons/components/ui/textarea";
import { Badge } from "@/commons/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/commons/components/ui/tabs";
import axiosInstance from "@/commons/utils/axiosInstance";
import { Copy, Loader2, WandSparkles } from "lucide-react";
import {
  DEBUG_EXTRACTION_CASES,
  DEFAULT_DEBUG_EXTRACTION_CASE,
  type DebugExtractionCase,
} from "./documentGenerationCases";

type InputMode = "json" | "session";
type ExtractionProvider = "gemini" | "openai" | "anthropic_api";

const PROVIDER_DEFAULT_MODELS: Record<ExtractionProvider, string> = {
  gemini: "",
  openai: "",
  anthropic_api: "claude-haiku-4-5-20251001",
};

type DebugClinicalExtractionResponse = {
  session_id: string;
  chunks: Array<{
    chunk_id: string;
    section_index: number;
    speaker: string | null;
    text: string;
  }>;
  raw_mentions: Record<string, unknown> | null;
  processed_mentions: Record<string, unknown> | null;
  evidence: Array<{
    fact_path: string;
    quote: string;
    turn_id?: string | null;
    matched: boolean;
    match_score: number | null;
    ambiguous: boolean;
    speaker_mismatch: boolean;
  }>;
  grounding_stats: Record<string, unknown>;
  extraction_model: string | null;
  latency_ms: number | null;
  status: string;
  error_code?: string | null;
};

type SessionTranscriptResponse = {
  session_id: string;
  encounter_id: number;
  document_id: number;
  doctor_id: number;
  status: string;
  transcript_json: Record<string, unknown>;
};

function JsonPanel({ value }: { value: unknown }) {
  const text = JSON.stringify(value, null, 2);

  return (
    <div className="relative">
      <Button
        type="button"
        size="sm"
        variant="outline"
        className="absolute right-2 top-2"
        onClick={() => void navigator.clipboard.writeText(text)}
      >
        <Copy className="mr-1 h-3 w-3" />
        Copiar
      </Button>
      <pre className="max-h-[28rem] overflow-auto rounded-md border bg-slate-950 p-4 text-xs text-slate-100">
        {text}
      </pre>
    </div>
  );
}

function applyDebugCase(
  debugCase: DebugExtractionCase,
): {
  transcriptText: string;
  language: string;
  patientName: string;
  selectedCaseIndex: number;
} {
  return {
    transcriptText: JSON.stringify(debugCase.transcriptJson, null, 2),
    language: debugCase.language,
    patientName: debugCase.patientName,
    selectedCaseIndex: debugCase.index,
  };
}

const initialCaseState = applyDebugCase(DEFAULT_DEBUG_EXTRACTION_CASE);

export default function DebugClinicalExtractionPage() {
  const [inputMode, setInputMode] = useState<InputMode>("json");
  const [transcriptText, setTranscriptText] = useState(
    initialCaseState.transcriptText,
  );
  const [sessionId, setSessionId] = useState("");
  const [language, setLanguage] = useState(initialCaseState.language);
  const [provider, setProvider] = useState<ExtractionProvider>("gemini");
  const [model, setModel] = useState("");
  const [patientName, setPatientName] = useState(initialCaseState.patientName);
  const [encounterId, setEncounterId] = useState("1");
  const [documentId, setDocumentId] = useState("1");
  const [doctorId, setDoctorId] = useState("1");
  const [selectedCaseIndex, setSelectedCaseIndex] = useState(
    initialCaseState.selectedCaseIndex,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DebugClinicalExtractionResponse | null>(null);
  const [loadedSession, setLoadedSession] = useState<SessionTranscriptResponse | null>(
    null,
  );

  const activeCase =
    DEBUG_EXTRACTION_CASES.find((debugCase) => debugCase.index === selectedCaseIndex) ??
    null;

  const loadDebugCase = (debugCase: DebugExtractionCase) => {
    const next = applyDebugCase(debugCase);
    setTranscriptText(next.transcriptText);
    setLanguage(next.language);
    setPatientName(next.patientName);
    setSelectedCaseIndex(next.selectedCaseIndex);
    setError(null);
    setResult(null);
  };

  const loadSessionTranscript = async () => {
    if (!sessionId.trim()) {
      setError("Ingresa un session_id");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const response = await axiosInstance.get<SessionTranscriptResponse>(
        `/api/v1/clinical-extraction/debug/sessions/${encodeURIComponent(sessionId.trim())}/transcript`,
      );
      setLoadedSession(response.data);
      setTranscriptText(JSON.stringify(response.data.transcript_json, null, 2));
      setSelectedCaseIndex(0);
    } catch (loadError) {
      if (axios.isAxiosError(loadError)) {
        setError(loadError.response?.data?.detail ?? loadError.message);
      } else {
        setError("No se pudo cargar la sesión");
      }
    } finally {
      setBusy(false);
    }
  };

  const runExtraction = async () => {
    setBusy(true);
    setError(null);
    setResult(null);

    try {
      const body: Record<string, unknown> = {
        language: language.trim() || null,
        provider: provider.trim() || null,
        model: model.trim() || null,
      };

      if (inputMode === "session") {
        if (!sessionId.trim()) {
          setError("Ingresa un session_id");
          return;
        }
        body.session_id = sessionId.trim();
      } else {
        let transcriptJson: Record<string, unknown>;
        try {
          transcriptJson = JSON.parse(transcriptText) as Record<string, unknown>;
        } catch {
          setError("transcript_json inválido");
          return;
        }
        body.transcript_json = transcriptJson;
        body.context = {
          encounter_id: Number(encounterId) || 0,
          document_id: Number(documentId) || 0,
          doctor_id: Number(doctorId) || 0,
          patient_name: patientName.trim() || null,
        };
      }

      const response = await axiosInstance.post<DebugClinicalExtractionResponse>(
        "/api/v1/clinical-extraction/debug/extract",
        body,
      );
      setResult(response.data);
    } catch (extractError) {
      if (axios.isAxiosError(extractError)) {
        const detail = extractError.response?.data?.detail;
        setError(
          typeof detail === "string"
            ? detail
            : JSON.stringify(detail ?? extractError.message),
        );
      } else {
        setError("La extracción falló");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-6 py-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">
          Debug de extracción clínica
        </h1>
        <p className="max-w-3xl text-sm text-slate-600">
          Prueba el extractor shadow de proposiciones clínicas atómicas con
          transcript JSON manual o una sesión consolidada. Requiere backend local y
          clinical extraction worker en el puerto 8093.
        </p>
      </div>

      <Card className="p-4">
        <Tabs
          value={inputMode}
          onValueChange={(value) => setInputMode(value as InputMode)}
        >
          <TabsList>
            <TabsTrigger value="json">JSON manual</TabsTrigger>
            <TabsTrigger value="session">Session ID</TabsTrigger>
          </TabsList>

          <TabsContent value="json" className="mt-4 space-y-4">
            <div className="space-y-2">
              <p className="text-xs font-medium text-slate-600">
                Casos desde evals/document_generation/cases.json
              </p>
              <div className="flex flex-wrap gap-2">
                {DEBUG_EXTRACTION_CASES.map((debugCase) => (
                  <Button
                    key={debugCase.id}
                    type="button"
                    variant={
                      selectedCaseIndex === debugCase.index ? "default" : "outline"
                    }
                    size="sm"
                    className="min-w-9"
                    onClick={() => loadDebugCase(debugCase)}
                  >
                    {debugCase.index}
                  </Button>
                ))}
              </div>
              {activeCase ? (
                <div className="space-y-1 rounded-md border bg-slate-50 p-3 text-xs text-slate-700">
                  <p className="font-medium">{activeCase.id}</p>
                  <p>{activeCase.context}</p>
                  {activeCase.notes ? (
                    <p className="text-slate-500">{activeCase.notes}</p>
                  ) : null}
                </div>
              ) : null}
            </div>
            <Textarea
              value={transcriptText}
              onChange={(event) => {
                setTranscriptText(event.target.value);
                setSelectedCaseIndex(0);
              }}
              className="min-h-[16rem] font-mono text-xs"
              placeholder="transcript_json"
            />
            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <label className="text-xs font-medium text-slate-600">
                  Patient name (metadata)
                </label>
                <Input value={patientName} onChange={(e) => setPatientName(e.target.value)} />
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label className="text-xs font-medium text-slate-600">Encounter</label>
                  <Input value={encounterId} onChange={(e) => setEncounterId(e.target.value)} />
                </div>
                <div>
                  <label className="text-xs font-medium text-slate-600">Document</label>
                  <Input value={documentId} onChange={(e) => setDocumentId(e.target.value)} />
                </div>
                <div>
                  <label className="text-xs font-medium text-slate-600">Doctor</label>
                  <Input value={doctorId} onChange={(e) => setDoctorId(e.target.value)} />
                </div>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="session" className="mt-4 space-y-4">
            <div className="flex flex-wrap items-end gap-2">
              <div className="min-w-[20rem] flex-1">
                <label className="text-xs font-medium text-slate-600">session_id</label>
                <Input
                  value={sessionId}
                  onChange={(event) => setSessionId(event.target.value)}
                  placeholder="sess-..."
                />
              </div>
              <Button
                type="button"
                variant="outline"
                disabled={busy}
                onClick={() => void loadSessionTranscript()}
              >
                Cargar transcript
              </Button>
            </div>
            {loadedSession ? (
              <div className="flex flex-wrap gap-2 text-xs text-slate-600">
                <Badge variant="outline">status: {loadedSession.status}</Badge>
                <Badge variant="outline">encounter: {loadedSession.encounter_id}</Badge>
                <Badge variant="outline">document: {loadedSession.document_id}</Badge>
              </div>
            ) : null}
            <Textarea
              value={transcriptText}
              onChange={(event) => setTranscriptText(event.target.value)}
              className="min-h-[12rem] font-mono text-xs"
              readOnly={inputMode === "session"}
            />
          </TabsContent>
        </Tabs>

        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <div>
            <label className="text-xs font-medium text-slate-600">language</label>
            <Input value={language} onChange={(event) => setLanguage(event.target.value)} />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-600">provider</label>
            <select
              value={provider}
              onChange={(event) => {
                const nextProvider = event.target.value as ExtractionProvider;
                setProvider(nextProvider);
                if (!model.trim()) {
                  setModel(PROVIDER_DEFAULT_MODELS[nextProvider]);
                }
              }}
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm"
            >
              <option value="gemini">gemini</option>
              <option value="openai">openai</option>
              <option value="anthropic_api">anthropic_api</option>
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-slate-600">model override</label>
            <Input
              value={model}
              onChange={(event) => setModel(event.target.value)}
              placeholder={PROVIDER_DEFAULT_MODELS[provider] || "opcional"}
            />
          </div>
        </div>

        <div className="mt-4">
          <Button type="button" disabled={busy} onClick={() => void runExtraction()}>
            {busy ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <WandSparkles className="mr-2 h-4 w-4" />
            )}
            Extraer
          </Button>
        </div>
      </Card>

      {error ? (
        <Card className="border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</Card>
      ) : null}

      {result ? (
        <Card className="p-4">
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <Badge>{result.status}</Badge>
            {result.extraction_model ? (
              <Badge variant="outline">{result.extraction_model}</Badge>
            ) : null}
            {result.latency_ms != null ? (
              <Badge variant="outline">{result.latency_ms} ms</Badge>
            ) : null}
            {result.error_code ? (
              <Badge variant="destructive">{result.error_code}</Badge>
            ) : null}
          </div>

          <Tabs defaultValue="processed">
            <TabsList>
              <TabsTrigger value="chunks">Chunks</TabsTrigger>
              <TabsTrigger value="raw">Raw mentions</TabsTrigger>
              <TabsTrigger value="processed">Processed mentions</TabsTrigger>
              <TabsTrigger value="evidence">Evidence</TabsTrigger>
              <TabsTrigger value="stats">Stats</TabsTrigger>
            </TabsList>
            <TabsContent value="chunks" className="mt-4">
              <JsonPanel value={result.chunks} />
            </TabsContent>
            <TabsContent value="raw" className="mt-4">
              <JsonPanel value={result.raw_mentions} />
            </TabsContent>
            <TabsContent value="processed" className="mt-4">
              <JsonPanel value={result.processed_mentions} />
            </TabsContent>
            <TabsContent value="evidence" className="mt-4">
              <JsonPanel value={result.evidence} />
            </TabsContent>
            <TabsContent value="stats" className="mt-4">
              <JsonPanel value={result.grounding_stats} />
            </TabsContent>
          </Tabs>
        </Card>
      ) : null}
    </div>
  );
}
