"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
export function useApi<T>(path: string, enabled = true) {
  return useQuery<T>({ queryKey: [path], queryFn: () => api<T>(path), enabled, refetchInterval: 60000 });
}
