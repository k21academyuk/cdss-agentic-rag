import React from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Grid,
  LinearProgress,
  MenuItem,
  Stack,
  Step,
  StepLabel,
  Stepper,
  TextField,
  Typography,
} from "@mui/material";
import {
  AutoFixHigh,
  CloudUpload,
  Delete,
  Description,
  DoneAll,
  Replay,
  UploadFile,
} from "@mui/icons-material";
import { PageContainer, PageHeader } from "@/components/ui";
import { clinicalApi } from "@/lib/api-client";
import type {
  ApiError,
  DocumentGroundedPreviewResponse,
  DocumentIngestionStatusResponse,
  DocumentSearchVerificationResponse,
} from "@/lib/types";
import { alpha as alphaUtil, borderRadius, componentShadows, semantic, severity, spacing } from "@/theme";

type PipelineStage = "queued" | "uploading" | "parsing" | "indexing" | "completed" | "error";

interface PipelineFile {
  id: string;
  file?: File;
  fileName: string;
  fileSize: number;
  requestedDocumentType: IngestionDocumentType;
  patientId?: string;
  stage: PipelineStage;
  progress: number;
  message?: string;
  documentId?: string;
  updatedAt: string;
}

interface StoredPipelineFile {
  id: string;
  fileName: string;
  fileSize: number;
  requestedDocumentType: IngestionDocumentType;
  patientId?: string;
  stage: PipelineStage;
  progress: number;
  message?: string;
  documentId?: string;
  updatedAt: string;
}

type IngestionDocumentType = "patient_record" | "protocol" | "literature";

const POLL_INTERVAL_MS = 1200;
const MAX_POLL_ATTEMPTS = 120;
const STAGE_ORDER: PipelineStage[] = ["queued", "uploading", "parsing", "indexing", "completed"];
const ALL_STAGES: PipelineStage[] = [...STAGE_ORDER, "error"];
const STORAGE_KEY = "cdss.documents.pipeline.v1";
const MAX_STORED_ITEMS = 50;
const DEFAULT_PATIENT_ID = "patient_12345";
const DOCUMENT_TYPE_LABELS: Record<IngestionDocumentType, string> = {
  patient_record: "Patient Record (Query/Patients)",
  protocol: "Protocol (Guideline Search)",
  literature: "Literature (Evidence Search)",
};

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function clampProgress(value?: number): number {
  if (typeof value !== "number" || Number.isNaN(value)) return 0;
  return Math.max(0, Math.min(100, value));
}

function normalizeStage(value: unknown): PipelineStage {
  if (typeof value === "string" && ALL_STAGES.includes(value as PipelineStage)) {
    return value as PipelineStage;
  }
  return "queued";
}

function loadPipelineHistory(): PipelineFile[] {
  if (typeof window === "undefined") return [];

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];

    return parsed
      .slice(-MAX_STORED_ITEMS)
      .flatMap((item: unknown) => {
        if (!item || typeof item !== "object") return [];
        const record = item as Partial<StoredPipelineFile>;
        if (!record.id || !record.fileName || typeof record.fileSize !== "number") return [];

        const requestedDocumentType =
          record.requestedDocumentType === "protocol" ||
          record.requestedDocumentType === "literature" ||
          record.requestedDocumentType === "patient_record"
            ? record.requestedDocumentType
            : "patient_record";

        return [
          {
            id: record.id,
            fileName: record.fileName,
            fileSize: Math.max(0, record.fileSize),
            requestedDocumentType,
            patientId: record.patientId,
            stage: normalizeStage(record.stage),
            progress: clampProgress(record.progress),
            message: record.message,
            documentId: record.documentId,
            updatedAt: record.updatedAt || new Date().toISOString(),
          },
        ];
      });
  } catch {
    return [];
  }
}

function persistPipelineHistory(files: PipelineFile[]): void {
  if (typeof window === "undefined") return;

  const serializable: StoredPipelineFile[] = files.slice(-MAX_STORED_ITEMS).map((entry) => ({
    id: entry.id,
    fileName: entry.fileName,
    fileSize: entry.fileSize,
    requestedDocumentType: entry.requestedDocumentType,
    patientId: entry.patientId,
    stage: entry.stage,
    progress: clampProgress(entry.progress),
    message: entry.message,
    documentId: entry.documentId,
    updatedAt: entry.updatedAt,
  }));
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(serializable));
}

function mapStatusToStage(payload: DocumentIngestionStatusResponse): { stage: PipelineStage; progress: number } {
  const status = payload.status;
  const progress = clampProgress(payload.progress);

  if (status === "completed") {
    return { stage: "completed", progress: 100 };
  }
  if (status === "failed" || status === "error" || status === "not_found") {
    return { stage: "error", progress: Math.max(progress, 100) };
  }
  if (status === "queued" || status === "pending") {
    return { stage: "queued", progress: Math.max(0, Math.min(progress, 10)) };
  }
  if (progress < 30) {
    return { stage: "uploading", progress: Math.max(progress, 12) };
  }
  if (progress < 70) {
    return { stage: "parsing", progress };
  }
  return { stage: "indexing", progress };
}

function statusMessage(payload: DocumentIngestionStatusResponse, stage: PipelineStage): string {
  if (payload.error) return payload.error;
  if (payload.message) return payload.message;
  if (stage === "queued") return "Document queued for background processing.";
  if (stage === "uploading") return "Uploading payload and scheduling ingestion.";
  if (stage === "parsing") return "Extracting and parsing clinical document content.";
  if (stage === "indexing") return "Generating embeddings and indexing retrieval chunks.";
  if (stage === "completed") return "Document indexed and available for search.";
  return "Document ingestion failed.";
}

function stageColor(stage: PipelineStage): string {
  if (stage === "completed") return semantic.success.main;
  if (stage === "error") return severity.major.main;
  if (stage === "indexing") return semantic.info.main;
  if (stage === "parsing") return semantic.warning.main;
  if (stage === "uploading") return semantic.info.main;
  return "#6B7280";
}

function stageLabel(stage: PipelineStage): string {
  if (stage === "queued") return "Queued";
  if (stage === "uploading") return "Uploading";
  if (stage === "parsing") return "Parsing";
  if (stage === "indexing") return "Indexing";
  if (stage === "completed") return "Completed";
  return "Error";
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export default function DocumentUploadPage() {
  const [pipelineFiles, setPipelineFiles] = React.useState<PipelineFile[]>(() => loadPipelineHistory());
  const [dragActive, setDragActive] = React.useState(false);
  const [selectedDocumentType, setSelectedDocumentType] = React.useState<IngestionDocumentType>("patient_record");
  const [patientIdInput, setPatientIdInput] = React.useState(DEFAULT_PATIENT_ID);
  const [verificationPhraseById, setVerificationPhraseById] = React.useState<Record<string, string>>({});
  const [verificationResultById, setVerificationResultById] = React.useState<Record<string, DocumentSearchVerificationResponse>>(
    {}
  );
  const [verificationErrorById, setVerificationErrorById] = React.useState<Record<string, string>>({});
  const [verifyingById, setVerifyingById] = React.useState<Record<string, boolean>>({});
  const [groundedQuestionById, setGroundedQuestionById] = React.useState<Record<string, string>>({});
  const [groundedResultById, setGroundedResultById] = React.useState<Record<string, DocumentGroundedPreviewResponse>>({});
  const [groundedErrorById, setGroundedErrorById] = React.useState<Record<string, string>>({});
  const [groundingById, setGroundingById] = React.useState<Record<string, boolean>>({});
  const [deletingById, setDeletingById] = React.useState<Record<string, boolean>>({});
  const isMountedRef = React.useRef(true);

  React.useEffect(() => {
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  React.useEffect(() => {
    persistPipelineHistory(pipelineFiles);
  }, [pipelineFiles]);

  const addFiles = (incoming: File[]) => {
    if (incoming.length === 0) return;
    setPipelineFiles((prev) => {
      const typedPatientId = selectedDocumentType === "patient_record" ? patientIdInput.trim() : "";
      const existing = new Set(
        prev.map(
          (entry) =>
            `${entry.fileName}:${entry.fileSize}:${entry.requestedDocumentType}:${(entry.patientId || "").trim()}`
        )
      );
      const additions = incoming
        .filter(
          (file) =>
            !existing.has(`${file.name}:${file.size}:${selectedDocumentType}:${typedPatientId}`)
        )
        .map((file) => ({
          id: `${file.name}-${file.size}-${crypto.randomUUID()}`,
          file,
          fileName: file.name,
          fileSize: file.size,
          requestedDocumentType: selectedDocumentType,
          patientId: typedPatientId || undefined,
          stage: "queued" as PipelineStage,
          progress: 0,
          updatedAt: new Date().toISOString(),
        }));
      return [...prev, ...additions].slice(-MAX_STORED_ITEMS);
    });
  };

  const updateFile = (fileId: string, updates: Partial<PipelineFile>) => {
    setPipelineFiles((prev) =>
      prev.map((entry) =>
        entry.id === fileId
          ? {
              ...entry,
              ...updates,
              updatedAt: updates.updatedAt || new Date().toISOString(),
            }
          : entry
      )
    );
  };

  const removeFile = (fileId: string) => {
    setPipelineFiles((prev) => prev.filter((entry) => entry.id !== fileId));
    setVerificationPhraseById((prev) => {
      const next = { ...prev };
      delete next[fileId];
      return next;
    });
    setVerificationResultById((prev) => {
      const next = { ...prev };
      delete next[fileId];
      return next;
    });
    setVerificationErrorById((prev) => {
      const next = { ...prev };
      delete next[fileId];
      return next;
    });
    setVerifyingById((prev) => {
      const next = { ...prev };
      delete next[fileId];
      return next;
    });
    setGroundedQuestionById((prev) => {
      const next = { ...prev };
      delete next[fileId];
      return next;
    });
    setGroundedResultById((prev) => {
      const next = { ...prev };
      delete next[fileId];
      return next;
    });
    setGroundedErrorById((prev) => {
      const next = { ...prev };
      delete next[fileId];
      return next;
    });
    setGroundingById((prev) => {
      const next = { ...prev };
      delete next[fileId];
      return next;
    });
    setDeletingById((prev) => {
      const next = { ...prev };
      delete next[fileId];
      return next;
    });
  };

  const deleteDocument = async (entry: PipelineFile) => {
    if (!entry.documentId) {
      removeFile(entry.id);
      return;
    }

    const shouldDelete = window.confirm(
      "Delete this ingested document from backend indexes and remove it from this dashboard?"
    );
    if (!shouldDelete) return;

    setDeletingById((prev) => ({ ...prev, [entry.id]: true }));
    setVerificationErrorById((prev) => {
      const next = { ...prev };
      delete next[entry.id];
      return next;
    });

    try {
      await clinicalApi.deleteDocument(entry.documentId);
      removeFile(entry.id);
    } catch (error) {
      const apiError = error as ApiError;
      const message = apiError.message || "Failed to delete ingested document from backend.";
      setVerificationErrorById((prev) => ({ ...prev, [entry.id]: message }));
      updateFile(entry.id, {
        message,
      });
    } finally {
      setDeletingById((prev) => {
        const next = { ...prev };
        delete next[entry.id];
        return next;
      });
    }
  };

  const pollDocumentStatus = async (fileId: string, documentId: string): Promise<void> => {
    for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt += 1) {
      if (!isMountedRef.current) return;
      try {
        const statusPayload = await clinicalApi.getDocumentIngestionStatus(documentId);
        const { stage, progress } = mapStatusToStage(statusPayload);
        updateFile(fileId, {
          stage,
          progress,
          message: statusMessage(statusPayload, stage),
          ...(stage === "completed" ? { file: undefined } : {}),
        });

        if (stage === "completed" || stage === "error") {
          return;
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to poll document status.";
        if (attempt >= 2) {
          updateFile(fileId, {
            stage: "error",
            progress: 100,
            message,
          });
          return;
        }
      }
      await wait(POLL_INTERVAL_MS);
    }

    updateFile(fileId, {
      stage: "error",
      progress: 100,
      message: "Timed out while polling ingestion status.",
    });
  };

  const runPipeline = async (entry: PipelineFile) => {
    if (!entry.file) {
      updateFile(entry.id, {
        stage: "error",
        progress: 100,
        message: "Original file is unavailable. Re-upload the document to retry ingestion.",
      });
      return;
    }

    updateFile(entry.id, {
      stage: "uploading",
      progress: 6,
      message: "Submitting document for ingestion.",
    });

    try {
      const metadata =
        entry.requestedDocumentType === "protocol"
          ? {
              guideline_name: entry.fileName,
              guideline: entry.fileName,
              specialty: "general",
              version: "1.0",
            }
          : undefined;

      const response = await clinicalApi.ingestDocument(
        entry.file,
        entry.requestedDocumentType,
        metadata,
        entry.patientId
      );
      if (!response.document_id) {
        throw new Error("Missing document_id from ingestion response.");
      }

      updateFile(entry.id, {
        stage: "queued",
        progress: 10,
        documentId: response.document_id,
        message: response.message || "Document queued for processing.",
      });

      await pollDocumentStatus(entry.id, response.document_id);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unexpected ingestion error";
      updateFile(entry.id, {
        stage: "error",
        progress: 100,
        message,
      });
    }
  };

  const runAllQueued = async () => {
    const queued = pipelineFiles.filter(
      (entry) => (entry.stage === "queued" || entry.stage === "error") && Boolean(entry.file)
    );
    for (const entry of queued) {
      await runPipeline(entry);
    }
  };

  const retryFile = async (fileId: string) => {
    const entry = pipelineFiles.find((item) => item.id === fileId);
    if (!entry) return;
    if (!entry.file) {
      updateFile(fileId, {
        stage: "error",
        progress: 100,
        message: "Original file is unavailable. Re-upload the document to retry ingestion.",
      });
      return;
    }
    const resetEntry: PipelineFile = {
      ...entry,
      stage: "queued",
      progress: 0,
      message: undefined,
      documentId: undefined,
    };
    updateFile(fileId, resetEntry);
    await runPipeline(resetEntry);
  };

  const verifyIndexedDocument = async (entry: PipelineFile) => {
    if (!entry.documentId) return;

    setVerifyingById((prev) => ({ ...prev, [entry.id]: true }));
    setVerificationErrorById((prev) => ({ ...prev, [entry.id]: "" }));

    try {
      const phrase = (verificationPhraseById[entry.id] || "").trim();
      const verification = await clinicalApi.verifyDocumentInSearch(entry.documentId, {
        phrase: phrase.length > 0 ? phrase : undefined,
        top: 5,
      });
      setVerificationResultById((prev) => ({ ...prev, [entry.id]: verification }));
    } catch (error) {
      const apiError = error as ApiError | undefined;
      const detail = apiError?.details as { detail?: unknown } | undefined;
      const message =
        (typeof detail?.detail === "string" && detail.detail) ||
        apiError?.message ||
        "Document verification failed.";
      setVerificationErrorById((prev) => ({ ...prev, [entry.id]: message }));
    } finally {
      setVerifyingById((prev) => ({ ...prev, [entry.id]: false }));
    }
  };

  const generateGroundedPreview = async (entry: PipelineFile) => {
    if (!entry.documentId) return;

    const question = (groundedQuestionById[entry.id] || "").trim();
    if (!question) {
      setGroundedErrorById((prev) => ({ ...prev, [entry.id]: "Enter a question to generate grounded answer preview." }));
      return;
    }

    setGroundingById((prev) => ({ ...prev, [entry.id]: true }));
    setGroundedErrorById((prev) => ({ ...prev, [entry.id]: "" }));

    try {
      const result = await clinicalApi.generateDocumentGroundedPreview(entry.documentId, {
        question,
        top: 8,
        timeout_seconds: 25,
        max_tokens: 700,
        use_cache: true,
      });
      setGroundedResultById((prev) => ({ ...prev, [entry.id]: result }));
    } catch (error) {
      const apiError = error as ApiError | undefined;
      const detail = apiError?.details as { detail?: unknown } | undefined;
      const message =
        (typeof detail?.detail === "string" && detail.detail) ||
        apiError?.message ||
        "Grounded preview generation failed.";
      setGroundedErrorById((prev) => ({ ...prev, [entry.id]: message }));
    } finally {
      setGroundingById((prev) => ({ ...prev, [entry.id]: false }));
    }
  };

  const completedCount = pipelineFiles.filter((entry) => entry.stage === "completed").length;
  const errorCount = pipelineFiles.filter((entry) => entry.stage === "error").length;
  const inFlightCount = pipelineFiles.filter(
    (entry) => entry.stage === "uploading" || entry.stage === "parsing" || entry.stage === "indexing"
  ).length;

  return (
    <PageContainer>
      <PageHeader
        title="Documents Ingestion Pipeline"
        subtitle="Upload, parse, and index clinical documents with timeline visibility, backend status polling, and retry controls."
      />

      <Grid container spacing={2}>
        <Grid item xs={12} lg={4}>
          <Card sx={{ borderRadius: borderRadius.md, boxShadow: componentShadows.card, height: "100%" }}>
            <CardContent sx={{ p: spacing[3], height: "100%" }}>
              <Stack spacing={2} sx={{ height: "100%" }}>
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                  Upload Queue
                </Typography>

                <TextField
                  select
                  size="small"
                  label="Document Type"
                  value={selectedDocumentType}
                  onChange={(event) => setSelectedDocumentType(event.target.value as IngestionDocumentType)}
                  helperText="Controls which workspace/index this upload targets."
                >
                  {Object.entries(DOCUMENT_TYPE_LABELS).map(([value, label]) => (
                    <MenuItem key={value} value={value}>
                      {label}
                    </MenuItem>
                  ))}
                </TextField>

                {selectedDocumentType === "patient_record" && (
                  <TextField
                    size="small"
                    label="Patient ID (optional)"
                    value={patientIdInput}
                    onChange={(event) => setPatientIdInput(event.target.value)}
                    placeholder="patient_12345"
                    helperText="Attach patient records to a specific patient context."
                  />
                )}

                <Box
                  onDragOver={(event) => {
                    event.preventDefault();
                    setDragActive(true);
                  }}
                  onDragLeave={() => setDragActive(false)}
                  onDrop={(event) => {
                    event.preventDefault();
                    setDragActive(false);
                    addFiles(Array.from(event.dataTransfer.files));
                  }}
                  sx={{
                    p: spacing[4],
                    borderRadius: borderRadius.md,
                    border: `2px dashed ${dragActive ? semantic.info.main : alphaUtil(semantic.info.main, 0.35)}`,
                    bgcolor: dragActive ? alphaUtil(semantic.info.main, 0.08) : alphaUtil(semantic.info.main, 0.03),
                    textAlign: "center",
                  }}
                >
                  <CloudUpload sx={{ fontSize: 36, color: semantic.info.main, mb: 1 }} />
                  <Typography variant="subtitle2" sx={{ mb: 0.3 }}>
                    Drop files to ingest
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    PDF, DOCX, TXT
                  </Typography>

                  <Button variant="outlined" component="label" startIcon={<UploadFile />} sx={{ mt: 2 }}>
                    Select Files
                    <input
                      hidden
                      type="file"
                      multiple
                      accept=".pdf,.docx,.txt"
                      onChange={(event) => addFiles(Array.from(event.target.files ?? []))}
                    />
                  </Button>
                </Box>

                <Card sx={{ borderRadius: borderRadius.sm, boxShadow: "none", border: "1px solid", borderColor: "divider" }}>
                  <CardContent sx={{ p: spacing[2] }}>
                    <Stack spacing={1}>
                      <Typography variant="caption" color="text.secondary">
                        Pipeline status
                      </Typography>
                      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                        <Chip size="small" label={`${pipelineFiles.length} total`} />
                        <Chip size="small" label={`${completedCount} completed`} color="success" />
                        <Chip size="small" label={`${inFlightCount} processing`} color="info" />
                        <Chip size="small" label={`${errorCount} failed`} color={errorCount > 0 ? "error" : "default"} />
                      </Stack>
                    </Stack>
                  </CardContent>
                </Card>

                <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                  <Button
                    variant="contained"
                    startIcon={<AutoFixHigh />}
                    disabled={pipelineFiles.length === 0 || inFlightCount > 0}
                    onClick={runAllQueued}
                  >
                    Run Pipeline
                  </Button>
                  <Button
                    variant="text"
                    color="inherit"
                    disabled={pipelineFiles.length === 0 || inFlightCount > 0}
                    onClick={() => {
                      setPipelineFiles([]);
                      setVerificationPhraseById({});
                      setVerificationResultById({});
                      setVerificationErrorById({});
                      setVerifyingById({});
                      setGroundedQuestionById({});
                      setGroundedResultById({});
                      setGroundedErrorById({});
                      setGroundingById({});
                    }}
                  >
                    Clear Queue
                  </Button>
                </Stack>
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} lg={8}>
          <Stack spacing={1.5}>
            {pipelineFiles.length === 0 && (
              <Card sx={{ borderRadius: borderRadius.md, boxShadow: componentShadows.card }}>
                <CardContent sx={{ py: spacing[8], textAlign: "center" }}>
                  <Description sx={{ fontSize: 44, color: "text.disabled", mb: 1 }} />
                  <Typography variant="h6">No files in queue</Typography>
                  <Typography variant="body2" color="text.secondary">
                    Add documents to track backend ingestion states in real time.
                  </Typography>
                </CardContent>
              </Card>
            )}

            {pipelineFiles.map((entry) => {
              const activeStep = entry.stage === "error" ? 1 : Math.max(STAGE_ORDER.findIndex((item) => item === entry.stage), 0);
              const verification = verificationResultById[entry.id];
              const verificationError = verificationErrorById[entry.id];
              const isVerifying = verifyingById[entry.id] === true;
              const groundedResult = groundedResultById[entry.id];
              const groundedError = groundedErrorById[entry.id];
              const isGrounding = groundingById[entry.id] === true;
              const isDeleting = deletingById[entry.id] === true;
              const phraseValue = verificationPhraseById[entry.id] ?? "";
              const groundedQuestionValue = groundedQuestionById[entry.id] ?? "";
              const defaultPhrase =
                entry.requestedDocumentType === "protocol"
                  ? "guideline recommendation"
                  : entry.requestedDocumentType === "literature"
                    ? "trial outcome"
                    : "CKD Stage G3a-A2";
              const defaultGroundedQuestion =
                entry.requestedDocumentType === "protocol"
                  ? "What is the protocol recommendation and monitoring plan?"
                  : entry.requestedDocumentType === "literature"
                    ? "Summarize the key evidence and outcomes from this document."
                    : "Summarize this patient context and key clinical concerns.";

              return (
                <Card key={entry.id} sx={{ borderRadius: borderRadius.md, boxShadow: componentShadows.card }}>
                  <CardContent sx={{ p: spacing[3] }}>
                    <Grid container spacing={2}>
                      <Grid item xs={12} md={4}>
                        <Stack spacing={1}>
                          <Typography variant="subtitle2" sx={{ wordBreak: "break-word" }}>
                            {entry.fileName}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            {formatFileSize(entry.fileSize)}
                          </Typography>
                          <Chip
                            size="small"
                            label={DOCUMENT_TYPE_LABELS[entry.requestedDocumentType]}
                            sx={{
                              alignSelf: "flex-start",
                              bgcolor: alphaUtil(semantic.info.main, 0.1),
                              color: semantic.info.main,
                            }}
                          />
                          {entry.patientId && (
                            <Typography variant="caption" color="text.secondary">
                              Patient: {entry.patientId}
                            </Typography>
                          )}
                          <Chip
                            size="small"
                            label={stageLabel(entry.stage)}
                            sx={{
                              alignSelf: "flex-start",
                              color: stageColor(entry.stage),
                              bgcolor: alphaUtil(stageColor(entry.stage), 0.12),
                            }}
                          />
                          {entry.documentId && (
                            <Typography variant="caption" color="text.secondary">
                              ID: {entry.documentId}
                            </Typography>
                          )}
                        </Stack>
                      </Grid>

                      <Grid item xs={12} md={5}>
                        <Stack spacing={1}>
                          <LinearProgress
                            variant="determinate"
                            value={entry.progress}
                            sx={{
                              height: 8,
                              borderRadius: borderRadius.full,
                              "& .MuiLinearProgress-bar": {
                                borderRadius: borderRadius.full,
                              },
                            }}
                          />
                          <Typography variant="caption" color="text.secondary">
                            {entry.message || "Awaiting ingestion start."}
                          </Typography>

                          <Stepper activeStep={activeStep} alternativeLabel sx={{ mt: 0.6 }}>
                            <Step completed={entry.stage !== "queued"}>
                              <StepLabel>Upload</StepLabel>
                            </Step>
                            <Step completed={entry.stage === "indexing" || entry.stage === "completed"}>
                              <StepLabel>Parse</StepLabel>
                            </Step>
                            <Step completed={entry.stage === "completed"}>
                              <StepLabel>Index</StepLabel>
                            </Step>
                          </Stepper>
                        </Stack>
                      </Grid>

                      <Grid item xs={12} md={3}>
                        <Stack direction={{ xs: "row", md: "column" }} spacing={1} justifyContent="flex-end">
                          {entry.stage === "error" && (
                            <Button
                              size="small"
                              variant="outlined"
                              startIcon={<Replay />}
                              onClick={() => retryFile(entry.id)}
                              disabled={!entry.file}
                            >
                              Retry
                            </Button>
                          )}
                          {entry.stage === "completed" && (
                            <Button
                              size="small"
                              variant="outlined"
                              color="success"
                              startIcon={<DoneAll />}
                              disabled={isDeleting}
                            >
                              Ready
                            </Button>
                          )}
                          {entry.stage === "completed" && (
                            <Button
                              size="small"
                              variant="text"
                              color="error"
                              startIcon={<Delete />}
                              onClick={() => void deleteDocument(entry)}
                              disabled={isDeleting}
                            >
                              {isDeleting ? "Deleting..." : "Delete"}
                            </Button>
                          )}
                          {(entry.stage === "queued" || entry.stage === "error") && (
                            <Button
                              size="small"
                              variant="text"
                              color="inherit"
                              startIcon={<Delete />}
                              onClick={() => removeFile(entry.id)}
                            >
                              Remove
                            </Button>
                          )}
                        </Stack>
                      </Grid>
                    </Grid>

                    {entry.stage === "completed" && entry.documentId && (
                      <Box sx={{ mt: 2, pt: 2, borderTop: "1px solid", borderColor: "divider" }}>
                        <Stack spacing={1.2}>
                          <Typography variant="subtitle2">Validation (UI-native)</Typography>
                          <Typography variant="caption" color="text.secondary">
                            Proves index persistence and phrase retrieval for this ingestion target.
                          </Typography>
                          <Stack direction={{ xs: "column", md: "row" }} spacing={1}>
                            <TextField
                              size="small"
                              label="Phrase for retrieval proof (optional)"
                              placeholder={defaultPhrase}
                              value={phraseValue}
                              onChange={(event) =>
                                setVerificationPhraseById((prev) => ({ ...prev, [entry.id]: event.target.value }))
                              }
                              fullWidth
                            />
                            <Button
                              variant="outlined"
                              onClick={() => void verifyIndexedDocument(entry)}
                              disabled={isVerifying || isDeleting}
                            >
                              {isVerifying ? "Verifying..." : "Verify Index & Retrieval"}
                            </Button>
                          </Stack>

                          <Stack direction={{ xs: "column", md: "row" }} spacing={1}>
                            <TextField
                              size="small"
                              label="Grounded answer question"
                              placeholder={defaultGroundedQuestion}
                              value={groundedQuestionValue}
                              onChange={(event) =>
                                setGroundedQuestionById((prev) => ({ ...prev, [entry.id]: event.target.value }))
                              }
                              fullWidth
                            />
                            <Button
                              variant="contained"
                              color="secondary"
                              onClick={() => void generateGroundedPreview(entry)}
                              disabled={isGrounding || isDeleting}
                            >
                              {isGrounding ? "Generating..." : "Generate Grounded Answer"}
                            </Button>
                          </Stack>

                          {verificationError && (
                            <Alert severity="error" sx={{ borderRadius: borderRadius.sm }}>
                              {verificationError}
                            </Alert>
                          )}

                          {verification && (
                            <Alert severity="success" sx={{ borderRadius: borderRadius.sm }}>
                              <Stack spacing={0.5}>
                                <Typography variant="body2">
                                  Workspace target: <strong>{verification.workspace_target}</strong> | Index:{" "}
                                  <strong>{verification.physical_index_name}</strong>
                                </Typography>
                                <Typography variant="body2">
                                  Indexed chunks: <strong>{verification.indexed_chunks_count}</strong>
                                </Typography>
                                <Typography variant="body2">
                                  Phrase hits: <strong>{verification.phrase_hits_count}</strong>
                                  {verification.phrase ? ` for "${verification.phrase}"` : " (no phrase provided)"}
                                </Typography>
                              </Stack>
                            </Alert>
                          )}

                          {groundedError && (
                            <Alert severity="error" sx={{ borderRadius: borderRadius.sm }}>
                              {groundedError}
                            </Alert>
                          )}

                          {groundedResult && (
                            <Alert
                              severity={groundedResult.status === "ok" ? "success" : "warning"}
                              sx={{ borderRadius: borderRadius.sm }}
                            >
                              <Stack spacing={0.7}>
                                <Typography variant="body2">
                                  Grounded status: <strong>{groundedResult.status}</strong>
                                  {groundedResult.cached ? " (cached)" : ""}
                                </Typography>
                                <Typography variant="body2">
                                  Retrieved chunks: <strong>{groundedResult.retrieved_chunks_count}</strong> | Citations:{" "}
                                  <strong>{groundedResult.citations.length}</strong> | Confidence:{" "}
                                  <strong>{groundedResult.confidence.toFixed(2)}</strong>
                                </Typography>
                                <Typography variant="body2">
                                  {groundedResult.answer}
                                </Typography>
                              </Stack>
                            </Alert>
                          )}
                        </Stack>
                      </Box>
                    )}
                  </CardContent>
                </Card>
              );
            })}
          </Stack>
        </Grid>
      </Grid>

      {errorCount > 0 && (
        <Alert severity="warning" sx={{ mt: spacing[2], borderRadius: borderRadius.md }}>
          {errorCount} file{errorCount > 1 ? "s" : ""} failed ingestion. Use Retry to recover without rebuilding the entire queue.
        </Alert>
      )}
    </PageContainer>
  );
}
