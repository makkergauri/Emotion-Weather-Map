/**
 * Every call to the backend goes through here.
 *
 * No data-fetching library: there are four endpoints, none of them paginated,
 * and the only real requirements are "don't set state after unmount" and "let
 * the user retry". A small hook covers that; React Query would be a dependency
 * carrying features this app never uses.
 */

import { useCallback, useEffect, useState } from 'react';
import type {
  CityDetail,
  CityRef,
  CountryDetail,
  CountrySummary,
  GlobalSummary,
} from '../types';

// Empty in development — Vite proxies /api to the backend (see vite.config.ts).
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '';

export interface Resource<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

async function getJson<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { signal });
  if (!response.ok) {
    // The backend sends { detail } on 4xx; anything else gets a generic line
    // rather than dumping a stack trace into the UI.
    const detail = await response
      .json()
      .then((body) => body?.detail)
      .catch(() => null);
    throw new Error(detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

/**
 * Fetch `path` whenever it changes. A null path means "nothing to load yet",
 * which is how the detail hooks stay idle until something is selected.
 */
function useResource<T>(path: string | null): Resource<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!path) {
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }

    // Aborting on cleanup matters here: clicking through three countries
    // quickly would otherwise let a slow first response overwrite the third.
    const controller = new AbortController();
    setLoading(true);
    setError(null);

    getJson<T>(path, controller.signal)
      .then((body) => {
        setData(body);
        setLoading(false);
      })
      .catch((err: Error) => {
        if (err.name === 'AbortError') return;
        setError(err.message);
        setLoading(false);
      });

    return () => controller.abort();
  }, [path, attempt]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  return { data, loading, error, reload };
}

/** All supported countries with their current condition — powers the world map. */
export function useCountries(): Resource<CountrySummary[]> {
  return useResource<CountrySummary[]>('/api/countries');
}

/** Full detail for one country. Pass null when nothing is selected. */
export function useCountryDetail(code: string | null): Resource<CountryDetail> {
  return useResource<CountryDetail>(code ? `/api/countries/${code}` : null);
}

/**
 * Full detail for one city. The country code is passed along because city names
 * are not guaranteed unique across the catalogue.
 */
export function useCityDetail(
  name: string | null,
  countryCode: string | null,
): Resource<CityDetail> {
  const path =
    name && countryCode
      ? `/api/cities/${encodeURIComponent(name)}?country=${countryCode}`
      : null;
  return useResource<CityDetail>(path);
}

/** Planet mood for the header readout. */
export function useGlobalSummary(): Resource<GlobalSummary> {
  return useResource<GlobalSummary>('/api/global-summary');
}

export interface CityWeatherMap {
  readings: Record<string, CityDetail>;
  pending: number;
}

/**
 * Load the weather for every city in a country, filling in as each lands.
 *
 * Unlike countries, cities aren't pre-warmed — there are up to 60 of them and
 * warming all of them on boot would mean 60 RSS requests nobody asked for. So
 * the drill-down pays the cost for the five cities you actually opened, and the
 * pins resolve one by one instead of the view blocking on the slowest feed.
 */
export function useCitiesWeather(
  countryCode: string | null,
  cities: CityRef[],
): CityWeatherMap {
  const [readings, setReadings] = useState<Record<string, CityDetail>>({});
  const [pending, setPending] = useState(0);

  // Cities arrive as a new array on every render of the parent, so the effect
  // keys off a stable string instead of the array identity.
  const cityKey = cities.map((c) => c.name).join('|');

  useEffect(() => {
    setReadings({});
    if (!countryCode || cities.length === 0) {
      setPending(0);
      return;
    }

    const controller = new AbortController();
    setPending(cities.length);

    cities.forEach((city) => {
      const path = `/api/cities/${encodeURIComponent(city.name)}?country=${countryCode}`;
      getJson<CityDetail>(path, controller.signal)
        .then((detail) => {
          setReadings((current) => ({ ...current, [city.name]: detail }));
        })
        .catch(() => {
          // One unreachable city shouldn't disturb the other four; it simply
          // keeps its pending pin until the view is left.
        })
        .finally(() => {
          if (!controller.signal.aborted) setPending((n) => Math.max(0, n - 1));
        });
    });

    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [countryCode, cityKey]);

  return { readings, pending };
}
