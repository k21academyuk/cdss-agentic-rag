import axios, { AxiosError, AxiosInstance, AxiosRequestConfig } from 'axios';
import { msalInstance } from './auth';
import { runtimeConfig } from "@/config/runtime";
import {
  ApiError,
  ClinicalResponse,
  DocumentDeleteResponse,
  DocumentGroundedPreviewRequest,
  DocumentGroundedPreviewResponse,
  DocumentIngestResponse,
  DocumentIngestionStatusResponse,
  DocumentSearchVerificationRequest,
  DocumentSearchVerificationResponse,
  PatientListResponse,
  PatientProfile,
  StreamingQueryUpdate,
} from './types';

function resolveApiBaseUrl(rawValue: string | undefined): string {
  const value = (rawValue || '/api').trim();
  if (runtimeConfig.environment === "production") {
    const isAbsolute = /^https?:\/\//i.test(value);
    if (!isAbsolute || !value.toLowerCase().startsWith('https://')) {
      throw new Error('VITE_API_BASE_URL must be an absolute HTTPS URL in production.');
    }
  }
  return value.replace(/\/+$/, '');
}

const API_BASE_URL = resolveApiBaseUrl(runtimeConfig.apiBaseUrl);
const API_SCOPE = runtimeConfig.apiScope || '';

class ApiClient {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    this.client.interceptors.request.use(async (config) => {
      try {
        const account = msalInstance.getAllAccounts()[0];
        if (account && API_SCOPE) {
          const response = await msalInstance.acquireTokenSilent({
            scopes: [API_SCOPE],
            account,
          });
          config.headers.Authorization = `Bearer ${response.accessToken}`;
        }
      } catch (error) {
        console.error('Failed to acquire token:', error);
      }
      return config;
    });

    this.client.interceptors.response.use(
      (response) => response,
      (error: AxiosError) => {
        const responseData = error.response?.data as { message?: string } | undefined;
        const apiError: ApiError = {
          message: responseData?.message || error.message,
          status_code: error.response?.status,
          details: error.response?.data,
        };
        return Promise.reject(apiError);
      }
    );
  }

  async get<T = any>(url: string, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.client.get<T>(url, config);
    return response.data;
  }

  async post<T = any>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.client.post<T>(url, data, config);
    return response.data;
  }

  async put<T = any>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.client.put<T>(url, data, config);
    return response.data;
  }

  async delete<T = any>(url: string, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.client.delete<T>(url, config);
    return response.data;
  }
}

export const apiClient = new ApiClient();

export const clinicalApi = {
  submitQuery: async (query: string, patientId?: string, sessionId?: string) => {
    return apiClient.post('/v1/query', {
      text: query,
      patient_id: patientId,
      session_id: sessionId,
    });
  },

  getQuery: async (queryId: string) => {
    return apiClient.get(`/v1/query/${queryId}`);
  },

  getPatient: async (patientId: string) => {
    return apiClient.get<PatientProfile>(`/v1/patients/${patientId}`);
  },

  searchPatients: async (params: { search?: string; page?: number; limit?: number }) => {
    return apiClient.get<PatientListResponse>('/v1/patients', { params });
  },

  checkDrugInteractions: async (medications: string[]) => {
    return apiClient.post('/v1/drugs/interactions', {
      medications,
    });
  },

  searchLiterature: async (params: {
    query: string;
    max_results?: number;
    date_range?: { start: string; end: string };
    article_types?: string[];
  }) => {
    return apiClient.post('/v1/search/literature', params);
  },

  searchProtocols: async (params: { query: string; specialty?: string; max_results?: number }) => {
    return apiClient.post('/v1/search/protocols', params);
  },

  ingestDocument: async (
    file: File,
    documentType: string,
    metadata?: Record<string, unknown>,
    patientId?: string
  ): Promise<DocumentIngestResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('document_type', documentType);
    if (patientId && patientId.trim().length > 0) {
      formData.append('patient_id', patientId.trim());
    }
    if (metadata) {
      formData.append('metadata', JSON.stringify(metadata));
    }
    return apiClient.post<DocumentIngestResponse>('/v1/documents/ingest', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },

  getDocumentIngestionStatus: async (documentId: string): Promise<DocumentIngestionStatusResponse> => {
    return apiClient.get<DocumentIngestionStatusResponse>(`/v1/documents/${documentId}/status`);
  },

  verifyDocumentInSearch: async (
    documentId: string,
    payload: DocumentSearchVerificationRequest
  ): Promise<DocumentSearchVerificationResponse> => {
    return apiClient.post<DocumentSearchVerificationResponse>(`/v1/documents/${documentId}/verify`, payload);
  },

  generateDocumentGroundedPreview: async (
    documentId: string,
    payload: DocumentGroundedPreviewRequest
  ): Promise<DocumentGroundedPreviewResponse> => {
    return apiClient.post<DocumentGroundedPreviewResponse>(
      `/v1/documents/${documentId}/grounded-preview`,
      payload
    );
  },

  deleteDocument: async (documentId: string): Promise<DocumentDeleteResponse> => {
    return apiClient.delete<DocumentDeleteResponse>(`/v1/documents/${documentId}`);
  },

  getAuditTrail: async (params: {
    start_date?: string;
    end_date?: string;
    event_type?: string;
    actor_id?: string;
    page?: number;
    limit?: number;
  }) => {
    return apiClient.get('/v1/audit', { params });
  },

  getHealthCheck: async () => {
    return apiClient.get('/v1/health');
  },
};

export function createStreamingConnection(
  query: string,
  onMessage: (data: unknown) => void,
  onError: (error: Error) => void,
  onComplete: () => void,
  patientId?: string,
  sessionId?: string
): () => void {
  const abortController = new AbortController();
  let closed = false;

  const normalizeUpdate = (eventName: string, payload: unknown): StreamingQueryUpdate | null => {
    if (payload && typeof payload === 'object' && 'type' in payload) {
      const maybeTyped = payload as StreamingQueryUpdate;
      if (
        maybeTyped.type === 'agent_start' ||
        maybeTyped.type === 'agent_progress' ||
        maybeTyped.type === 'agent_complete' ||
        maybeTyped.type === 'synthesis_start' ||
        maybeTyped.type === 'synthesis_complete' ||
        maybeTyped.type === 'validation_start' ||
        maybeTyped.type === 'validation_complete' ||
        maybeTyped.type === 'error'
      ) {
        return maybeTyped;
      }
    }

    const data = (payload && typeof payload === 'object' ? payload : {}) as Record<string, unknown>;
    switch (eventName) {
      case 'processing':
        return {
          type: 'synthesis_start',
          message: (data.message as string) || 'Processing clinical query...',
        };
      case 'progress':
        return {
          type: 'agent_progress',
          agent: (data.phase as string) || 'orchestrator',
          progress: typeof data.progress === 'number' ? data.progress : 15,
          message: (data.message as string) || 'Planning query orchestration...',
        };
      case 'agent_result':
        return {
          type: 'agent_complete',
          agent: (data.agent as string) || 'agent',
          progress: 100,
          message: (data.summary as string) || `${(data.agent as string) || 'Agent'} completed`,
        };
      case 'drug_alerts': {
        const alerts = Array.isArray(data.alerts) ? data.alerts.length : 0;
        return {
          type: 'validation_complete',
          message: `${alerts} drug alert(s) identified.`,
        };
      }
      case 'complete':
        return {
          type: 'synthesis_complete',
          response: payload as ClinicalResponse,
          message: 'Clinical response completed.',
        };
      case 'error':
        return {
          type: 'error',
          message: (data.message as string) || 'Streaming query failed',
          agent: data.agent as string | undefined,
        };
      default:
        return null;
    }
  };

  const parsePayload = (raw: string): unknown => {
    try {
      return JSON.parse(raw);
    } catch {
      return raw;
    }
  };

  const closeConnection = () => {
    if (closed) {
      return;
    }
    closed = true;
    abortController.abort();
    onComplete();
  };

  const handleEventPayload = (eventName: string, raw: string) => {
    const payload = parsePayload(raw);
    const normalized = normalizeUpdate(eventName, payload);
    if (normalized) {
      onMessage(normalized);
    }
    if (eventName === 'complete') {
      closeConnection();
    }
  };

  const processSseChunk = (chunk: string) => {
    const lines = chunk.split('\n');
    let eventName = 'message';
    const dataLines: string[] = [];

    for (const line of lines) {
      const normalizedLine = line.replace(/\r$/, '');
      if (normalizedLine.startsWith('event:')) {
        eventName = normalizedLine.slice(6).trim();
      } else if (normalizedLine.startsWith('data:')) {
        dataLines.push(normalizedLine.slice(5).trimStart());
      }
    }

    if (dataLines.length > 0) {
      handleEventPayload(eventName, dataLines.join('\n'));
    }
  };

  const start = async () => {
    try {
      let authHeader: string | undefined;
      const account = msalInstance.getAllAccounts()[0];

      if (API_SCOPE) {
        if (!account) {
          throw new Error('Authentication required. Click Sign in and retry orchestration.');
        }
        const response = await msalInstance.acquireTokenSilent({
          scopes: [API_SCOPE],
          account,
        });
        authHeader = `Bearer ${response.accessToken}`;
      }

      const response = await fetch(`${API_BASE_URL}/v1/query/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
          ...(authHeader ? { Authorization: authHeader } : {}),
        },
        body: JSON.stringify({
          text: query,
          ...(patientId ? { patient_id: patientId } : {}),
          ...(sessionId ? { session_id: sessionId } : {}),
        }),
        signal: abortController.signal,
      });

      if (!response.ok) {
        const responseBody = await response.text().catch(() => '');
        throw new Error(
          `Streaming request failed (${response.status}). ${responseBody || 'Check auth/CORS configuration.'}`.trim()
        );
      }

      if (!response.body) {
        throw new Error('Streaming response is empty.');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (!closed) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split('\n\n');
        buffer = events.pop() ?? '';

        events.forEach((eventChunk) => {
          if (!eventChunk.trim()) return;
          processSseChunk(eventChunk);
        });
      }

      if (buffer.trim()) {
        processSseChunk(buffer);
      }
    } catch (error) {
      if (closed) {
        return;
      }
      if (error instanceof DOMException && error.name === 'AbortError') {
        return;
      }
      onError(error instanceof Error ? error : new Error('Connection error'));
    } finally {
      if (!closed) {
        closeConnection();
      }
    }
  };

  void start();

  return () => {
    closeConnection();
  };
}
