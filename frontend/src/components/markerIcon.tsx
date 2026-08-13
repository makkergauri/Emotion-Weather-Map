/**
 * Builds the Leaflet markers.
 *
 * Leaflet wants an HTML string, React wants components, so the icon is rendered
 * once through renderToStaticMarkup. Worth knowing: the markup Leaflet inserts
 * is inert — no React events, no re-render — which is why clicks are wired on
 * the Leaflet Marker instead, and why the icon animations live in a stylesheet
 * rather than in component state.
 *
 * Shared by the country and city layers so a city pin is visibly the same
 * object as a country pin, just smaller.
 */

import L from 'leaflet';
import { renderToStaticMarkup } from 'react-dom/server';
import { conditionColor } from '../conditions';
import type { Confidence, WeatherCondition } from '../types';
import WeatherIcon from './WeatherIcon';

export interface MarkerOptions {
  condition: WeatherCondition;
  label: string;
  score: number;
  confidence: Confidence;
  /** Icon edge in pixels: countries sit around 44, cities around 30. */
  iconPx: number;
  selected?: boolean;
  /** Dimmed and unanimated — used for countries once you've drilled into one. */
  receded?: boolean;
  /**
   * Draw the name under the icon. Off at low zoom, where neighbouring labels
   * collide into an unreadable pile — western Europe is the worst case.
   */
  showLabel?: boolean;
  /**
   * Vertical nudge for the label, in pixels. Negative lifts it above the icon.
   * Used to unpick the handful of collisions that geography creates and no
   * general rule can fix — see LABEL_NUDGE_PX in WorldMap.
   */
  labelOffsetY?: number;
}

const LABEL_BLOCK = 22;
const MARKER_WIDTH = 148;

export function buildMarkerIcon({
  condition,
  label,
  score,
  confidence,
  iconPx,
  selected = false,
  receded = false,
  showLabel = true,
  labelOffsetY = 0,
}: MarkerOptions): L.DivIcon {
  // Strength of feeling drives the halo. A region can't glow on a score alone —
  // low confidence dims it — so the brightest pins are the ones that are both
  // well covered and strongly felt, which is exactly what deserves the eye.
  const intensity = condition === 'no_data' ? 0 : Math.min(Math.abs(score), 1);
  const confidenceFactor = confidence === 'high' ? 1 : 0.45;
  const glowPx = iconPx * (1.2 + intensity * 0.9);

  const classNames = [
    'marker',
    confidence !== 'high' ? 'marker--low-confidence' : '',
    selected ? 'marker--selected' : '',
    receded ? 'marker--receded' : '',
  ]
    .filter(Boolean)
    .join(' ');

  const html = renderToStaticMarkup(
    <div className={classNames}>
      <span
        className="marker__glow"
        style={{
          width: glowPx,
          height: glowPx,
          background: `radial-gradient(circle, ${conditionColor(condition)} 0%, transparent 68%)`,
          opacity: (0.16 + intensity * 0.4) * confidenceFactor,
        }}
      />
      <span className="marker__button">
        <WeatherIcon condition={condition} size={iconPx} animated={!receded} />
        {showLabel && (
          <span
            className="marker__label"
            style={labelOffsetY ? { transform: `translateY(${labelOffsetY}px)` } : undefined}
          >
            {label}
          </span>
        )}
      </span>
    </div>,
  );

  // Without a label the marker is just the glyph, so the box shrinks to match —
  // an oversized transparent hit area would swallow clicks on nearby pins.
  const width = showLabel ? MARKER_WIDTH : iconPx;
  const height = showLabel ? iconPx + LABEL_BLOCK : iconPx;
  return L.divIcon({
    html,
    // Overrides leaflet-div-icon, which otherwise paints a white box behind it.
    className: 'marker-shell',
    iconSize: [width, height],
    iconAnchor: [width / 2, height / 2],
  });
}