/**
 * Display metadata for the five conditions, in one place.
 *
 * The thresholds are duplicated from backend/app/mapping/weather_mapper.py.
 * That duplication is deliberate and narrow: the legend has to state the scale
 * it's explaining, and shipping a whole config endpoint to move four numbers
 * across the wire would be worse. If the backend bands change, this list is the
 * one thing that has to follow.
 */

import type { WeatherCondition } from './types';

export interface ConditionMeta {
  id: WeatherCondition;
  label: string;
  /** CSS custom property holding this condition's colour. */
  colorVar: string;
  /** Lower bound of the band, for the legend. */
  min: number;
  /** Upper bound, exclusive. */
  max: number;
}

/** Brightest first — the order the legend reads top to bottom. */
export const CONDITIONS: ConditionMeta[] = [
  { id: 'sunny', label: 'Sunny', colorVar: '--sunny', min: 0.5, max: 1 },
  { id: 'partly_cloudy', label: 'Partly cloudy', colorVar: '--partly-cloudy', min: 0.15, max: 0.5 },
  { id: 'overcast', label: 'Overcast', colorVar: '--overcast', min: -0.15, max: 0.15 },
  { id: 'rainy', label: 'Rainy', colorVar: '--rainy', min: -0.5, max: -0.15 },
  { id: 'thunderstorm', label: 'Thunderstorm', colorVar: '--thunderstorm', min: -1, max: -0.5 },
];

const NO_DATA: ConditionMeta = {
  id: 'no_data',
  label: 'No data',
  colorVar: '--no-data',
  min: 0,
  max: 0,
};

export function conditionMeta(condition: WeatherCondition): ConditionMeta {
  return CONDITIONS.find((c) => c.id === condition) ?? NO_DATA;
}

export function conditionColor(condition: WeatherCondition): string {
  return `var(${conditionMeta(condition).colorVar})`;
}

export function conditionLabel(condition: WeatherCondition): string {
  return conditionMeta(condition).label;
}

/** Signed, fixed-width score for the monospace readouts: "-0.31", "+0.07". */
export function formatScore(score: number): string {
  return `${score >= 0 ? '+' : '\u2212'}${Math.abs(score).toFixed(2)}`;
}

/** Zulu time, as a weather station would report it. */
export function formatObservedAt(iso: string | null): string {
  if (!iso) return '--:--Z';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '--:--Z';
  const hh = String(date.getUTCHours()).padStart(2, '0');
  const mm = String(date.getUTCMinutes()).padStart(2, '0');
  return `${hh}:${mm}Z`;
}
