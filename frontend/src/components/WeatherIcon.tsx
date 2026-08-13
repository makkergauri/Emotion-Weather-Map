/**
 * The animated weather glyphs.
 *
 * Inline SVG rather than Lottie: five icons of a dozen shapes each is not worth
 * a runtime plus five JSON files, and inline paths inherit `currentColor`, which
 * is how one component serves both the amber sun and the violet storm. The
 * motion lives in styles.css so it also applies to the copies of this markup
 * that Leaflet renders into map markers, where React never gets to run.
 *
 * Everything is drawn in a 64x64 box so icons stay optically consistent when
 * they're scaled from 20px city pins up to the 56px panel headline.
 */

import { conditionColor, conditionLabel } from '../conditions';
import type { WeatherCondition } from '../types';

interface WeatherIconProps {
  condition: WeatherCondition;
  size?: number;
  /** Turn off for dense lists, where a dozen looping animations is noise. */
  animated?: boolean;
  className?: string;
}

/** Shared cloud body. `y` shifts it so a sun can sit behind the top-left. */
function Cloud({ y = 0, opacity = 1 }: { y?: number; opacity?: number }) {
  return (
    <g transform={`translate(0 ${y})`} opacity={opacity}>
      <circle cx="25" cy="30" r="10" fill="currentColor" />
      <circle cx="38" cy="28" r="12" fill="currentColor" />
      <rect x="16" y="30" width="31" height="13" rx="6.5" fill="currentColor" />
    </g>
  );
}

function Drop({ x, className }: { x: number; className?: string }) {
  return (
    <path
      className={`ewm-drop ${className ?? ''}`}
      d={`M${x} 45 q2.6 4 0 6 q-2.6 -2 0 -6 z`}
      fill="currentColor"
    />
  );
}

/** Eight rays on a 45-degree rhythm. Rotation handles the diagonals. */
function Rays({ cx, cy, inner, outer }: { cx: number; cy: number; inner: number; outer: number }) {
  return (
    <g className="ewm-rays" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
      {[0, 45, 90, 135, 180, 225, 270, 315].map((angle) => (
        <line
          key={angle}
          x1={cx}
          y1={cy - inner}
          x2={cx}
          y2={cy - outer}
          transform={`rotate(${angle} ${cx} ${cy})`}
        />
      ))}
    </g>
  );
}

function Glyph({ condition }: { condition: WeatherCondition }) {
  switch (condition) {
    case 'sunny':
      return (
        <>
          <Rays cx={32} cy={32} inner={17} outer={26} />
          <circle cx="32" cy="32" r="12" fill="currentColor" />
        </>
      );

    case 'partly_cloudy':
      return (
        <>
          <g opacity="0.95">
            <Rays cx={24} cy={22} inner={12} outer={19} />
            <circle cx="24" cy="22" r="8.5" fill="currentColor" />
          </g>
          <g className="ewm-cloud">
            <Cloud y={4} opacity={0.75} />
          </g>
        </>
      );

    case 'overcast':
      return (
        <>
          {/* Back cloud offset and dimmed so the stack reads as depth, not blur. */}
          <g className="ewm-cloud" opacity="0.4" transform="translate(-7 -7)">
            <Cloud />
          </g>
          <g className="ewm-cloud">
            <Cloud y={3} />
          </g>
        </>
      );

    case 'rainy':
      return (
        <>
          <g className="ewm-cloud">
            <Cloud y={-4} />
          </g>
          <Drop x={24} />
          <Drop x={32} className="ewm-drop--2" />
          <Drop x={40} className="ewm-drop--3" />
        </>
      );

    case 'thunderstorm':
      return (
        <>
          <g className="ewm-cloud">
            <Cloud y={-6} opacity={0.9} />
          </g>
          <path
            className="ewm-bolt"
            d="M34 36 L25 50 L31 50 L28 60 L39 45 L33 45 L38 36 Z"
            fill="currentColor"
          />
          <Drop x={21} />
          <Drop x={44} className="ewm-drop--2" />
        </>
      );

    case 'no_data':
    default:
      return (
        <>
          {/* Deliberately not a cloud — a station that isn't reporting shouldn't
              look like a weather reading at all. */}
          <circle
            cx="32"
            cy="32"
            r="17"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeDasharray="4 5"
          />
          <line
            x1="24"
            y1="32"
            x2="40"
            y2="32"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
          />
        </>
      );
  }
}

export default function WeatherIcon({
  condition,
  size = 40,
  animated = true,
  className,
}: WeatherIconProps) {
  return (
    <svg
      className={`weather-icon ${animated ? '' : 'weather-icon--still'} ${className ?? ''}`}
      width={size}
      height={size}
      viewBox="0 0 64 64"
      role="img"
      aria-label={conditionLabel(condition)}
      style={{ color: conditionColor(condition) }}
    >
      <title>{conditionLabel(condition)}</title>
      <Glyph condition={condition} />
    </svg>
  );
}
