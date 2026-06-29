import { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Upload, FileText, CheckCircle2, Loader2, Zap, AlertCircle, X, Download, ChevronDown,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { useRun } from '@/hooks/useRun';
import { usePermissions } from '@/hooks/usePermissions';
import { api } from '@/lib/api';

// Mirrors the backend canonical spec (app/upload_format.py) for at-a-glance
// reference. The authoritative machine-readable version is GET /v1/upload/format.
const REQUIRED_COLS: [string, string][] = [
  ['invoice_id', 'Unique ID · 1–64 chars'],
  ['vendor_name', 'Supplier name'],
  ['invoice_amount', 'Number ≥ 0 ($ , tolerated)'],
  ['exception_type', 'e.g. Price Variance, Missing PO'],
  ['exception_description', 'Free text'],
  ['days_outstanding · or · invoice_date', 'Age in days, or ISO date'],
];
const OPTIONAL_COLS: [string, string][] = [
  ['po_number', 'Purchase order'],
  ['approver_assigned', 'Approver name / email'],
];

function FormatReference() {
  return (
    <div className="mt-2 rounded-lg border bg-muted/40 p-3 text-xs">
      <p className="text-muted-foreground">
        Accepts <span className="font-medium text-foreground">.csv</span> or{' '}
        <span className="font-medium text-foreground">.json</span> · max 25 MB · common header
        aliases auto-map (e.g. “Invoice No” → <code className="font-mono">invoice_id</code>,
        “Supplier” → <code className="font-mono">vendor_name</code>).
      </p>
      <p className="mt-2.5 font-semibold">Required columns</p>
      <ul className="mt-1 space-y-0.5">
        {REQUIRED_COLS.map(([c, d]) => (
          <li key={c} className="flex justify-between gap-3">
            <code className="font-mono text-foreground">{c}</code>
            <span className="text-right text-muted-foreground">{d}</span>
          </li>
        ))}
      </ul>
      <p className="mt-2.5 font-semibold">Optional columns</p>
      <ul className="mt-1 space-y-0.5">
        {OPTIONAL_COLS.map(([c, d]) => (
          <li key={c} className="flex justify-between gap-3">
            <code className="font-mono text-foreground">{c}</code>
            <span className="text-right text-muted-foreground">{d}</span>
          </li>
        ))}
      </ul>
      <p className="mt-2.5 text-muted-foreground">
        <code className="font-mono">severity</code> &amp;{' '}
        <code className="font-mono">confidence_score</code> are computed by the agent — not required.
      </p>
    </div>
  );
}

export function UploadPanel() {
  const {
    uploadFile,
    isUploading,
    isProcessing,
    isLoadingData,
    status,
    currentNode,
    rowsAccepted,
    rowsQuarantined,
    error,
    runId,
    clearRun,
    clearError,
  } = useRun();

  const { can } = usePermissions();
  const canCreate = can('run:create');

  // Hand the user a clean slate after a rejected/failed upload. A FAILED run
  // leaves sticky chrome app-wide (the error banner, the sidebar "Run failed",
  // the header FAILED badge, and a localStorage pointer that survives refresh),
  // so we fully reset it; for a non-failed transient error we only clear the
  // banner and keep any good run intact.
  const resetAfterFailure = useCallback(() => {
    if (status === 'FAILED') clearRun();
    else clearError();
  }, [status, clearRun, clearError]);

  const [isDragging, setIsDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [showFormat, setShowFormat] = useState(false);
  // Tracks whether THIS panel has submitted the *currently selected* file.
  // It resets on every new selection — that's what lets a second/third upload
  // re-show the "Run AI Agent" button instead of being blocked by the previous
  // run's global status (the original bug).
  const [hasSubmitted, setHasSubmitted] = useState(false);
  // Client-side validation message for a rejected file (wrong type/empty/too big).
  const [fileError, setFileError] = useState<string | null>(null);

  const busy = isUploading || isProcessing || isLoadingData;

  // "done" is scoped to the file this panel submitted — NOT the global run
  // status. Without `hasSubmitted`, a freshly selected file would inherit the
  // previous run's AWAITING_REVIEW/COMPLETED status and look "already done".
  const done =
    hasSubmitted && !busy && (status === 'AWAITING_REVIEW' || status === 'COMPLETED');

  // Show the Run button whenever a file is selected and we haven't kicked it
  // off yet — independent of any previous run's state. Gated on the RBAC
  // run:create permission (the backend enforces it too).
  const canRun = !!file && !busy && !hasSubmitted && canCreate;

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  // Fast client-side gate. Returns an error message (negative case) or null
  // (positive case). Deeper row/schema validation happens on the backend, which
  // quarantines bad rows and reports the count back.
  const MAX_BYTES = 25 * 1024 * 1024; // mirrors the backend upload cap
  const validateFile = (f: File): string | null => {
    const okType =
      f.type === 'text/csv' ||
      f.type === 'application/json' ||
      /\.(csv|json)$/i.test(f.name);
    if (!okType) return 'Unsupported file type — upload a .csv or .json file.';
    if (f.size === 0) return 'That file is empty — there are no rows to process.';
    if (f.size > MAX_BYTES)
      return `File is too large (${(f.size / 1024 / 1024).toFixed(1)} MB). The limit is 25 MB.`;
    return null;
  };

  // Selecting a new file (drag OR browse) must reset the submission flag so the
  // Run button reappears for the new file.
  const selectNewFile = useCallback((f: File) => {
    setFile(f);
    setHasSubmitted(false);
    setFileError(null);
    // Starting over after a rejected upload must clear the previous failure so
    // its banner / "Run failed" status don't bleed into the new attempt.
    resetAfterFailure();
  }, [resetAfterFailure]);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const dropped = e.dataTransfer.files[0];
      if (!dropped) return;
      const err = validateFile(dropped);
      if (err) {
        setFileError(err);
        return;
      }
      selectNewFile(dropped);
    },
    // validateFile is pure; selectNewFile is the only reactive dep.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [selectNewFile],
  );

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    // Reset the input value so picking the SAME file again still fires onChange.
    // (A file input won't emit `change` if the chosen path is identical to its
    // current value — clearing it here removes that trap.)
    e.target.value = '';
    if (!selected) return;
    const err = validateFile(selected);
    if (err) {
      setFileError(err);
      return;
    }
    selectNewFile(selected);
  };

  // Clear the chosen file so a different one can be selected. Disabled mid-run.
  // Also resets a failed run so removing the file returns the whole UI to a
  // fresh state (no lingering error banner / "Run failed" chrome).
  const removeFile = useCallback(() => {
    setFile(null);
    setHasSubmitted(false);
    setFileError(null);
    resetAfterFailure();
  }, [resetAfterFailure]);

  const handleRunAI = async () => {
    if (!file || busy) return;
    setHasSubmitted(true); // lock the button + start showing progress
    try {
      // uploadFile() clears the previous run's results in context and starts a
      // brand-new run, so old data is replaced with the new upload's results.
      await uploadFile(file);
    } catch {
      // Upload failed before the run started — re-enable the button to retry.
      setHasSubmitted(false);
    }
  };

  const progressValue = isUploading ? 35 : isProcessing ? 70 : isLoadingData ? 90 : done ? 100 : 0;
  const progressLabel = isUploading
    ? 'Uploading…'
    : isProcessing
      ? `Processing${currentNode ? ` · ${currentNode}` : '…'}`
      : isLoadingData
        ? 'Loading results…'
        : done
          ? 'Complete'
          : '';

  return (
    <Card className="overflow-hidden">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Upload className="w-5 h-5 text-primary" />
          Upload exception queue
        </CardTitle>
      </CardHeader>
      <CardContent>
        {/* Drop zone shows only while NO file is selected; the file card replaces it. */}
        {!file && (
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={`relative border-2 border-dashed rounded-lg p-8 transition-all duration-300 ${
            isDragging
              ? 'border-primary bg-primary/5'
              : 'border-muted-foreground/25 hover:border-primary/50 hover:bg-primary/5'
          }`}
        >
          <div className="flex flex-col items-center justify-center text-center">
            <motion.div
              animate={{ scale: isDragging ? 1.1 : 1 }}
              transition={{ type: 'spring', stiffness: 300 }}
            >
              <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center mb-4">
                <Upload className="w-8 h-8 text-primary" />
              </div>
            </motion.div>

            <h3 className="text-lg font-semibold mb-1">
              {isDragging ? 'Drop to upload' : 'Drag & drop your file'}
            </h3>
            <p className="text-sm text-muted-foreground mb-4">
              Supports CSV or JSON files
            </p>

            <label>
              <input
                type="file"
                accept=".csv,.json"
                onChange={handleFileSelect}
                className="hidden"
                disabled={busy}
              />
              <Button variant="outline" className="cursor-pointer" disabled={busy} asChild>
                <span>Browse Files</span>
              </Button>
            </label>
          </div>
        </div>
        )}

        {!file && (
          <div className="mt-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <button
                type="button"
                onClick={() => void api.downloadTemplate().catch(() => {})}
                className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:underline"
              >
                <Download className="h-3.5 w-3.5" /> Download CSV template
              </button>
              <button
                type="button"
                onClick={() => setShowFormat((v) => !v)}
                aria-expanded={showFormat}
                className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
              >
                Accepted format
                <ChevronDown
                  className={`h-3.5 w-3.5 transition-transform ${showFormat ? 'rotate-180' : ''}`}
                />
              </button>
            </div>
            {showFormat && <FormatReference />}
          </div>
        )}

        {!file && fileError && (
          <div className="mt-4 flex items-start gap-2 p-3 rounded-lg bg-overdue/10 border border-overdue/25 text-sm text-overdue">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span className="break-words">{fileError}</span>
          </div>
        )}

        <AnimatePresence>
          {file && (
            <motion.div
              // Re-keying on the file identity remounts this block per file, so
              // its animation/state never carries over from a previous upload.
              key={`${file.name}-${file.size}-${file.lastModified}`}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 10 }}
              className="mt-4 p-4 rounded-lg bg-muted/50 border"
            >
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-md bg-ink text-ink-foreground flex items-center justify-center">
                  <FileText className="w-5 h-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium truncate">{file.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {(file.size / 1024).toFixed(2)} KB
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {done && <CheckCircle2 className="w-5 h-5 text-settled" />}
                  {!busy && (
                    <button
                      type="button"
                      onClick={removeFile}
                      aria-label="Remove selected file"
                      title="Remove file"
                      className="grid h-8 w-8 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>

              {!busy && (
                <p className="mt-2 text-xs text-muted-foreground">
                  Wrong file? Remove it with ✕ to choose a different file.
                </p>
              )}

              {(busy || done) && (
                <div className="mt-3">
                  <Progress value={progressValue} className="h-2" />
                  <p className="text-xs text-muted-foreground mt-1">{progressLabel}</p>
                </div>
              )}

              {done && (
                <div className="mt-2 space-y-2">
                  <p className="text-xs text-muted-foreground">
                    {rowsAccepted} rows accepted
                    {rowsQuarantined > 0 && `, ${rowsQuarantined} quarantined`}
                  </p>
                  {rowsQuarantined > 0 && runId && (
                    <button
                      type="button"
                      onClick={() => void api.downloadRejections(runId).catch(() => {})}
                      className="inline-flex items-center gap-1.5 text-xs font-medium text-overdue hover:underline"
                    >
                      <Download className="h-3.5 w-3.5" />
                      Download rejection file ({rowsQuarantined})
                    </button>
                  )}
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>

        {error && (
          <div className="mt-4 flex items-start gap-2 p-3 rounded-lg bg-overdue/10 border border-overdue/25 text-sm text-overdue">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span className="flex-1 break-words">{error}</span>
            <button
              type="button"
              onClick={resetAfterFailure}
              aria-label="Dismiss error"
              title="Dismiss"
              className="shrink-0 grid h-5 w-5 place-items-center rounded text-overdue/70 transition-colors hover:bg-overdue/10 hover:text-overdue focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {canRun && (
          <Button onClick={handleRunAI} className="w-full mt-4">
            <Zap className="w-4 h-4 mr-2" />
            Clear this queue
          </Button>
        )}

        {file && !busy && !hasSubmitted && !canCreate && (
          <div className="mt-4 flex items-start gap-2 p-3 rounded-lg bg-muted/60 border text-sm text-muted-foreground">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span className="break-words">
              Your role can’t start a run. Ask an AP Clerk, Manager, or Admin to process this queue.
            </span>
          </div>
        )}

        {busy && (
          <Button disabled className="w-full mt-4">
            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            {progressLabel}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
