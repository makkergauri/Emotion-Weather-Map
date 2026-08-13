/**
 * The scale, stated outright.
 *
 * Without it the map is a puzzle: a viewer can guess that storms are bad news
 * but not where the cut-off sits, and the thresholds are the one modelling
 * decision a reader most deserves to see.
 */

import { CONDITIONS, formatScore } from '../conditions';
import type { WeatherCondition } from '../types';
import WeatherIcon from './WeatherIcon';

/**
 * Plain-English gloss for each band.
 *
 * The raw thresholds (+0.50 and so on) are precise but meaningless without
 * knowing the scale they sit on, and a legend that needs its own legend has
 * failed. The numbers survive as a tooltip for anyone who wants them.
 */
const MEANING: Record<WeatherCondition, string> = {
  sunny: 'Overwhelmingly good news',
  partly_cloudy: 'More good news than bad',
  overcast: 'Mixed, or nothing much happening',
  rainy: 'More bad news than good',
  thunderstorm: 'Relentlessly grim',
  no_data: 'No reading available',
};

export default function Legend() {
  return (
    <aside className="legend" aria-label="How sentiment maps to weather">
      <span className="eyebrow">What the weather means</span>
      <div className="legend__rows">
        {CONDITIONS.map((condition) => (
          <div
            className="legend__row"
            key={condition.id}
            title={`Average headline score ${formatScore(condition.min)} to ${formatScore(
              condition.max,
            )}, on a scale from -1 to +1`}
          >
            <WeatherIcon condition={condition.id} size={20} animated={false} />
            <span className="legend__name">{condition.label}</span>
            <span>{MEANING[condition.id]}</span>
          </div>
        ))}
      </div>
    </aside>
  );
}