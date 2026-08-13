/**
 * Planet mood, fixed in the header.
 *
 * The barometer is the point: a bare number tells you nothing about whether
 * -0.12 is unusual, but a needle sitting just left of centre on a fixed scale
 * does. It also states how many countries are actually reporting, because an
 * average over four countries deserves less trust than one over twelve.
 */

import { conditionLabel, formatScore } from '../conditions';
import type { GlobalSummary } from '../types';
import WeatherIcon from './WeatherIcon';

export default function GlobalMood({ summary }: { summary: GlobalSummary | null }) {
  if (!summary) {
    return (
      <div className="global-mood">
        <span className="station-strip">Reading stations&hellip;</span>
      </div>
    );
  }

  const hasData = summary.condition !== 'no_data';
  // Map -1..+1 onto 0..100% of the scale.
  const needleLeft = `${((summary.score + 1) / 2) * 100}%`;

  return (
    <div className="global-mood">
      <WeatherIcon condition={summary.condition} size={38} />
      <div className="global-mood__readout">
        <span className="eyebrow">Planet mood</span>
        <span className="global-mood__label">{conditionLabel(summary.condition)}</span>
        <span className="station-strip">
          <b>{hasData ? formatScore(summary.score) : '--'}</b>
          <span className="sep">&middot;</span>
          {summary.countries_reporting}/{summary.countries_total} reporting
          {summary.stormiest && (
            <>
              <span className="sep">&middot;</span>
              darkest <b>{summary.stormiest}</b>
            </>
          )}
        </span>
      </div>
      {hasData && (
        <div
          className="barometer"
          role="img"
          aria-label={`Global sentiment ${formatScore(summary.score)} on a scale from -1 to +1`}
        >
          <span className="barometer__centre" />
          <span className="barometer__needle" style={{ left: needleLeft }} />
        </div>
      )}
    </div>
  );
}
