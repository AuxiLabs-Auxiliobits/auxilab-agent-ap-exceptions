import { useState, useMemo, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { usePreferences } from '@/hooks/usePreferences';
import { motion } from 'framer-motion';
import { Search, Filter, ArrowUpDown, ChevronLeft, ChevronRight } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { formatCompactCurrency, formatCurrencyFull } from '@/lib/format';
import type { Exception, Severity, ExceptionStatus } from '@/types';

interface ExceptionTableProps {
  exceptions: Exception[];
}

export function ExceptionTable({ exceptions }: ExceptionTableProps) {
  const [searchParams] = useSearchParams();
  // Seed the search box from the Header's ?q= query param.
  const [search, setSearch] = useState(() => searchParams.get('q') ?? '');

  useEffect(() => {
    const q = searchParams.get('q');
    if (q !== null) setSearch(q);
  }, [searchParams]);
  const [severityFilter, setSeverityFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [sortField, setSortField] = useState<keyof Exception>('invoiceAmount');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const [currentPage, setCurrentPage] = useState(1);
  const { preferences } = usePreferences();
  const itemsPerPage = preferences.pageSize;

  // Snap back to page 1 whenever the page size or filters change so the
  // current page never points past the end of the list.
  useEffect(() => {
    setCurrentPage(1);
  }, [itemsPerPage, search, severityFilter, statusFilter]);

  const filteredExceptions = useMemo(() => {
    return exceptions.filter((exc) => {
      const matchesSearch =
        exc.invoiceId.toLowerCase().includes(search.toLowerCase()) ||
        exc.vendorName.toLowerCase().includes(search.toLowerCase());
      const matchesSeverity =
        severityFilter === 'all' || exc.severity === severityFilter;
      const matchesStatus = statusFilter === 'all' || exc.status === statusFilter;

      return matchesSearch && matchesSeverity && matchesStatus;
    });
  }, [exceptions, search, severityFilter, statusFilter]);

  const sortedExceptions = useMemo(() => {
    return [...filteredExceptions].sort((a, b) => {
      const aValue = a[sortField];
      const bValue = b[sortField];

      if (typeof aValue === 'string' && typeof bValue === 'string') {
        return sortDirection === 'asc'
          ? aValue.localeCompare(bValue)
          : bValue.localeCompare(aValue);
      }

      if (typeof aValue === 'number' && typeof bValue === 'number') {
        return sortDirection === 'asc' ? aValue - bValue : bValue - aValue;
      }

      return 0;
    });
  }, [filteredExceptions, sortField, sortDirection]);

  const paginatedExceptions = useMemo(() => {
    const start = (currentPage - 1) * itemsPerPage;
    return sortedExceptions.slice(start, start + itemsPerPage);
  }, [sortedExceptions, currentPage]);

  const totalPages = Math.ceil(filteredExceptions.length / itemsPerPage);

  const getSeverityBadge = (severity: Severity) => {
    const variants: Record<Severity, 'danger' | 'warning' | 'success'> = {
      High: 'danger',
      Medium: 'warning',
      Low: 'success',
    };
    return <Badge variant={variants[severity]}>{severity}</Badge>;
  };

  const getStatusBadge = (status: ExceptionStatus) => {
    const variants: Record<
      ExceptionStatus,
      'default' | 'secondary' | 'success' | 'warning' | 'info'
    > = {
      Pending: 'secondary',
      'In Progress': 'info',
      'Auto-Resolved': 'success',
      Escalated: 'warning',
      Resolved: 'default',
    };
    return <Badge variant={variants[status]}>{status}</Badge>;
  };

  const handleSort = (field: keyof Exception) => {
    if (field === sortField) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('desc');
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>Exception Queue</span>
          <div className="flex items-center gap-2">
            <Badge variant="secondary">{filteredExceptions.length} items</Badge>
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col md:flex-row gap-4 mb-6">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search by Invoice ID or Vendor..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-10"
            />
          </div>
          <div className="flex gap-2">
            <Select value={severityFilter} onValueChange={setSeverityFilter}>
              <SelectTrigger className="w-[140px]">
                <Filter className="w-4 h-4 mr-2" />
                <SelectValue placeholder="Severity" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Severities</SelectItem>
                <SelectItem value="High">High</SelectItem>
                <SelectItem value="Medium">Medium</SelectItem>
                <SelectItem value="Low">Low</SelectItem>
              </SelectContent>
            </Select>

            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-[160px]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Status</SelectItem>
                <SelectItem value="Pending">Pending</SelectItem>
                <SelectItem value="In Progress">In Progress</SelectItem>
                <SelectItem value="Auto-Resolved">Auto-Resolved</SelectItem>
                <SelectItem value="Escalated">Escalated</SelectItem>
                <SelectItem value="Resolved">Resolved</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="rounded-xl border overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-muted/50 sticky top-0">
                <tr>
                  {[
                    { key: 'invoiceId', label: 'Invoice ID' },
                    { key: 'vendorName', label: 'Vendor Name' },
                    { key: 'invoiceAmount', label: 'Amount' },
                    { key: 'exceptionType', label: 'Exception Type' },
                    { key: 'severity', label: 'Severity' },
                    { key: 'daysOutstanding', label: 'Days Outstanding' },
                    { key: 'assignedApprover', label: 'Assigned To' },
                    { key: 'status', label: 'Status' },
                  ].map(({ key, label }) => (
                    <th
                      key={key}
                      className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider cursor-pointer hover:bg-muted/80 transition-colors"
                      onClick={() => handleSort(key as keyof Exception)}
                    >
                      <div className="flex items-center gap-2">
                        {label}
                        <ArrowUpDown className="w-3 h-3" />
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {paginatedExceptions.map((exception, index) => (
                  <motion.tr
                    key={exception.id}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: index * 0.02 }}
                    className="hover:bg-muted/30 transition-colors"
                  >
                    <td className="px-4 py-3 text-sm font-mono">
                      {exception.invoiceId}
                    </td>
                    <td className="px-4 py-3 text-sm font-medium">
                      {exception.vendorName}
                    </td>
                    <td
                      className="px-4 py-3 text-sm font-semibold"
                      title={formatCurrencyFull(exception.invoiceAmount)}
                    >
                      {formatCompactCurrency(exception.invoiceAmount)}
                    </td>
                    <td className="px-4 py-3 text-sm">
                      {exception.exceptionType}
                    </td>
                    <td className="px-4 py-3">
                      {getSeverityBadge(exception.severity)}
                    </td>
                    <td className="px-4 py-3 text-sm">
                      {exception.daysOutstanding} days
                    </td>
                    <td className="px-4 py-3 text-sm">
                      {exception.assignedApprover}
                    </td>
                    <td className="px-4 py-3">
                      {getStatusBadge(exception.status)}
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="flex items-center justify-between mt-4">
          <p className="text-sm text-muted-foreground">
            Showing {(currentPage - 1) * itemsPerPage + 1} to{' '}
            {Math.min(currentPage * itemsPerPage, filteredExceptions.length)} of{' '}
            {filteredExceptions.length} exceptions
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setCurrentPage(currentPage - 1)}
              disabled={currentPage === 1}
            >
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setCurrentPage(currentPage + 1)}
              disabled={currentPage === totalPages}
            >
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
