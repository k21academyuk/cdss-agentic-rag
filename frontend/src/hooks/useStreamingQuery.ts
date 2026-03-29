import { useState, useCallback, useRef, useEffect } from 'react';
import { ClinicalResponse, StreamingQueryUpdate } from '@/lib/types';
import { createStreamingConnection } from '@/lib/api-client';

export type StreamingStatus = 'idle' | 'streaming' | 'completed' | 'partial_failure' | 'cancelled' | 'error';

export interface StreamingTimelineEvent {
  id: string;
  type: StreamingQueryUpdate['type'] | 'stream_start' | 'cancelled' | 'stream_error';
  agent?: string;
  progress?: number;
  message?: string;
  timestamp: number;
  level: 'info' | 'success' | 'warning' | 'error';
}

interface UseStreamingQueryReturn {
  response: ClinicalResponse | null;
  isStreaming: boolean;
  progress: number;
  agentProgress: Record<string, number>;
  error: string | null;
  status: StreamingStatus;
  timeline: StreamingTimelineEvent[];
  failedAgents: string[];
  lastMessage: string | null;
  startStream: () => void;
  cancelStream: () => void;
  reset: () => void;
}

export function useStreamingQuery(
  query: string,
  patientId?: string,
  sessionId?: string
): UseStreamingQueryReturn {
  const [response, setResponse] = useState<ClinicalResponse | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [progress, setProgress] = useState(0);
  const [agentProgress, setAgentProgress] = useState<Record<string, number>>({});
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<StreamingStatus>('idle');
  const [timeline, setTimeline] = useState<StreamingTimelineEvent[]>([]);
  const [failedAgents, setFailedAgents] = useState<string[]>([]);
  const [lastMessage, setLastMessage] = useState<string | null>(null);
  
  const cancelRef = useRef<(() => void) | null>(null);
  const lastAgentProgressRef = useRef<Record<string, number>>({});
  const hasResponseRef = useRef(false);
  const failedAgentsRef = useRef<string[]>([]);

  const pushTimelineEvent = useCallback(
    (
      type: StreamingTimelineEvent['type'],
      options?: {
        agent?: string;
        progress?: number;
        message?: string;
        level?: StreamingTimelineEvent['level'];
      }
    ) => {
      const event: StreamingTimelineEvent = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        type,
        agent: options?.agent,
        progress: options?.progress,
        message: options?.message,
        timestamp: Date.now(),
        level: options?.level || 'info',
      };
      setTimeline((prev) => [...prev, event]);
      if (options?.message) {
        setLastMessage(options.message);
      }
    },
    []
  );

  const startStream = useCallback(() => {
    setResponse(null);
    setProgress(0);
    setAgentProgress({});
    setError(null);
    setIsStreaming(true);
    setStatus('streaming');
    setTimeline([]);
    setFailedAgents([]);
    setLastMessage('Initializing orchestration...');
    lastAgentProgressRef.current = {};
    hasResponseRef.current = false;
    failedAgentsRef.current = [];
    pushTimelineEvent('stream_start', {
      message: 'Streaming query orchestration started.',
      level: 'info',
    });

    cancelRef.current = createStreamingConnection(
      query,
      (data) => {
        const update = data as StreamingQueryUpdate;
        const agentName = update.agent || 'unknown';
        const updateMessage = update.message || '';
        
        if (update.type === 'agent_start') {
          setAgentProgress((prev) => ({
            ...prev,
            [agentName]: 0,
          }));
          lastAgentProgressRef.current[agentName] = 0;
          pushTimelineEvent('agent_start', {
            agent: agentName,
            progress: 0,
            message: updateMessage || `${agentName} started`,
            level: 'info',
          });
        } else if (update.type === 'agent_progress') {
          const nextProgress = update.progress || 0;
          setAgentProgress((prev) => ({
            ...prev,
            [agentName]: nextProgress,
          }));
          setProgress(nextProgress);
          const previousProgress = lastAgentProgressRef.current[agentName] || 0;
          const shouldLogProgress = nextProgress >= 100 || nextProgress - previousProgress >= 20 || previousProgress === 0;
          if (shouldLogProgress) {
            lastAgentProgressRef.current[agentName] = nextProgress;
            pushTimelineEvent('agent_progress', {
              agent: agentName,
              progress: nextProgress,
              message: updateMessage || `${agentName} ${Math.round(nextProgress)}%`,
              level: 'info',
            });
          }
        } else if (update.type === 'agent_complete') {
          setAgentProgress((prev) => ({
            ...prev,
            [agentName]: 100,
          }));
          lastAgentProgressRef.current[agentName] = 100;
          pushTimelineEvent('agent_complete', {
            agent: agentName,
            progress: 100,
            message: updateMessage || `${agentName} completed`,
            level: 'success',
          });
        } else if (update.type === 'synthesis_start') {
          pushTimelineEvent('synthesis_start', {
            message: updateMessage || 'Synthesizing final response...',
            level: 'info',
          });
        } else if (update.type === 'validation_start') {
          pushTimelineEvent('validation_start', {
            message: updateMessage || 'Running guardrail validation...',
            level: 'info',
          });
        } else if (update.type === 'validation_complete') {
          pushTimelineEvent('validation_complete', {
            message: updateMessage || 'Validation complete.',
            level: 'success',
          });
        } else if (update.type === 'synthesis_complete') {
          if (update.response) {
            setResponse(update.response);
            hasResponseRef.current = true;
          }
          setProgress(100);
          setStatus(failedAgentsRef.current.length > 0 ? 'partial_failure' : 'completed');
          pushTimelineEvent('synthesis_complete', {
            progress: 100,
            message: updateMessage || 'Synthesis completed.',
            level: failedAgentsRef.current.length > 0 ? 'warning' : 'success',
          });
        } else if (update.type === 'error') {
          const errorMessage = update.message || 'An error occurred';
          setError(errorMessage);
          pushTimelineEvent('error', {
            agent: update.agent,
            message: errorMessage,
            level: 'error',
          });
          if (update.agent && !failedAgentsRef.current.includes(update.agent)) {
            failedAgentsRef.current = [...failedAgentsRef.current, update.agent];
            setFailedAgents(failedAgentsRef.current);
          }
          if (!hasResponseRef.current) {
            setStatus('error');
          } else {
            setStatus('partial_failure');
          }
        }
      },
      (err) => {
        setError(err.message);
        setStatus('error');
        pushTimelineEvent('stream_error', {
          message: err.message,
          level: 'error',
        });
        setIsStreaming(false);
      },
      () => {
        setIsStreaming(false);
        setStatus((prev) => {
          if (prev === 'cancelled' || prev === 'error' || prev === 'partial_failure' || prev === 'completed') {
            return prev;
          }
          if (hasResponseRef.current) {
            return failedAgentsRef.current.length > 0 ? 'partial_failure' : 'completed';
          }
          return failedAgentsRef.current.length > 0 ? 'partial_failure' : 'idle';
        });
      },
      patientId,
      sessionId
    );
  }, [query, patientId, sessionId, pushTimelineEvent]);

  const cancelStream = useCallback(() => {
    if (cancelRef.current) {
      cancelRef.current();
      cancelRef.current = null;
    }
    setIsStreaming(false);
    setStatus('cancelled');
    pushTimelineEvent('cancelled', {
      message: 'Streaming cancelled by user.',
      level: 'warning',
    });
  }, [pushTimelineEvent]);

  const reset = useCallback(() => {
    setResponse(null);
    setProgress(0);
    setAgentProgress({});
    setError(null);
    setIsStreaming(false);
    setStatus('idle');
    setTimeline([]);
    setFailedAgents([]);
    setLastMessage(null);
    lastAgentProgressRef.current = {};
    hasResponseRef.current = false;
    failedAgentsRef.current = [];
    if (cancelRef.current) {
      cancelRef.current();
      cancelRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      if (cancelRef.current) {
        cancelRef.current();
      }
    };
  }, []);

  return {
    response,
    isStreaming,
    progress,
    agentProgress,
    error,
    status,
    timeline,
    failedAgents,
    lastMessage,
    startStream,
    cancelStream,
    reset,
  };
}
