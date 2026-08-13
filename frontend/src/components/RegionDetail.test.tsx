import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import RegionDetail from './RegionDetail';
import type { CityDetail, CountryDetail } from '../types';

const country: CountryDetail = {
  code: 'in',
  name: 'India',
  lat: 22,
  lng: 79,
  score: -0.31,
  condition: 'rainy',
  headline_count: 24,
  confidence: 'high',
  source: 'newsapi',
  updated_at: '2026-08-11T11:42:00+00:00',
  bounds: [
    [8, 68.1],
    [35.5, 97.4],
  ],
  headlines: [
    { title: 'Floods close two highways', source: 'The Hindu', url: 'https://x', score: -0.72 },
    { title: 'Metro line opens early', source: 'TOI', url: null, score: 0.55 },
  ],
  forecast: [{ date: '2026-08-11', score: -0.31, condition: 'rainy' }],
  cities: [
    { name: 'Bhopal', lat: 23.2, lng: 77.4 },
    { name: 'Mumbai', lat: 19, lng: 72.8 },
  ],
};

const noop = { loading: false, error: null, onRetry: vi.fn(), onClose: vi.fn() };

describe('RegionDetail', () => {
  it('shows the region, its condition and the station readout', () => {
    render(<RegionDetail data={country} {...noop} onSelectCity={vi.fn()} />);

    expect(screen.getByText('India')).toBeInTheDocument();
    // Scoped: "Rainy" is also the icon's accessible title, so a bare text query
    // matches twice.
    expect(screen.getByText('Rainy', { selector: '.panel__condition' })).toBeInTheDocument();
    // The observation time is a bare text node inside the strip, so the strip
    // itself is what gets queried.
    expect(screen.getByText(/11:42Z/, { selector: '.station-strip' })).toBeInTheDocument();
    expect(screen.getByText('\u22120.31', { selector: '.station-strip b' })).toBeInTheDocument();
    // The same figure also appears in today's forecast square — the strip's
    // last entry is meant to agree with the current reading.
    expect(screen.getAllByText('\u22120.31')).toHaveLength(2);
  });

  it('lists the headlines with their sources', () => {
    render(<RegionDetail data={country} {...noop} onSelectCity={vi.fn()} />);

    expect(screen.getByText('Floods close two highways')).toBeInTheDocument();
    expect(screen.getByText('The Hindu')).toBeInTheDocument();
  });

  it('links headlines out rather than showing article text', () => {
    render(<RegionDetail data={country} {...noop} onSelectCity={vi.fn()} />);

    const link = screen.getByRole('link', { name: 'Floods close two highways' });
    expect(link).toHaveAttribute('href', 'https://x');
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
  });

  it('offers the drill-down cities', async () => {
    const onSelectCity = vi.fn();
    render(<RegionDetail data={country} {...noop} onSelectCity={onSelectCity} />);

    await userEvent.click(screen.getByRole('button', { name: 'Bhopal' }));
    expect(onSelectCity).toHaveBeenCalledWith('Bhopal');
  });

  it('warns when a reading rests on too few headlines', () => {
    render(
      <RegionDetail
        data={{ ...country, confidence: 'low', headline_count: 4 }}
        {...noop}
        onSelectCity={vi.fn()}
      />,
    );
    expect(screen.getByText(/only 4 headlines available/i)).toBeInTheDocument();
  });

  it('explains an unreachable station', () => {
    render(
      <RegionDetail
        data={{ ...country, condition: 'no_data', confidence: 'none', headlines: [] }}
        {...noop}
        onSelectCity={vi.fn()}
      />,
    );
    expect(screen.getByText(/isn.t reporting/i)).toBeInTheDocument();
  });

  it('drops the forecast and city list for a city', () => {
    const city: CityDetail = {
      name: 'Bhopal',
      country_code: 'in',
      country_name: 'India',
      lat: 23.2,
      lng: 77.4,
      score: 0.18,
      condition: 'partly_cloudy',
      headline_count: 18,
      confidence: 'high',
      source: 'rss',
      updated_at: '2026-08-11T11:42:00+00:00',
      headlines: [{ title: 'New library opens', source: 'FPJ', url: null, score: 0.6 }],
    };
    const { container } = render(
      <RegionDetail data={city} {...noop} onSelectCity={vi.fn()} />,
    );

    expect(screen.getByText('Bhopal')).toBeInTheDocument();
    expect(screen.getByText(/City · India/)).toBeInTheDocument();
    expect(container.querySelector('.forecast')).toBeNull();
    expect(container.querySelector('.city-list')).toBeNull();
  });

  it('names the source in the readout', () => {
    render(<RegionDetail data={country} {...noop} onSelectCity={vi.fn()} />);
    expect(screen.getByText(/SRC NEWSAPI/)).toBeInTheDocument();
  });

  it('says so when a country fell back to an RSS search', () => {
    render(
      <RegionDetail data={{ ...country, source: 'rss' }} {...noop} onSelectCity={vi.fn()} />,
    );
    expect(screen.getByText(/newsapi had no headlines for this country/i)).toBeInTheDocument();
  });

  it('does not explain the source for a city, where RSS is the only option', () => {
    render(<RegionDetail data={country} {...noop} onSelectCity={vi.fn()} />);
    expect(screen.queryByText(/newsapi had no headlines/i)).toBeNull();
  });

  it('closes on request', async () => {
    const onClose = vi.fn();
    render(
      <RegionDetail data={country} {...noop} onClose={onClose} onSelectCity={vi.fn()} />,
    );

    await userEvent.click(screen.getByRole('button', { name: /close panel/i }));
    expect(onClose).toHaveBeenCalledOnce();
  });
});
