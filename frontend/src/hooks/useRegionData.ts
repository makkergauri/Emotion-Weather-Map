/**
 * Every call to the backend goes through here.
 *
 * No data-fetching library: there are four endpoints, none of them paginated.
 * The requirements are small but specific — don't set state after unmount, let
 * the user retry, survive a server that is still waking up, and keep asking
 * while the cache fills. A small hook covers all four; React Query would be a
 * dependency carrying features this app never uses.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type {
  CityDetail,
  CityRef,
  CountryDetail,
  CountrySummary,
  GlobalSummary,
} from '../types';

// Empty in development — Vite proxies /api to the backend (see vite.config.ts).
// In production it must be set at build time to the backend's origin. A
// trailing slash is stripped, because "https://api.example.com/" + "/api/..."
// produces a double slash that some hosts answer with a 404.
const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '');

/**
 * Free hosting puts an idle backend to sleep, and the first request after that
 * can take the best part of a minute to answer. Rather than show an error to
 * someone who simply arrived at a quiet moment, the initial loads retry for
 * roughly that long before giving up.
 */
const COLD_START = { retries: 12, retryDelayMs: 5000 };

/**
 * After a cold start the backend answers immediately but with every country
 * still grey, and fills them in over the next thirty seconds or so. The map
 * polls while that is happening, then stops. The limit exists so a country that
 * genuinely can't be reached doesn't keep the page polling forever.
 */
const WARMUP_POLL_MS = 5000;
const WARMUP_POLL_LIMIT = 36; // three minutes

export interface Resource<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  /** True while an automatic retry is pending — i.e. the server is waking up. */
  retrying: boolean;
  reload: () => void;
}

interface RetryOptions {
  retries?: number;
  retryDelayMs?: number;
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
function useResource<T>(
  path: string | null,
  { retries = 0, retryDelayMs = 5000 }: RetryOptions = {},
): Resource<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [tick, setTick] = useState(0);

  // A ref, not state: bumping it must not itself trigger another fetch.
  const retriesUsed = useRef(0);

  useEffect(() => {
    retriesUsed.current = 0;
  }, [path]);

  useEffect(() => {
    if (!path) {
      setData(null);
      setError(null);
      setLoading(false);
      setRetrying(false);
      return;
    }

    // Aborting on cleanup matters here: clicking through three countries
    // quickly would otherwise let a slow first response overwrite the third.
    const controller = new AbortController();
    let retryTimer: number | undefined;
    setLoading(true);
    setError(null);

    getJson<T>(path, controller.signal)
      .then((body) => {
        retriesUsed.current = 0;
        setData(body);
        setLoading(false);
        setRetrying(false);
      })
      .catch((err: Error) => {
        if (err.name === 'AbortError') return;

        if (retriesUsed.current < retries) {
          retriesUsed.current += 1;
          setRetrying(true);
          retryTimer = window.setTimeout(() => setTick((n) => n + 1), retryDelayMs);
          return;
        }

        setRetrying(false);
        setError(err.message);
        setLoading(false);
      });

    return () => {
      controller.abort();
      window.clearTimeout(retryTimer);
    };
    // retries and retryDelayMs are fixed per call site, so they're left out.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, tick]);

  const reload = useCallback(() => {
    retriesUsed.current = 0;
    setTick((n) => n + 1);
  }, []);

  return { data, loading, error, retrying, reload };
}

export interface CountriesResource extends Resource<CountrySummary[]> {
  /** Some countries are still grey and the map is polling for them. */
  warming: boolean;
}

/** All supported countries with their current condition — powers the world map. */
export function useCountries(): CountriesResource {
  const resource = useResource<CountrySummary[]>('/api/countries', COLD_START);
  const { data, reload } = resource;
  const [polls, setPolls] = useState(0);

  const stillGrey = data?.some((c) => c.condition === 'no_data') ?? false;
  const warming = stillGrey && polls < WARMUP_POLL_LIMIT;

  useEffect(() => {
    if (!warming) return;
    const timer = window.setTimeout(() => {
      setPolls((n) => n + 1);
      reload();
    }, WARMUP_POLL_MS);
    return () => window.clearTimeout(timer);
  }, [warming, data, reload]);

  return { ...resource, warming };
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
  return useResource<GlobalSummary>('/api/global-summary', COLD_START);
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