/**
 * RunProvider — single source of truth for the active run, plus the run history.
 *
 * History and per-run data come from the BACKEND (the durable DB store), not the
 * browser. Responsibilities:
 *   - upload a CSV/JSON queue (POST /v1/runs)
 *   - poll GET /v1/runs/{id} until the pipeline reaches a terminal status
 *   - fetch results + metrics + audit from the backend once terminal
 *   - list runs from GET /v1/runs (DB-backed) for the history picker
 *   - re-open any past run by fetching it fresh from the backend
 *
 * The only thing kept in localStorage is a pointer to the *active* run id, so a
 * page refresh re-opens the same run — its data is always re-fetched from the DB.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useAuth } from '@clerk/react';
import {
  api,
  ApiError,
  TERMINAL_STATUSES,
  type AuditEvent,
  type Case,
  type CaseStatus,
  type DashboardMetrics,
  type PriorityQueues,
  type QuarantinedRow,
  type ResultItem,
  type RunStatus,
} from '@/lib/api';
import type { RunHistoryEntry } from '@/lib/runHistory';
import {
  toActivityLog,
  toAnalyticsData,
  toCommunications,
  toDashboardStats,
  toExceptions,
} from '@/lib/adapters';
import type {
  ActivityLog,
  AnalyticsData,
  Communication,
  DashboardStats,
  Exception,
} from '@/types';

const RUN_ID_KEY = 'ap-active-run-id';
const POLL_INTERVAL_MS = 2000;

interface RunContextValue {
  runId: string | null;
  status: RunStatus | null;
  currentNode: string | null;
  createdAt: string | null;
  rowsAccepted: number;
  rowsQuarantined: number;
  quarantined: QuarantinedRow[];

  /** Run history, sourced from the backend DB (GET /v1/runs), newest first. */
  history: RunHistoryEntry[];

  isUploading: boolean;
  isProcessing: boolean;
  isLoadingData: boolean;
  error: string | null;

  // raw backend payloads
  results: ResultItem[];
  metrics: DashboardMetrics | null;
  priorityQueues: PriorityQueues | null;
  audit: AuditEvent[];
  /** Resolution-tracker cases, invoice_id -> case (shared so a status change in
   *  the tracker reflects on the dashboard, SLA tracker, and queues instantly). */
  cases: Record<string, Case>;

  // UI-adapted derivations
  exceptions: Exception[];
  communications: Communication[];
  dashboardStats: DashboardStats | null;
  analyticsData: AnalyticsData | null;
  activities: ActivityLog[];

  // actions
  uploadFile: (file: File, tenantId?: string) => Promise<void>;
  refresh: () => Promise<void>;
  reloadData: () => Promise<void>;
  loadRuns: () => Promise<void>;
  selectRun: (runId: string) => void;
  approve: () => Promise<void>;
  /** Advance an invoice's resolution case; updates shared state so every screen
   *  reflects it immediately. */
  updateCaseStatus: (invoiceId: string, status: CaseStatus, note?: string) => Promise<void>;
  clearRun: () => void;
  clearError: () => void;
  clearHistory: () => void;
}

const RunContext = createContext<RunContextValue | null>(null);

export function RunProvider({ children }: { children: React.ReactNode }) {
  // Only call authed endpoints once Clerk has loaded AND the user is signed in,
  // otherwise requests fire on refresh before the bearer token exists → 401.
  const { isLoaded, isSignedIn } = useAuth();
  const authReady = isLoaded && isSignedIn;

  const [runId, setRunId] = useState<string | null>(
    () => localStorage.getItem(RUN_ID_KEY),
  );
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [currentNode, setCurrentNode] = useState<string | null>(null);
  const [createdAt, setCreatedAt] = useState<string | null>(null);
  const [rowsAccepted, setRowsAccepted] = useState(0);
  const [rowsQuarantined, setRowsQuarantined] = useState(0);
  const [quarantined, setQuarantined] = useState<QuarantinedRow[]>([]);

  // Run history list, sourced from the backend (DB-backed) run store.
  const [backendRuns, setBackendRuns] = useState<RunHistoryEntry[]>([]);

  const [isUploading, setIsUploading] = useState(false);
  const [isLoadingData, setIsLoadingData] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [results, setResults] = useState<ResultItem[]>([]);
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [priorityQueues, setPriorityQueues] = useState<PriorityQueues | null>(null);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [cases, setCases] = useState<Record<string, Case>>({});

  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const isProcessing = status === 'PENDING' || status === 'RUNNING';

  // ---- history (backend DB is the source of truth), newest first ---------
  const history = useMemo<RunHistoryEntry[]>(
    () => [...backendRuns].sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1)),
    [backendRuns],
  );

  // ---- derivations -------------------------------------------------------
  const effectiveCreatedAt = createdAt ?? new Date(0).toISOString();
  const exceptions = toExceptions(results, effectiveCreatedAt, priorityQueues, cases);
  const communications = toCommunications(results, effectiveCreatedAt);
  const dashboardStats = metrics ? toDashboardStats(metrics) : null;
  const analyticsData = metrics ? toAnalyticsData(metrics, results) : null;
  const activities = toActivityLog(audit);

  const clearView = useCallback(() => {
    setResults([]);
    setMetrics(null);
    setPriorityQueues(null);
    setAudit([]);
    setQuarantined([]);
    setCases({});
  }, []);

  // ---- run history list (GET /v1/runs, DB-backed) ------------------------
  const loadRuns = useCallback(async () => {
    try {
      const res = await api.listRuns();
      setBackendRuns(
        res.runs.map((r) => ({
          runId: r.run_id,
          tenantId: r.tenant_id,
          status: r.status,
          createdAt: r.created_at,
          rowsAccepted: r.rows_accepted,
          rowsQuarantined: r.rows_quarantined,
        })),
      );
      setCreatedAt((prev) => prev ?? res.runs.find((r) => r.run_id === runId)?.created_at ?? null);
    } catch (e) {
      // History is non-critical chrome — never blast a global error (e.g. a
      // transient 401 during the Clerk-load window on refresh).
      console.warn('loadRuns failed:', e instanceof ApiError ? e.message : e);
    }
  }, [runId]);

  // ---- data fetch (from the backend) after a run is terminal -------------
  const fetchRunData = useCallback(async (id: string) => {
    setIsLoadingData(true);
    try {
      const [resultsRes, metricsRes, auditRes, casesRes] = await Promise.all([
        api.getResults(id),
        api.getMetrics(id),
        api.getAudit(id).catch(() => ({ run_id: id, events: [] })),
        api.getCases(id).catch(() => ({ run_id: id, cases: {} })),
      ]);
      setResults(resultsRes.results);
      setMetrics(metricsRes.metrics);
      setPriorityQueues(metricsRes.priority_queues);
      setAudit(auditRes.events);
      setCases(casesRes.cases);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setIsLoadingData(false);
    }
  }, []);

  // ---- polling -----------------------------------------------------------
  const stopPolling = useCallback(() => {
    if (pollTimer.current) {
      clearTimeout(pollTimer.current);
      pollTimer.current = null;
    }
  }, []);

  const poll = useCallback(
    async (id: string) => {
      try {
        const detail = await api.getRun(id);
        setStatus(detail.status);
        setCurrentNode(detail.current_node ?? null);
        setRowsAccepted(detail.rows_accepted);
        setRowsQuarantined(detail.rows_quarantined);
        setQuarantined(detail.quarantined ?? []);

        if (TERMINAL_STATUSES.includes(detail.status)) {
          stopPolling();
          if (detail.status !== 'FAILED') {
            await fetchRunData(id);
          } else {
            // Surface the *actual* reason the backend recorded (e.g. a missing
            // required column) instead of a generic "check the logs" message.
            const reasons = (detail.errors ?? [])
              .map((e) => e?.message?.trim())
              .filter((m): m is string => Boolean(m));
            setError(
              reasons.length > 0
                ? `Upload couldn't be processed: ${reasons.join(' ')}`
                : 'Run failed during processing. Check the backend logs.',
            );
          }
          // Refresh the history list so the run's final status is reflected.
          void loadRuns();
          return;
        }
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) {
          // Stale active-run pointer: the run id persisted in localStorage no
          // longer exists on the backend (e.g. a previous session, or the
          // in-memory run store was cleared on a backend restart). Don't show a
          // scary error on a fresh dashboard visit — just clear the pointer and
          // fall back to the empty / upload state.
          stopPolling();
          localStorage.removeItem(RUN_ID_KEY);
          setRunId(null);
          setStatus(null);
          setCurrentNode(null);
          clearView();
          console.warn(`Active run ${id} not found on the backend — cleared stale pointer.`);
          return;
        }
        setError(e instanceof ApiError ? e.message : String(e));
      }
      pollTimer.current = setTimeout(() => void poll(id), POLL_INTERVAL_MS);
    },
    [fetchRunData, stopPolling, loadRuns, clearView],
  );

  // Resume / switch run: fetch everything fresh from the backend (once signed in).
  useEffect(() => {
    if (!runId || !authReady) return;
    void poll(runId);
    return stopPolling;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, authReady]);

  // Load the run history once the user is authenticated.
  useEffect(() => {
    if (authReady) void loadRuns();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authReady]);

  // ---- actions -----------------------------------------------------------
  const uploadFile = useCallback(
    async (file: File, tenantId?: string) => {
      setIsUploading(true);
      setError(null);
      // Reset the *active view* only — previous runs remain in the backend history.
      clearView();
      stopPolling();
      try {
        const summary = await api.createRun(file, tenantId);
        localStorage.setItem(RUN_ID_KEY, summary.run_id);
        setCreatedAt(summary.created_at);
        setStatus(summary.status);
        setRowsAccepted(summary.rows_accepted);
        setRowsQuarantined(summary.rows_quarantined);
        setRunId(summary.run_id); // triggers the polling effect
        void loadRuns();
      } catch (e) {
        setError(e instanceof ApiError ? e.message : String(e));
        throw e;
      } finally {
        setIsUploading(false);
      }
    },
    [stopPolling, loadRuns, clearView],
  );

  const selectRun = useCallback(
    (id: string) => {
      if (id === runId) return;
      stopPolling();
      setError(null);
      clearView();
      // Seed status/createdAt from the history entry for instant display; the
      // polling effect then fetches the full run fresh from the backend.
      const entry = history.find((r) => r.runId === id);
      setStatus(entry?.status ?? null);
      setCreatedAt(entry?.createdAt ?? null);
      setRowsAccepted(entry?.rowsAccepted ?? 0);
      setRowsQuarantined(entry?.rowsQuarantined ?? 0);
      localStorage.setItem(RUN_ID_KEY, id);
      setRunId(id);
    },
    [runId, history, stopPolling, clearView],
  );

  const refresh = useCallback(async () => {
    if (!runId) return;
    await poll(runId);
  }, [runId, poll]);

  const reloadData = useCallback(async () => {
    if (!runId) return;
    await fetchRunData(runId);
  }, [runId, fetchRunData]);

  const approve = useCallback(async () => {
    if (!runId) return;
    await api.approveRun(runId);
    setStatus('COMPLETED');
    await fetchRunData(runId);
    void loadRuns();
  }, [runId, fetchRunData, loadRuns]);

  const updateCaseStatus = useCallback(
    async (invoiceId: string, status: CaseStatus, note?: string) => {
      if (!runId) return;
      const res = await api.updateCase(runId, invoiceId, status, note);
      // Update the shared map so exceptions/SLA/dashboard recompute immediately.
      setCases((c) => ({ ...c, [invoiceId]: res.case }));
    },
    [runId],
  );

  const clearRun = useCallback(() => {
    // Clears the *active* run only — backend history is untouched.
    stopPolling();
    localStorage.removeItem(RUN_ID_KEY);
    setRunId(null);
    setStatus(null);
    setCurrentNode(null);
    setCreatedAt(null);
    setRowsAccepted(0);
    setRowsQuarantined(0);
    clearView();
    setError(null);
  }, [stopPolling, clearView]);

  // Dismiss a transient error banner *without* discarding the active run (used
  // when the run itself is fine but a one-off fetch/upload error surfaced).
  const clearError = useCallback(() => setError(null), []);

  const clearHistory = useCallback(() => {
    // History lives in the backend DB; re-fetch it rather than clearing locally.
    void loadRuns();
  }, [loadRuns]);

  const value: RunContextValue = {
    runId,
    status,
    currentNode,
    createdAt,
    rowsAccepted,
    rowsQuarantined,
    quarantined,
    history,
    isUploading,
    isProcessing,
    isLoadingData,
    error,
    results,
    metrics,
    priorityQueues,
    audit,
    cases,
    exceptions,
    communications,
    dashboardStats,
    analyticsData,
    activities,
    uploadFile,
    refresh,
    reloadData,
    loadRuns,
    selectRun,
    approve,
    updateCaseStatus,
    clearRun,
    clearError,
    clearHistory,
  };

  return <RunContext.Provider value={value}>{children}</RunContext.Provider>;
}

export function useRun(): RunContextValue {
  const ctx = useContext(RunContext);
  if (!ctx) throw new Error('useRun must be used within a RunProvider');
  return ctx;
}
