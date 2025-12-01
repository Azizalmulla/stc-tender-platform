"use client";

import { useState, useEffect, useCallback } from 'react';

const STORAGE_KEY = 'stc_saved_tenders';

export function useSavedTenders() {
  const [savedIds, setSavedIds] = useState<Set<number>>(new Set());
  const [isLoaded, setIsLoaded] = useState(false);

  // Load from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const ids = JSON.parse(stored) as number[];
        setSavedIds(new Set(ids));
      }
    } catch (e) {
      console.error('Failed to load saved tenders:', e);
    }
    setIsLoaded(true);
  }, []);

  // Save to localStorage whenever savedIds changes
  useEffect(() => {
    if (isLoaded) {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(savedIds)));
      } catch (e) {
        console.error('Failed to save tenders:', e);
      }
    }
  }, [savedIds, isLoaded]);

  const isSaved = useCallback((tenderId: number) => {
    return savedIds.has(tenderId);
  }, [savedIds]);

  const toggleSave = useCallback((tenderId: number) => {
    setSavedIds(prev => {
      const next = new Set(prev);
      if (next.has(tenderId)) {
        next.delete(tenderId);
      } else {
        next.add(tenderId);
      }
      return next;
    });
  }, []);

  const savedCount = savedIds.size;
  const savedTenderIds = Array.from(savedIds);

  return {
    isSaved,
    toggleSave,
    savedCount,
    savedTenderIds,
    isLoaded
  };
}
