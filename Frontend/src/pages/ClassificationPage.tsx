import { useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { ClassificationPanel } from '@/components/classification/ClassificationPanel';
import { InvoiceCombobox } from '@/components/classification/InvoiceCombobox';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Sparkles } from 'lucide-react';
import { useRun } from '@/hooks/useRun';
import { toException } from '@/lib/adapters';
import type { Exception } from '@/types';

export function ClassificationPage() {
  const { results, createdAt, runId } = useRun();
  const [selectedInvoice, setSelectedInvoice] = useState('');

  const invoiceIndex = useMemo(() => {
    const map = new Map<string, (typeof results)[number]>();
    for (const r of results) map.set(r.invoice_id.toUpperCase(), r);
    return map;
  }, [results]);

  const invoiceOptions = useMemo(
    () => results.map((r) => ({ id: r.invoice_id, vendor: r.row?.vendor_name })),
    [results],
  );

  // The result panel is derived directly from the selected invoice — picking (or
  // typing an exact) invoice shows the classification immediately, with no
  // separate "View Classification" button. An exact match that has no
  // classification surfaces the "not found" note; a partial/typing value just
  // shows the empty placeholder (the combobox itself lists the matches).
  const { analysis, notFound } = useMemo<{
    analysis: Exception | null;
    notFound: boolean;
  }>(() => {
    const key = selectedInvoice.trim().toUpperCase();
    if (!key) return { analysis: null, notFound: false };
    const item = invoiceIndex.get(key);
    if (!item) return { analysis: null, notFound: false };
    if (!item.classification) return { analysis: null, notFound: true };
    return {
      analysis: toException(item, createdAt ?? new Date(0).toISOString(), new Map()),
      notFound: false,
    };
  }, [selectedInvoice, invoiceIndex, createdAt]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold tracking-tight">AI Classification</h1>
        <p className="text-muted-foreground mt-1">
          Inspect the agent's classification for any invoice in the current run
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Look up Exception</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Invoice ID</label>
              <InvoiceCombobox
                value={selectedInvoice}
                onChange={setSelectedInvoice}
                options={invoiceOptions}
                placeholder="Select or type an Invoice ID (e.g., INV-2001)"
                disabled={results.length === 0}
              />
              {!runId && (
                <p className="text-xs text-muted-foreground">
                  Upload a queue on the Dashboard first.
                </p>
              )}
              {runId && results.length > 0 && (
                <p className="text-xs text-muted-foreground">
                  {results.length} invoices available — pick one to see its classification.
                </p>
              )}
            </div>

            {notFound && (
              <p className="text-sm text-pending">
                No classification found for that invoice ID in the current run.
              </p>
            )}
          </CardContent>
        </Card>

        <motion.div
          key={analysis?.invoiceId ?? 'empty'}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2 }}
        >
          {analysis ? (
            <ClassificationPanel
              exceptionType={analysis.exceptionType}
              rootCause={analysis.rootCause ?? '—'}
              confidence={analysis.confidence ?? 0}
              reasoning={analysis.reasoning ?? '—'}
              severity={analysis.severity}
            />
          ) : (
            <Card className="h-full flex items-center justify-center min-h-[400px]">
              <CardContent className="text-center">
                <Sparkles className="w-12 h-12 text-muted-foreground/50 mx-auto mb-4" />
                <p className="text-muted-foreground">
                  Select an Invoice ID to see the agent's classification
                </p>
              </CardContent>
            </Card>
          )}
        </motion.div>
      </div>
    </div>
  );
}
