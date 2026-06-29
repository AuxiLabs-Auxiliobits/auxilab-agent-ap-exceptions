/**
 * Client-side UI preferences, persisted to localStorage. These genuinely
 * apply across the app:
 *   - defaultView : where "/" redirects after login
 *   - pageSize    : rows per page in the Exception Queue table
 *
 * (Theme is handled separately by useTheme.) These are browser-local
 * preferences only — they never touch backend configuration.
 */
import { createContext, useCallback, useContext, useEffect, useState } from 'react';

export interface Preferences {
  defaultView: string;
  pageSize: number;
}

export const DEFAULT_PREFERENCES: Preferences = {
  defaultView: '/dashboard',
  pageSize: 10,
};

const STORAGE_KEY = 'ap-preferences';

function load(): Preferences {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_PREFERENCES;
    return { ...DEFAULT_PREFERENCES, ...(JSON.parse(raw) as Partial<Preferences>) };
  } catch {
    return DEFAULT_PREFERENCES;
  }
}

interface PreferencesContextValue {
  preferences: Preferences;
  setPreferences: (patch: Partial<Preferences>) => void;
  reset: () => void;
}

const PreferencesContext = createContext<PreferencesContextValue | null>(null);

export function PreferencesProvider({ children }: { children: React.ReactNode }) {
  const [preferences, setPrefs] = useState<Preferences>(load);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences));
  }, [preferences]);

  const setPreferences = useCallback((patch: Partial<Preferences>) => {
    setPrefs((prev) => ({ ...prev, ...patch }));
  }, []);

  const reset = useCallback(() => setPrefs(DEFAULT_PREFERENCES), []);

  return (
    <PreferencesContext.Provider value={{ preferences, setPreferences, reset }}>
      {children}
    </PreferencesContext.Provider>
  );
}

export function usePreferences(): PreferencesContextValue {
  const ctx = useContext(PreferencesContext);
  if (!ctx) throw new Error('usePreferences must be used within a PreferencesProvider');
  return ctx;
}
