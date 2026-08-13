/**
 * Guards the seam between React and Leaflet. renderToStaticMarkup runs outside
 * the component tree, so a mistake here fails silently at runtime — the map just
 * draws empty pins — rather than throwing anywhere a normal render test looks.
 */

import { describe, expect, it } from 'vitest';
import { buildMarkerIcon } from './markerIcon';

function html(options: Parameters<typeof buildMarkerIcon>[0]): string {
  return buildMarkerIcon(options).options.html as string;
}

const base = {
  condition: 'rainy',
  label: 'India',
  score: -0.31,
  confidence: 'high',
  iconPx: 44,
} as const;

describe('buildMarkerIcon', () => {
  it('renders the icon and the label into the marker', () => {
    const markup = html(base);
    expect(markup).toContain('India');
    expect(markup).toContain('ewm-drop');
    expect(markup).toContain('weather-icon');
  });

  it('strips Leaflet default icon chrome', () => {
    expect(buildMarkerIcon(base).options.className).toBe('marker-shell');
  });

  it('anchors the marker on its centre', () => {
    const { iconSize, iconAnchor } = buildMarkerIcon(base).options;
    expect(iconAnchor).toEqual([(iconSize as number[])[0] / 2, (iconSize as number[])[1] / 2]);
  });

  it('flags thin coverage so the map can dim it', () => {
    expect(html({ ...base, confidence: 'low' })).toContain('marker--low-confidence');
    expect(html(base)).not.toContain('marker--low-confidence');
  });

  it('glows harder for stronger feeling', () => {
    const opacity = (markup: string) => Number(/opacity:([\d.]+)/.exec(markup)![1]);
    expect(opacity(html({ ...base, score: -0.9 }))).toBeGreaterThan(
      opacity(html({ ...base, score: -0.16 })),
    );
  });

  it('never glows for a station with no data', () => {
    const markup = html({ ...base, condition: 'no_data', score: 0, confidence: 'none' });
    expect(markup).toContain('opacity:0');
  });

  it('stops animating receded countries', () => {
    expect(html({ ...base, receded: true })).toContain('weather-icon--still');
  });
});
