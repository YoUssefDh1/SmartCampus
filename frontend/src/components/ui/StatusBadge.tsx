import { VISIBILITIES } from "@/lib/catalog";
import type { Visibility } from "@/types/api";

/** Ce que voit réellement le candidat : En ligne / Programmé / Expiré / Brouillon / Archivé. */
export default function StatusBadge({ visibility }: { visibility: Visibility }) {
  const v = VISIBILITIES[visibility];
  return <span className={`badge badge-${visibility}`} title={v.hint}>{v.label}</span>;
}

export function ActiveBadge({ active }: { active: boolean }) {
  return <span className={`badge ${active ? "badge-visible" : "badge-archived"}`}>{active ? "Active" : "Inactive"}</span>;
}
