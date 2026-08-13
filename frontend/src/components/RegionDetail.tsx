/**
 * The side panel. One component serves both countries and cities.
 *
 * They differ in exactly two places — countries get a forecast strip and a list
 * of cities to drill into — and splitting them into two components would mean
 * maintaining two copies of the headline list, the station strip and the empty
 * states to avoid one `in` check.
 */

import { conditionColor, conditionLabel, formatObservedAt, formatScore } from '../conditions';
import type { CityDetail, CountryDetail, Headline, Source } from '../types';
import ForecastStrip from './ForecastStrip';
import WeatherIcon from './WeatherIcon';

interface RegionDetailProps {
  data: CountryDetail | CityDetail | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onClose: () => void;
  onSelectCity: (cityName: string) => void;
}

const SOURCE_LABELS: Record<NonNullable<Source>, string> = {
  newsapi: 'NEWSAPI',
  rss: 'RSS',
};

function isCountry(data: CountryDetail | CityDetail): data is CountryDetail {
  return 'cities' in data;
}

/** Station code for the strip: "IN" for a country, "IN/BHOPAL" for a city. */
function stationCode(data: CountryDetail | CityDetail): string {
  return isCountry(data)
    ? data.code.toUpperCase()
    : `${data.country_code.toUpperCase()}/${data.name.toUpperCase()}`;
}

function HeadlineRow({ headline }: { headline: Headline }) {
  return (
    <li className="headline">
      {/* Gauge colour follows the sign, opacity follows the magnitude, so a
          glance down the list shows which stories are doing the pushing. */}
      <span
        className="headline__gauge"
        style={{
          background: headline.score >= 0 ? 'var(--sunny)' : 'var(--rainy)',
          opacity: 0.35 + Math.min(Math.abs(headline.score), 1) * 0.65,
        }}
        aria-hidden="true"
      />
      <div className="headline__text">
        <p className="headline__title">
          {headline.url ? (
            <a href={headline.url} target="_blank" rel="noopener noreferrer">
              {headline.title}
            </a>
          ) : (
            headline.title
          )}
        </p>
        <div className="headline__meta">
          <span>{headline.source}</span>
          <span>{formatScore(headline.score)}</span>
        </div>
      </div>
    </li>
  );
}

export default function RegionDetail({
  data,
  loading,
  error,
  onRetry,
  onClose,
  onSelectCity,
}: RegionDetailProps) {
  return (
    <section className="panel" aria-label="Region detail">
      <header className="panel__head">
        <button type="button" className="panel__close" onClick={onClose} aria-label="Close panel">
          &#10005;
        </button>

        {data ? (
          <>
            <WeatherIcon condition={data.condition} size={56} />
            <div className="panel__titles">
              <span className="eyebrow">
                {isCountry(data) ? 'Country' : `City \u00b7 ${data.country_name}`}
              </span>
              <h2 className="panel__region">{data.name}</h2>
              <p
                className="panel__condition"
                style={{ color: conditionColor(data.condition) }}
              >
                {conditionLabel(data.condition)}
              </p>
              <p className="station-strip">
                <b>{stationCode(data)}</b>
                <span className="sep">&middot;</span>
                {formatObservedAt(data.updated_at)}
                <span className="sep">&middot;</span>
                SENT <b>{data.condition === 'no_data' ? '--' : formatScore(data.score)}</b>
                <span className="sep">&middot;</span>
                N={data.headline_count}
                <span className="sep">&middot;</span>
                CONF {data.confidence.toUpperCase()}
                {data.source && (
                  <>
                    <span className="sep">&middot;</span>
                    SRC {SOURCE_LABELS[data.source]}
                  </>
                )}
              </p>
            </div>
          </>
        ) : (
          <div className="panel__titles">
            <span className="eyebrow">Reading station</span>
            <h2 className="panel__region">{loading ? 'Fetching\u2026' : 'No reading'}</h2>
          </div>
        )}
      </header>

      <div className="panel__body">
        {error && (
          <p className="panel__note">
            {error}
            <button type="button" className="status__retry" onClick={onRetry}>
              Try again
            </button>
          </p>
        )}

        {data?.confidence === 'low' && (
          <p className="panel__note">
            Only {data.headline_count} headlines available, so this reading is
            noisier than the rest of the map.
          </p>
        )}

        {data && isCountry(data) && data.source === 'rss' && (
          <p className="panel__note">
            NewsAPI had no headlines for this country, so this reading comes from
            a Google News search instead &mdash; broader and noisier than a
            curated front page.
          </p>
        )}

        {data?.condition === 'no_data' && (
          <p className="panel__note">
            This station isn&rsquo;t reporting. The news source couldn&rsquo;t be
            reached on the last attempt &mdash; it retries automatically.
          </p>
        )}

        {data && isCountry(data) && (
          <div className="panel__section">
            <span className="eyebrow">Last 7 days</span>
            <ForecastStrip points={data.forecast} />
          </div>
        )}

        {data && data.headlines.length > 0 && (
          <div className="panel__section">
            <span className="eyebrow">Driving the score</span>
            <ul className="headlines">
              {data.headlines.map((headline) => (
                <HeadlineRow key={headline.title} headline={headline} />
              ))}
            </ul>
          </div>
        )}

        {data && isCountry(data) && data.cities.length > 0 && (
          <div className="panel__section">
            <span className="eyebrow">Drill down</span>
            <div className="city-list">
              {data.cities.map((city) => (
                <button
                  type="button"
                  key={city.name}
                  className="city-chip"
                  onClick={() => onSelectCity(city.name)}
                >
                  {city.name}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
