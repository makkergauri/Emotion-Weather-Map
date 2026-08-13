/**
 * The icons are the app's whole vocabulary, so the render tests check that each
 * condition produces a distinct, labelled glyph — a silent fallback to the same
 * shape for two conditions would be invisible in review but obvious to a user.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import WeatherIcon from './WeatherIcon';
import type { WeatherCondition } from '../types';

const ALL: WeatherCondition[] = [
  'sunny',
  'partly_cloudy',
  'overcast',
  'rainy',
  'thunderstorm',
  'no_data',
];

describe('WeatherIcon', () => {
  it('labels every condition for screen readers', () => {
    render(<WeatherIcon condition="thunderstorm" />);
    expect(screen.getByRole('img', { name: 'Thunderstorm' })).toBeInTheDocument();
  });

  it('renders a different glyph for each condition', () => {
    const shapes = ALL.map((condition) => {
      const { container, unmount } = render(<WeatherIcon condition={condition} />);
      const markup = container.querySelector('svg')!.innerHTML;
      unmount();
      return markup;
    });
    expect(new Set(shapes).size).toBe(ALL.length);
  });

  it('animates by default and stops when asked', () => {
    const { container, rerender } = render(<WeatherIcon condition="rainy" />);
    expect(container.querySelector('.weather-icon--still')).toBeNull();
    expect(container.querySelectorAll('.ewm-drop')).toHaveLength(3);

    rerender(<WeatherIcon condition="rainy" animated={false} />);
    expect(container.querySelector('.weather-icon--still')).not.toBeNull();
  });

  it('respects the requested size', () => {
    const { container } = render(<WeatherIcon condition="sunny" size={64} />);
    expect(container.querySelector('svg')).toHaveAttribute('width', '64');
  });

  it('does not dress an unreachable station up as weather', () => {
    const { container } = render(<WeatherIcon condition="no_data" />);
    expect(container.querySelector('.ewm-cloud')).toBeNull();
    expect(container.querySelector('.ewm-rays')).toBeNull();
  });
});
