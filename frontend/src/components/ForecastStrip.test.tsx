import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import ForecastStrip from './ForecastStrip';
import type { ForecastPoint } from '../types';

const points: ForecastPoint[] = [
  { date: '2026-08-09', score: -0.62, condition: 'thunderstorm' },
  { date: '2026-08-10', score: -0.2, condition: 'rainy' },
  { date: '2026-08-11', score: 0.31, condition: 'partly_cloudy' },
];

describe('ForecastStrip', () => {
  it('renders one square per recorded day', () => {
    const { container } = render(<ForecastStrip points={points} />);
    expect(container.querySelectorAll('.forecast__day')).toHaveLength(3);
  });

  it('reads dates as UTC weekdays', () => {
    render(<ForecastStrip points={points} />);
    expect(screen.getByText('Sun')).toBeInTheDocument(); // 2026-08-09
    expect(screen.getByText('Tue')).toBeInTheDocument(); // 2026-08-11
  });

  it('shows signed scores', () => {
    render(<ForecastStrip points={points} />);
    expect(screen.getByText('\u22120.62')).toBeInTheDocument();
    expect(screen.getByText('+0.31')).toBeInTheDocument();
  });

  it('explains an empty strip instead of rendering nothing', () => {
    render(<ForecastStrip points={[]} />);
    expect(screen.getByText(/no history for this region yet/i)).toBeInTheDocument();
  });
});
