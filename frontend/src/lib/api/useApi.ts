"use client";
// Hook de chargement : gère état « chargement / données / erreur » pour tous les écrans.
import { useCallback, useEffect, useState } from "react";
import { ApiError } from "./errors";

export function useApi<T>(fetcher: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setData(await fetcher()); }
    catch (e) { setError(e instanceof ApiError ? e : new ApiError(0, "UNKNOWN", String(e))); }
    finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { load(); }, [load]);
  return { data, error, loading, reload: load };
}
