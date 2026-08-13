/**
 * The last seven days as a row of small icons, like the strip on a weather app.
 *
 * Only days the backend actually recorded appear. A fresh install shows one
 * square and grows a new one daily — a gap left visible is more honest than a
 * neutral placeholder that would be indistinguishable from a genuinely calm day.
 */

import { formatScore } from '../conditions';
import type { ForecastPoint } from '../types';
import WeatherIcon from './WeatherIcon';

/** Dates arrive as YYYY-MM-DD and are UTC days, so they're read back as UTC. */
function weekdayLabel(isoDate: string): string {
  const date = new Date(`${isoDate}T00:00:00Z`);
  return date.toLocaleDateString('en-US', { weekday: 'short', timeZone: 'UTC' });
}

function isToday(isoDate: string): boolean {
  return isoDate === new Date().toISOString().slice(0, 10);
}

export default function ForecastStrip({ points }: { points: ForecastPoint[] }) {
  if (points.length === 0) {
    return (
      <p className="panel__note">
        No history for this region yet. A square appears here for every day the
        backend has been running.
      </p>
    );
  }

  return (
    <div className="forecast">
      {points.map((point) => (
        <div
          key={point.date}
          className={`forecast__day ${isToday(point.date) ? 'forecast__day--today' : ''}`}
          title={`${point.date}: ${formatScore(point.score)}`}
        >
          <span className="forecast__weekday">{weekdayLabel(point.date)}</span>
          {/* Still icons here: seven looping animations in a 300px row is a
              distraction from the panel's actual content. */}
          <WeatherIcon condition={point.condition} size={26} animated={false} />
          <span className="forecast__score">{formatScore(point.score)}</span>
        </div>
      ))}
    </div>
  );
}
