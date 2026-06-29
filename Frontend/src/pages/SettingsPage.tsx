import { SettingsPanel } from '@/components/settings/SettingsPanel';

export function SettingsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold tracking-tight">Settings</h1>
        <p className="text-muted-foreground mt-1">
          Configure your LedgerClear agent
        </p>
      </div>

      <SettingsPanel />
    </div>
  );
}
