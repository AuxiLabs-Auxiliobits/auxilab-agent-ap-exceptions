import { motion } from 'framer-motion';
import { Sparkles, TrendingUp, AlertTriangle, Brain } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';

interface ClassificationPanelProps {
  exceptionType: string;
  rootCause: string;
  confidence: number;
  reasoning: string;
  severity: 'High' | 'Medium' | 'Low';
}

export function ClassificationPanel({
  exceptionType,
  rootCause,
  confidence,
  reasoning,
  severity,
}: ClassificationPanelProps) {
  const severityColors = {
    High: 'bg-overdue',
    Medium: 'bg-pending',
    Low: 'bg-settled',
  };

  const severityBg = {
    High: 'bg-overdue/10 border-overdue/20',
    Medium: 'bg-pending/10 border-pending/20',
    Low: 'bg-settled/10 border-settled/20',
  };

  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-4">
        <CardTitle className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-ink text-ink-foreground flex items-center justify-center">
            <Brain className="w-4 h-4" />
          </div>
          AI Classification Analysis
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="grid grid-cols-2 gap-4">
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className={`p-4 rounded-xl border ${severityBg[severity]}`}
          >
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle className="w-4 h-4 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">
                Severity Level
              </span>
            </div>
            <div className="flex items-center gap-2">
              <div
                className={`w-3 h-3 rounded-full bg-gradient-to-br ${severityColors[severity]}`}
              />
              <span className="text-xl font-bold">{severity}</span>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="p-4 rounded-xl border bg-primary/5 border-primary/15"
          >
            <div className="flex items-center gap-2 mb-2">
              <Sparkles className="w-4 h-4 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">
                Exception Type
              </span>
            </div>
            <Badge variant="info" className="text-sm">
              {exceptionType}
            </Badge>
          </motion.div>
        </div>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="space-y-2"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-primary" />
              <span className="text-sm font-medium">Confidence Score</span>
            </div>
            <span className="text-2xl font-bold text-primary tabular-nums">
              {confidence}%
            </span>
          </div>
          <Progress value={confidence} className="h-3" />
          <p className="text-xs text-muted-foreground">
            AI confidence level for this classification
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="p-4 rounded-xl border bg-muted/50 space-y-2"
        >
          <h4 className="text-sm font-semibold">Root Cause Hypothesis</h4>
          <p className="text-sm text-muted-foreground">{rootCause}</p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="space-y-2"
        >
          <h4 className="text-sm font-semibold">AI Reasoning Summary</h4>
          <div className="p-4 rounded-xl border bg-primary/5 border-primary/10">
            <p className="text-sm text-muted-foreground leading-relaxed">
              {reasoning}
            </p>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 }}
          className="flex flex-wrap gap-2"
        >
          {['Pattern Match', 'Vendor History', 'Amount Threshold', 'Similarity: 94%'].map(
            (tag) => (
              <Badge key={tag} variant="secondary" className="text-xs">
                {tag}
              </Badge>
            )
          )}
        </motion.div>
      </CardContent>
    </Card>
  );
}
