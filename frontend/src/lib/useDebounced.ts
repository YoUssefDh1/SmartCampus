"use client";
import { useEffect, useState } from "react";

/** Valeur retardée (recherche lancée quand l'utilisateur arrête de taper). */
export function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}
