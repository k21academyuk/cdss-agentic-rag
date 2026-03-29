// src/hooks/useStreamingSession.ts
// WebSocket hook for CDSS streaming events from Azure Web PubSub.

import { useEffect, useRef, useCallback, useState } from "react";
import { useSessionStore } from "@/stores/sessionStore";
import { runtimeConfig } from "@/config/runtime";
import type { StreamingEvent } from "@/types/cdss";

interface UseStreamingSessionOptions {
  sessionId: string | null;
  autoConnect?: boolean;
  maxRetries?: number;
}

interface UseStreamingSessionReturn {
  isConnected: boolean;
  isReconnecting: boolean;
  error: Error | null;
  connect: () => void;
  disconnect: () => void;
  reconnect: () => void;
}

const RETRY_DELAYS = [1000, 2000, 4000]; // Exponential backoff: 1s, 2s, 4s
const WS_ENDPOINT = runtimeConfig.wsEndpoint;

export function useStreamingSession({
  sessionId,
  autoConnect = true,
  maxRetries = 3,
}: UseStreamingSessionOptions): UseStreamingSessionReturn {
  const [isConnected, setIsConnected] = useState(false);
  const [isReconnecting, setIsReconnecting] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const retryCountRef = useRef(0);
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intentionalDisconnectRef = useRef(false);

  const handleStreamingEvent = useSessionStore((state) => state.handleStreamingEvent);
  const startSession = useSessionStore((state) => state.startSession);
  const resetSession = useSessionStore((state) => state.resetSession);
  const patientId = useSessionStore((state) => state.patientId);

  // Parse and handle incoming WebSocket messages
  const handleMessage = useCallback(
    (event: MessageEvent) => {
      try {
        const rawData = JSON.parse(event.data);
        const streamingEvent: StreamingEvent = rawData;

        // Validate event structure
        if (!streamingEvent.event_type || !streamingEvent.timestamp) {
          console.warn("Invalid streaming event structure:", rawData);
          return;
        }

        handleStreamingEvent(streamingEvent);
      } catch (err) {
        console.error("Failed to parse WebSocket message:", err);
        setError(new Error("Failed to parse server message"));
      }
    },
    [handleStreamingEvent]
  );

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (!sessionId || !WS_ENDPOINT) {
      if (!WS_ENDPOINT) {
        setError(new Error("WebSocket endpoint not configured"));
      }
      return;
    }

    // Clean up existing connection
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    intentionalDisconnectRef.current = false;
    setError(null);

    try {
      // Build WebSocket URL with session info
      const wsUrl = `${WS_ENDPOINT}/sessions/${sessionId}/stream`;
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        setIsConnected(true);
        setIsReconnecting(false);
        retryCountRef.current = 0;
        setError(null);

        // Initialize session in store
        const traceId = `trace-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        startSession(sessionId, patientId || "unknown", traceId);

        console.log(`[WS] Connected to session ${sessionId}`);
      };

      ws.onmessage = handleMessage;

      ws.onerror = (event) => {
        console.error("[WS] WebSocket error:", event);
        setError(new Error("WebSocket connection error"));
      };

      ws.onclose = (event) => {
        setIsConnected(false);

        // Attempt reconnection if not intentional and retries remaining
        if (
          !intentionalDisconnectRef.current &&
          retryCountRef.current < maxRetries &&
          sessionId
        ) {
          const delay = RETRY_DELAYS[retryCountRef.current] || RETRY_DELAYS[RETRY_DELAYS.length - 1];
          retryCountRef.current++;

          setIsReconnecting(true);
          console.log(`[WS] Reconnecting in ${delay}ms (attempt ${retryCountRef.current}/${maxRetries})`);

          retryTimeoutRef.current = setTimeout(() => {
            connect();
          }, delay);
        } else if (retryCountRef.current >= maxRetries) {
          setError(new Error("Max reconnection attempts reached"));
          setIsReconnecting(false);
        }
      };

      wsRef.current = ws;
    } catch (err) {
      setError(err instanceof Error ? err : new Error("Failed to connect"));
    }
  }, [sessionId, patientId, maxRetries, handleMessage, startSession]);

  // Disconnect from WebSocket
  const disconnect = useCallback(() => {
    intentionalDisconnectRef.current = true;

    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current);
      retryTimeoutRef.current = null;
    }

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    setIsConnected(false);
    setIsReconnecting(false);
    retryCountRef.current = 0;
  }, []);

  // Manual reconnect
  const reconnect = useCallback(() => {
    disconnect();
    retryCountRef.current = 0;
    intentionalDisconnectRef.current = false;
    connect();
  }, [connect, disconnect]);

  // Auto-connect when sessionId changes
  useEffect(() => {
    if (autoConnect && sessionId) {
      connect();
    }

    return () => {
      disconnect();
    };
  }, [sessionId, autoConnect, connect, disconnect]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (retryTimeoutRef.current) {
        clearTimeout(retryTimeoutRef.current);
      }
    };
  }, []);

  return {
    isConnected,
    isReconnecting,
    error,
    connect,
    disconnect,
    reconnect,
  };
}
