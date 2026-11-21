import { ApiError } from "@/lib/api/errors";

export default function ErrorBanner({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  return (
    <div className="banner banner-error" role="alert">
      <div>
        <strong>{error.userMessage}</strong>
        <div className="muted small">
          {error.status ? `Code ${error.status} · ${error.code}` : error.code}
          {error.requestId ? ` · réf. ${error.requestId}` : ""}
        </div>
      </div>
      {onRetry && <button className="btn btn-light" onClick={onRetry}>Réessayer</button>}
    </div>
  );
}
