// Libellés français et formats du catalogue (une seule source pour toutes les pages).
import type {
  Cycle, FeeType, PaymentMethod, PublicationStatus, RequirementCategory, RequirementKind, Visibility,
} from "@/types/api";

export const CYCLES: Record<Cycle, string> = {
  preparatory: "Préparatoire", engineering: "Ingénierie", bachelor: "Licence", master: "Master", other: "Autre",
};

export const FEE_TYPES: Record<FeeType, string> = {
  application: "Frais de dossier", registration: "Frais d'inscription", tuition: "Frais de scolarité",
  other: "Autres frais",
};

export const REQUIREMENT_CATEGORIES: Record<RequirementCategory, string> = {
  admission: "Condition d'admission", prerequisite: "Prérequis",
};

export const REQUIREMENT_KINDS: Record<RequirementKind, string> = {
  bac_series: "Série du baccalauréat", minimum_average: "Moyenne minimale", prior_diploma: "Diplôme requis",
  entrance_exam: "Concours / entretien", document: "Pièce à fournir", skill: "Compétence", other: "Autre",
};

export const PAYMENT_METHODS: Record<PaymentMethod, string> = {
  cash: "Espèces", bank_transfer: "Virement", check: "Chèque", card: "Carte bancaire", online: "Paiement en ligne",
};

export const STATUSES: Record<PublicationStatus, string> = {
  draft: "Brouillon", published: "Publié", archived: "Archivé",
};

export const VISIBILITIES: Record<Visibility, { label: string; hint: string }> = {
  visible: { label: "En ligne", hint: "Publié et valide aujourd'hui : visible par les candidats et l'agent IA" },
  scheduled: { label: "Programmé", hint: "Publié, mais la période de validité n'a pas commencé" },
  expired: { label: "Expiré", hint: "Publié, mais la période de validité est terminée" },
  draft: { label: "Brouillon", hint: "Non publié : invisible pour les candidats" },
  archived: { label: "Archivé", hint: "Historique : invisible et non modifiable" },
};

export const LANGUAGES: Record<string, string> = { fr: "Français", en: "Anglais", ar: "Arabe" };

export function money(amount: number | null | undefined, currency = "TND"): string {
  if (amount === null || amount === undefined) return "—";
  return `${new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 0, maximumFractionDigits: 3 }).format(amount)} ${currency}`;
}

export function day(value: string | null | undefined): string {
  if (!value) return "—";
  const [y, m, d] = value.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
}

export function validity(from: string | null, until: string | null): string {
  if (!from && !until) return "Sans limite";
  if (from && until) return `${day(from)} → ${day(until)}`;
  return from ? `À partir du ${day(from)}` : `Jusqu'au ${day(until)}`;
}

/** Année universitaire en cours : septembre -> août (nov. 2026 => 2026-2027). */
export function currentAcademicYear(now = new Date()): string {
  const y = now.getFullYear();
  return now.getMonth() >= 8 ? `${y}-${y + 1}` : `${y - 1}-${y}`;
}

export function academicYears(count = 4): string[] {
  const start = Number(currentAcademicYear().slice(0, 4)) - 1;
  return Array.from({ length: count }, (_, i) => `${start + i}-${start + i + 1}`);
}

/** Champs de formulaire -> valeurs API : "" => null, nombres convertis. */
export const blankToNull = (v: string): string | null => (v.trim() === "" ? null : v.trim());
export const toNumber = (v: string): number | null => (v.trim() === "" ? null : Number(v.replace(",", ".")));
export const str = (v: string | number | null | undefined): string => (v === null || v === undefined ? "" : String(v));
