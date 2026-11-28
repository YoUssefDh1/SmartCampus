// Erreur unique levée par le client API : le reste de l'application ne manipule jamais de réponse brute.
export class ApiError extends Error {
  status: number;
  code: string;
  details: unknown[];
  requestId: string | null;

  constructor(status: number, code: string, message: string, details: unknown[] = [], requestId: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }

  /** Message lisible par le candidat, selon le type d'erreur. */
  get userMessage(): string {
    switch (this.code) {
      case "NETWORK_ERROR": return "Impossible de joindre le serveur. Vérifiez que le backend est lancé.";
      case "TIMEOUT": return "Le serveur met trop de temps à répondre. Réessayez.";
      case "UNAUTHORIZED": return "Votre session a expiré. Veuillez vous reconnecter.";
      case "FORBIDDEN": return "Vous n'avez pas accès à cette ressource.";
      case "NOT_FOUND": return this.message || "Ressource introuvable.";
      case "VALIDATION_ERROR":
        return this.message && this.message !== "Données invalides." ? this.message : "Certaines données sont invalides.";
      case "CONFLICT": return this.message || "Cette opération entre en conflit avec des données existantes.";
      case "DATABASE_UNAVAILABLE": return "La base de données est injoignable. Vérifiez que PostgreSQL est lancé.";
      case "NOT_IMPLEMENTED": return "Cette fonctionnalité n'est pas encore disponible.";
      case "AI_UNAVAILABLE": return "L'assistant est momentanément indisponible. Réessayez dans un instant.";
      case "TOO_MANY_REQUESTS": return this.message || "Limite de messages atteinte. Réessayez plus tard.";
      default: return this.message || "Une erreur est survenue.";
    }
  }

  /** Détails de validation lisibles : « champ : problème ». */
  get detailMessages(): string[] {
    return this.details.flatMap((d) => {
      if (!d || typeof d !== "object") return [];
      const { field, issue } = d as { field?: string; issue?: string };
      if (!issue) return [];
      const text = issue.replace(/^Value error, /, "");
      return [field ? `${field} : ${text}` : text];
    });
  }
}
