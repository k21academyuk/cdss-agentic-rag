import { http, HttpResponse, delay } from 'msw';
import { mockPatients } from './data/patients';
import { mockClinicalResponse } from './data/clinical';
import { mockArticles } from './data/literature';
import { mockAuditLog, mockDashboardStats } from './data/audit';

const API_BASE = '/api/v1';
type MockIngestionStatus = {
  document_id: string;
  pipeline_document_id: string;
  filename: string;
  document_type: string;
  normalized_document_type: string;
  patient_id?: string | null;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  progress: number;
  created_at: string;
  updated_at: string;
  error: string | null;
  poll_count: number;
};

const mockIngestionJobs = new Map<string, MockIngestionStatus>();

async function buildMockStreamingResponse() {
  const sseEvents = [
    { event: 'processing', data: { status: 'started', message: 'Processing clinical query...', session_id: 'mock-session-' + Date.now() } },
    { event: 'progress', data: { phase: 'planning', message: 'Analyzing query and creating execution plan...' } },
    { event: 'agent_result', data: { agent: 'patient_history', summary: 'Retrieved patient profile with 3 active conditions.', sources_retrieved: 3, latency_ms: 450 } },
    { event: 'agent_result', data: { agent: 'medical_literature', summary: 'Found 8 relevant articles on diabetes and CKD management.', sources_retrieved: 8, latency_ms: 1200 } },
    { event: 'agent_result', data: { agent: 'protocol', summary: 'Retrieved ADA guidelines for diabetes management.', sources_retrieved: 2, latency_ms: 380 } },
    { event: 'agent_result', data: { agent: 'drug_safety', summary: 'Identified 1 moderate drug interaction.', sources_retrieved: 4, latency_ms: 520 } },
    { event: 'complete', data: mockClinicalResponse },
  ];

  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      for (const { event, data } of sseEvents) {
        await delay(500);
        const message = `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
        controller.enqueue(encoder.encode(message));
      }
      controller.close();
    },
  });

  return new HttpResponse(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
    },
  });
}

export const handlers = [
  // Health check
  http.get(`${API_BASE}/health`, () => {
    return HttpResponse.json({
      status: 'healthy',
      version: '1.0.0',
      services: {
        openai: 'healthy',
        cosmos: 'healthy',
        redis: 'healthy',
        search: 'healthy',
      },
      timestamp: new Date().toISOString(),
    });
  }),

  // Patient endpoints
  http.get(`${API_BASE}/patients/:id`, async ({ params }) => {
    await delay(300);
    const patient = mockPatients.find(p => p.patient_id === params.id);
    if (!patient) {
      return new HttpResponse(null, { status: 404 });
    }
    return HttpResponse.json(patient);
  }),

  http.get(`${API_BASE}/patients`, async ({ request }) => {
    await delay(400);
    const url = new URL(request.url);
    const search = url.searchParams.get('search') || '';
    
    let filtered = mockPatients;
    if (search) {
      filtered = mockPatients.filter(p => 
        p.patient_id.toLowerCase().includes(search.toLowerCase()) ||
        p.demographics.sex.toLowerCase().includes(search.toLowerCase())
      );
    }
    
    return HttpResponse.json({
      patients: filtered,
      total: filtered.length,
      page: 1,
      page_size: 20,
    });
  }),

  // Clinical query endpoints
  http.post(`${API_BASE}/query`, async () => {
    await delay(1500);
    return HttpResponse.json({
      query_id: 'query_' + Date.now(),
      status: 'completed',
      clinical_response: mockClinicalResponse,
    });
  }),

  http.get(`${API_BASE}/query/stream`, async () => buildMockStreamingResponse()),
  http.post(`${API_BASE}/query/stream`, async () => buildMockStreamingResponse()),

  // Drug interaction check
  http.post(`${API_BASE}/drugs/interactions`, async ({ request }) => {
    await delay(800);
    const body = await request.json();
    const medicationInputs = (
      body as unknown as { medications?: Array<string | { name?: string }> }
    ).medications ?? [];
    const medications = medicationInputs
      .map((entry) => (typeof entry === "string" ? entry : entry?.name ?? ""))
      .map((name) => name.trim())
      .filter((name) => name.length > 0);
    
    const interactions: Array<{
      drug_a: string;
      drug_b: string;
      severity: 'minor' | 'moderate' | 'major';
      description: string;
      evidence_level: number;
      source: string;
    }> = [];
    const severityLevels = ['minor', 'moderate', 'major'] as const;
    for (let i = 0; i < medications.length; i++) {
      for (let j = i + 1; j < medications.length; j++) {
        if (Math.random() > 0.5) {
          interactions.push({
            drug_a: medications[i],
            drug_b: medications[j],
            severity: severityLevels[Math.floor(Math.random() * severityLevels.length)],
            description: `Potential interaction between ${medications[i]} and ${medications[j]}. Monitor patient closely.`,
            evidence_level: Math.floor(Math.random() * 3) + 1,
            source: 'DrugBank 2024',
          });
        }
      }
    }
    
    return HttpResponse.json({
      interactions,
      alternatives: [],
      dosage_adjustments: [],
    });
  }),

  // Literature search
  http.post(`${API_BASE}/search/literature`, async ({ request }) => {
    await delay(1200);
    const body = await request.json();
    const maxResults = (body as any)?.max_results || 10;
    
    return HttpResponse.json({
      papers: mockArticles.slice(0, maxResults),
      total: mockArticles.length,
      page: 1,
      page_size: maxResults,
    });
  }),

  // Protocol search
  http.post(`${API_BASE}/search/protocols`, async ({ request }) => {
    await delay(600);
    const body = await request.json();
    
    return HttpResponse.json({
      protocols: [
        {
          guideline_name: 'ADA Standards of Medical Care in Diabetes - 2024',
          version: '2024.1',
          recommendation: 'For patients with T2DM and CKD, consider SGLT2 inhibitors for renal protection.',
          evidence_grade: 'A',
          specialty: 'Endocrinology',
          contraindications: ['eGFR < 30 mL/min for some SGLT2i'],
          last_updated: '2024-01-01',
        },
      ],
      total: 1,
      page: 1,
      page_size: 10,
    });
  }),

  // Document ingestion
  http.post(`${API_BASE}/documents/ingest`, async ({ request }) => {
    await delay(1000);
    const formData = await request.formData();
    const file = formData.get('file');
    const documentType = String(formData.get('document_type') || 'patient_record');
    const patientId = (formData.get('patient_id') || '').toString().trim() || null;
    const documentId = 'doc_' + Date.now();
    const pipelineDocumentId = `pipeline-${documentId}`;
    const now = new Date().toISOString();
    const normalizedMap: Record<string, string> = {
      patient_record: 'generic',
      protocol: 'clinical_guideline',
      literature: 'pubmed_abstract',
    };
    const normalizedDocumentType = normalizedMap[documentType] || documentType;

    mockIngestionJobs.set(documentId, {
      document_id: documentId,
      pipeline_document_id: pipelineDocumentId,
      filename: file instanceof File ? file.name : 'uploaded-document',
      document_type: documentType,
      normalized_document_type: normalizedDocumentType,
      patient_id: patientId,
      status: 'queued',
      progress: 0,
      created_at: now,
      updated_at: now,
      error: null,
      poll_count: 0,
    });

    return HttpResponse.json({
      document_id: documentId,
      status: 'queued',
      message: 'Document accepted for ingestion. Processing started.',
      estimated_completion_seconds: 45,
      chunks_count: Math.floor(Math.random() * 20) + 5,
    });
  }),

  // Document ingestion status
  http.get(`${API_BASE}/documents/:documentId/status`, async ({ params }) => {
    await delay(350);
    const documentId = String(params.documentId);
    const current = mockIngestionJobs.get(documentId);

    if (!current) {
      return HttpResponse.json({ detail: `Document '${documentId}' not found.` }, { status: 404 });
    }

    const next = { ...current };
    next.poll_count += 1;
    next.updated_at = new Date().toISOString();

    if (next.status === 'queued') {
      next.status = 'processing';
      next.progress = 15;
    } else if (next.status === 'processing') {
      next.progress = Math.min(100, next.progress + 25 + Math.floor(Math.random() * 20));
      if (next.progress >= 100) {
        next.status = 'completed';
        next.progress = 100;
      }
    }

    mockIngestionJobs.set(documentId, next);
    return HttpResponse.json({
      document_id: next.document_id,
      pipeline_document_id: next.pipeline_document_id,
      filename: next.filename,
      document_type: next.document_type,
      normalized_document_type: next.normalized_document_type,
      patient_id: next.patient_id ?? null,
      status: next.status,
      progress: next.progress,
      created_at: next.created_at,
      updated_at: next.updated_at,
      error: next.error,
    });
  }),

  // Document index/retrieval verification
  http.post(`${API_BASE}/documents/:documentId/verify`, async ({ params, request }) => {
    await delay(350);
    const documentId = String(params.documentId);
    const current = mockIngestionJobs.get(documentId);

    if (!current) {
      return HttpResponse.json({ detail: `Document '${documentId}' not found.` }, { status: 404 });
    }

    const body = (await request.json()) as { phrase?: string; top?: number };
    const phrase = (body?.phrase || '').trim();
    const top = Math.max(1, Math.min(20, Number(body?.top || 5)));

    const indexMap: Record<string, { logical: string; physical: string; workspace: string }> = {
      generic: {
        logical: 'patient_records',
        physical: 'patient-records',
        workspace: 'query_patient_context',
      },
      clinical_guideline: {
        logical: 'treatment_protocols',
        physical: 'treatment-protocols',
        workspace: 'protocol',
      },
      pubmed_abstract: {
        logical: 'medical_literature',
        physical: 'medical-literature-cache',
        workspace: 'literature',
      },
    };
    const resolved = indexMap[current.normalized_document_type] || indexMap.generic;

    const buildHit = (idx: number) => ({
      id: `${current.pipeline_document_id}-chunk-${idx}`,
      chunk_index: idx,
      score: Math.max(0.25, 1 - idx * 0.08),
      content_preview: `Mock chunk ${idx} from ${current.filename}${phrase ? ` containing '${phrase}'` : ''}.`,
    });

    const indexed_chunks = Array.from({ length: Math.min(top, 3) }, (_, i) => buildHit(i + 1));
    const phrase_hits = phrase
      ? Array.from({ length: Math.min(top, 2) }, (_, i) => buildHit(i + 1))
      : [];

    return HttpResponse.json({
      document_id: current.document_id,
      pipeline_document_id: current.pipeline_document_id,
      document_type: current.document_type,
      normalized_document_type: current.normalized_document_type,
      workspace_target: resolved.workspace,
      logical_index_name: resolved.logical,
      physical_index_name: resolved.physical,
      indexed_chunks_count: indexed_chunks.length,
      indexed_chunks,
      phrase: phrase || null,
      phrase_hits_count: phrase_hits.length,
      phrase_hits,
    });
  }),

  // Grounded answer preview
  http.post(`${API_BASE}/documents/:documentId/grounded-preview`, async ({ params, request }) => {
    await delay(500);
    const documentId = String(params.documentId);
    const current = mockIngestionJobs.get(documentId);

    if (!current) {
      return HttpResponse.json({ detail: `Document '${documentId}' not found.` }, { status: 404 });
    }

    const body = (await request.json()) as {
      question?: string;
      top?: number;
    };
    const question = String(body?.question || "").trim();
    const top = Math.max(1, Math.min(20, Number(body?.top || 8)));
    if (!question) {
      return HttpResponse.json({ detail: "question must not be empty." }, { status: 422 });
    }

    const indexMap: Record<string, { logical: string; physical: string; workspace: string }> = {
      generic: {
        logical: "patient_records",
        physical: "patient-records",
        workspace: "query_patient_context",
      },
      clinical_guideline: {
        logical: "treatment_protocols",
        physical: "treatment-protocols",
        workspace: "protocol",
      },
      pubmed_abstract: {
        logical: "medical_literature",
        physical: "medical-literature-cache",
        workspace: "literature",
      },
    };
    const resolved = indexMap[current.normalized_document_type] || indexMap.generic;

    const citations = Array.from({ length: Math.min(top, 2) }, (_, idx) => ({
      chunk_id: `${current.pipeline_document_id}-chunk-${idx + 1}`,
      chunk_index: idx + 1,
      quote: `Mock quote ${idx + 1} for '${question}'.`,
      score: Math.max(0.25, 1 - idx * 0.1),
      content_preview: `Mock content preview ${idx + 1} from ${current.filename}.`,
    }));

    return HttpResponse.json({
      document_id: current.document_id,
      pipeline_document_id: current.pipeline_document_id,
      normalized_document_type: current.normalized_document_type,
      workspace_target: resolved.workspace,
      logical_index_name: resolved.logical,
      physical_index_name: resolved.physical,
      question,
      retrieved_chunks_count: Math.min(top, 4),
      status: "ok",
      answer: `Mock grounded answer generated for '${question}'.`,
      confidence: 0.82,
      citations,
      cached: false,
    });
  }),

  // Document delete
  http.delete(`${API_BASE}/documents/:documentId`, async ({ params }) => {
    await delay(300);
    const documentId = String(params.documentId);
    const current = mockIngestionJobs.get(documentId);

    if (!current) {
      return HttpResponse.json({ detail: `Document '${documentId}' not found.` }, { status: 404 });
    }

    if (current.status === 'queued' || current.status === 'processing') {
      return HttpResponse.json(
        { detail: "Document is still processing. Wait until completion before deletion." },
        { status: 409 }
      );
    }

    mockIngestionJobs.delete(documentId);

    const indexMap: Record<string, { logical: string; physical: string }> = {
      generic: { logical: 'patient_records', physical: 'patient-records' },
      clinical_guideline: { logical: 'treatment_protocols', physical: 'treatment-protocols' },
      pubmed_abstract: { logical: 'medical_literature', physical: 'medical-literature-cache' },
    };
    const resolved = indexMap[current.normalized_document_type] || indexMap.generic;

    return HttpResponse.json({
      document_id: current.document_id,
      pipeline_document_id: current.pipeline_document_id,
      normalized_document_type: current.normalized_document_type,
      logical_index_name: resolved.logical,
      physical_index_name: resolved.physical,
      deleted_chunks_count: Math.floor(Math.random() * 8) + 1,
      status: 'deleted',
    });
  }),

  // Audit trail
  http.get(`${API_BASE}/audit`, async ({ request }) => {
    await delay(500);
    const url = new URL(request.url);
    const eventType = url.searchParams.get('event_type');
    
    let filtered = mockAuditLog;
    if (eventType) {
      filtered = mockAuditLog.filter((e) => (e.event_type || e.type || "").includes(eventType));
    }
    
    return HttpResponse.json(filtered);
  }),
];
