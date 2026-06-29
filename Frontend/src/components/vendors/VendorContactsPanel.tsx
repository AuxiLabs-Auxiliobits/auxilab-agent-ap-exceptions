import { useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Mail,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Search,
  Trash2,
  X,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { usePermissions } from '@/hooks/usePermissions';
import { api, ApiError, type VendorContact } from '@/lib/api';

const EMPTY = { vendor_name: '', email: '', contact_name: '' };
const PAGE_SIZE = 15;

function isEmail(v: string): boolean {
  const t = v.trim();
  return t.includes('@') && t.split('@').pop()!.includes('.');
}

export function VendorContactsPanel() {
  const { can } = usePermissions();
  const isAdmin = can('config:write');

  const [contacts, setContacts] = useState<VendorContact[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState({ ...EMPTY });
  const [editing, setEditing] = useState<string | null>(null); // vendor_name being edited, or null (new)
  const [busy, setBusy] = useState<string | null>(null); // 'save' | `del:<name>`
  const [formError, setFormError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(0);

  // Search + paginate so a directory of hundreds/thousands stays usable.
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!contacts) return [];
    if (!q) return contacts;
    return contacts.filter(
      (c) =>
        c.vendor_name.toLowerCase().includes(q) ||
        c.email.toLowerCase().includes(q) ||
        (c.contact_name ?? '').toLowerCase().includes(q),
    );
  }, [contacts, query]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages - 1);
  const pageItems = filtered.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listVendorContacts();
      setContacts(res.contacts);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      setContacts(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const resetForm = () => {
    setForm({ ...EMPTY });
    setEditing(null);
    setFormError(null);
  };

  const startEdit = (c: VendorContact) => {
    setForm({ vendor_name: c.vendor_name, email: c.email, contact_name: c.contact_name ?? '' });
    setEditing(c.vendor_name);
    setFormError(null);
  };

  const save = async () => {
    if (!form.vendor_name.trim()) return setFormError('Vendor name is required.');
    if (!isEmail(form.email)) return setFormError('Enter a valid email address.');
    setBusy('save');
    setFormError(null);
    try {
      await api.putVendorContact({
        vendor_name: form.vendor_name.trim(),
        email: form.email.trim(),
        contact_name: form.contact_name.trim() || null,
      });
      resetForm();
      await load();
    } catch (e) {
      setFormError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const remove = async (name: string) => {
    setBusy(`del:${name}`);
    try {
      await api.deleteVendorContact(name);
      if (editing === name) resetForm();
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center justify-between gap-2 text-base">
          <span className="flex items-center gap-2">
            <Mail className="w-4 h-4 text-primary" /> Vendor email directory
          </span>
          <Button variant="outline" size="sm" onClick={load} disabled={loading} className="gap-2">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </CardTitle>
        <p className="text-muted-foreground text-sm mt-1">
          Map each vendor to its AR email so a mixed-vendor upload routes every invoice to the right
          vendor. When several invoices go to one vendor, they’re sent as a single consolidated email.
          {!isAdmin && ' Read-only — admin (config:write) can edit.'}
        </p>
      </CardHeader>

      <CardContent className="space-y-4">
        {isAdmin && (
          <div className="rounded-lg border border-border/60 bg-muted/30 p-3 space-y-2">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              <Input
                placeholder="Vendor name"
                value={form.vendor_name}
                disabled={editing !== null || busy === 'save'}
                onChange={(e) => setForm((f) => ({ ...f, vendor_name: e.target.value }))}
              />
              <Input
                placeholder="vendor-ar@example.com"
                value={form.email}
                disabled={busy === 'save'}
                onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
              />
              <Input
                placeholder="Contact name (optional)"
                value={form.contact_name}
                disabled={busy === 'save'}
                onChange={(e) => setForm((f) => ({ ...f, contact_name: e.target.value }))}
              />
            </div>
            <div className="flex items-center gap-2">
              <Button size="sm" onClick={save} disabled={busy === 'save'} className="gap-2">
                {busy === 'save' ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : editing ? (
                  <Save className="w-4 h-4" />
                ) : (
                  <Plus className="w-4 h-4" />
                )}
                {editing ? 'Update' : 'Add vendor'}
              </Button>
              {editing && (
                <Button size="sm" variant="ghost" onClick={resetForm} disabled={busy === 'save'} className="gap-2">
                  <X className="w-4 h-4" /> Cancel
                </Button>
              )}
              {editing && (
                <span className="text-xs text-muted-foreground">
                  Editing <strong>{editing}</strong> (rename = delete + re-add)
                </span>
              )}
              {formError && <span className="text-xs text-overdue">{formError}</span>}
            </div>
          </div>
        )}

        {loading && (
          <div
            className="divide-y divide-border/60 rounded-lg border border-border/60"
            aria-busy="true"
          >
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="flex items-center justify-between gap-3 px-3 py-2">
                <div className="min-w-0 flex-1 space-y-1.5">
                  <Skeleton className="h-4 w-40" />
                  <Skeleton className="h-3 w-56" />
                </div>
                <Skeleton className="h-7 w-16 rounded-md" />
              </div>
            ))}
          </div>
        )}

        {error && !loading && (
          <div className="flex items-start gap-2 text-overdue text-sm">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span className="break-words">{error}</span>
          </div>
        )}

        {contacts && !loading && contacts.length === 0 && (
          <p className="text-sm text-muted-foreground py-2">
            No vendor emails configured yet.{' '}
            {isAdmin ? 'Add one above.' : 'An admin can add them above.'}
          </p>
        )}

        {contacts && contacts.length > 0 && (
          <>
            {/* Search — find a vendor without scrolling a long directory. */}
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Search vendor, email, or contact…"
                value={query}
                onChange={(e) => { setQuery(e.target.value); setPage(0); }}
                className="pl-9 h-9"
              />
            </div>

            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>{filtered.length} of {contacts.length} vendor{contacts.length === 1 ? '' : 's'}</span>
              {totalPages > 1 && <span>Page {safePage + 1} of {totalPages}</span>}
            </div>

            <div className="divide-y divide-border/60 rounded-lg border border-border/60">
              {pageItems.map((c) => (
                <div key={c.vendor_name} className="flex items-center justify-between gap-3 px-3 py-2">
                  <div className="min-w-0">
                    <div className="font-medium truncate">{c.vendor_name}</div>
                    <div className="text-sm text-muted-foreground truncate">
                      {c.email}
                      {c.contact_name ? ` · ${c.contact_name}` : ''}
                    </div>
                  </div>
                  {isAdmin ? (
                    <div className="flex items-center gap-1 shrink-0">
                      <Button size="sm" variant="ghost" onClick={() => startEdit(c)} className="gap-1">
                        <Pencil className="w-3.5 h-3.5" /> Edit
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => remove(c.vendor_name)}
                        disabled={busy === `del:${c.vendor_name}`}
                        className="gap-1 text-overdue"
                      >
                        {busy === `del:${c.vendor_name}` ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <Trash2 className="w-3.5 h-3.5" />
                        )}
                        Remove
                      </Button>
                    </div>
                  ) : (
                    <Badge variant="secondary" className="shrink-0">routed</Badge>
                  )}
                </div>
              ))}
              {pageItems.length === 0 && (
                <p className="px-3 py-6 text-center text-sm text-muted-foreground">
                  No vendors match “{query}”.
                </p>
              )}
            </div>

            {totalPages > 1 && (
              <div className="flex items-center justify-end gap-1">
                <Button size="sm" variant="outline" disabled={safePage === 0} onClick={() => setPage(safePage - 1)} className="gap-1">
                  <ChevronLeft className="w-4 h-4" /> Prev
                </Button>
                <Button size="sm" variant="outline" disabled={safePage >= totalPages - 1} onClick={() => setPage(safePage + 1)} className="gap-1">
                  Next <ChevronRight className="w-4 h-4" />
                </Button>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
