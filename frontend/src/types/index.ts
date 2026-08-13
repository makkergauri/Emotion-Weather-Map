/**
 * Mirrors backend/app/models.py.
 *
 * Hand-written rather than generated: the API has six response shapes and a
 * codegen step would be more machinery than it saves. If a field ever goes
 * missing at runtime, the culprit is a change on the Python side that didn't
 * get copied across.
 */

export type WeatherCondition =
  | 'sunny'
  | 'partly_cloudy'
  | 'overcast'
  | 'rainy'
  | 'thunderstorm'
  | 'no_data';

/** How much coverage sits behind a score. `none` means the source was unreachable. */
export type Confidence = 'high' | 'low' | 'none';

/**
 * Which feed a reading came from. Countries prefer 'newsapi' and fall back to
 * 'rss' when NewsAPI has no coverage; cities are always 'rss'. null means the
 * reading predates the label, or no source answered at all.
 */
export type Source = 'newsapi' | 'rss' | null;

export interface Headline {
  title: string;
  source: string;
  url: string | null;
  score: number;
}

export interface ForecastPoint {
  date: string;
  score: number;
  condition: WeatherCondition;
}

export interface CityRef {
  name: string;
  lat: number;
  lng: number;
}

interface RegionWeather {
  score: number;
  condition: WeatherCondition;
  headline_count: number;
  confidence: Confidence;
  source: Source;
  updated_at: string | null;
}

export interface CountrySummary extends RegionWeather {
  code: string;
  name: string;
  lat: number;
  lng: number;
}

export interface CountryDetail extends CountrySummary {
  /** [[south, west], [north, east]] — Leaflet's own bounds ordering. */
  bounds: [[number, number], [number, number]];
  headlines: Headline[];
  forecast: ForecastPoint[];
  cities: CityRef[];
}

export interface CitySummary extends RegionWeather {
  name: string;
  country_code: string;
  lat: number;
  lng: number;
}

export interface CityDetail extends CitySummary {
  country_name: string;
  headlines: Headline[];
}

export interface GlobalSummary {
  score: number;
  condition: WeatherCondition;
  countries_reporting: number;
  countries_total: number;
  brightest: string | null;
  stormiest: string | null;
  updated_at: string | null;
}
