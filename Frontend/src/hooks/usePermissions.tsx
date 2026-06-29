/**
 * PermissionsProvider — the authoritative RBAC state for the console.
 *
 * Roles and permissions are owned by the backend (app/api/roles.py). Rather than
 * re-derive the role → permission matrix in the browser (which would drift), we
 * fetch the caller's effective permissions once from GET /v1/me and gate the UI
 * on those. The backend still enforces every mutation — this layer is UX only:
 * it disables controls a role can't use and explains why.
 *
 * Until /v1/me resolves (and if it ever fails — e.g. an older backend without
 * the endpoint), `can()` is optimistic and returns true. That keeps the UI from
 * bricking; the server remains the real gate and surfaces a 403 if the action
 * truly isn't allowed.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { useAuth } from '@clerk/react';
import { api, ApiError, type Me, type Permission, type Role } from '@/lib/api';

interface PermissionsContextValue {
  /** Resolved role, or null until /v1/me returns (or if it failed). */
  role: Role | null;
  /** True once /v1/me has resolved at least once. */
  loaded: boolean;
  /** Whether the current caller may perform `permission`. Optimistic pre-load. */
  can: (permission: Permission) => boolean;
}

const PermissionsContext = createContext<PermissionsContextValue | null>(null);

export function PermissionsProvider({ children }: { children: React.ReactNode }) {
  const { isLoaded, isSignedIn } = useAuth();
  const authReady = isLoaded && isSignedIn;

  const [me, setMe] = useState<Me | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!authReady) return;
    let cancelled = false;
    void (async () => {
      try {
        const result = await api.me();
        if (!cancelled) setMe(result);
      } catch (e) {
        // Non-fatal: keep optimistic gating; the backend still enforces.
        console.warn('permissions: /v1/me failed:', e instanceof ApiError ? e.message : e);
      } finally {
        if (!cancelled) setLoaded(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [authReady]);

  const can = useCallback(
    (permission: Permission): boolean => {
      // Optimistic until we actually know the caller's permissions.
      if (!me) return true;
      return me.permissions.includes(permission);
    },
    [me],
  );

  const value = useMemo<PermissionsContextValue>(
    () => ({ role: me?.role ?? null, loaded, can }),
    [me, loaded, can],
  );

  return (
    <PermissionsContext.Provider value={value}>{children}</PermissionsContext.Provider>
  );
}

export function usePermissions(): PermissionsContextValue {
  const ctx = useContext(PermissionsContext);
  if (!ctx) {
    throw new Error('usePermissions must be used within a PermissionsProvider');
  }
  return ctx;
}
