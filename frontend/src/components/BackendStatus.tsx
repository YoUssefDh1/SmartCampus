"use client";
import { healthApi } from "@/lib/api/services";
import { useApi } from "@/lib/api/useApi";
import ErrorBanner from "./ErrorBanner";

export default function BackendStatus() {
  const { data, error, loading, reload } = useApi(healthApi.check);
  if (loading) return <div className="banner">Vérification du backend…</div>;
  if (error) return <ErrorBanner error={error} onRetry={reload} />;
  return (
    <div className="banner banner-ok">
      Backend connecté · {data?.app} v{data?.version} ({data?.environment})
    </div>
  );
}
