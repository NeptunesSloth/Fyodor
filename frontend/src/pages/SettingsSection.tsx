import type { ReactNode } from "react";
import { sectionById } from "./settingsBits";

/** One section of the Settings page: a short heading and its one-line explanation (settingsBits.SETTINGS_SECTIONS), then its rows. */
export function SettingsSection({ id, children, testId, className }: { id: string; children: ReactNode; testId?: string; className?: string }) {
  const s = sectionById(id);
  return (
    <section id={id} className={`st-section ${className ?? ""}`} data-testid={testId} aria-labelledby={`${id}-title`}>
      <header className="st-head">
        <h2 id={`${id}-title`}>{s.title}</h2>
        <p>{s.blurb}</p>
      </header>
      {children}
    </section>
  );
}
