/**
 * City pins inside a zoomed-in country.
 *
 * Rendered into the same MapContainer as the country layer rather than swapping
 * to a second map, so the flyTo stays continuous and the country pins can recede
 * behind these instead of disappearing.
 *
 * Readings arrive one at a time (see useCitiesWeather), so each pin starts as a
 * grey placeholder and resolves independently. Showing the pins immediately and
 * filling them in beats holding the whole layer back for the slowest RSS feed.
 */

import { useMemo } from 'react';
import { Marker } from 'react-leaflet';
import { useCitiesWeather } from '../hooks/useRegionData';
import type { CityRef, CountryDetail } from '../types';
import { buildMarkerIcon } from './markerIcon';

const CITY_ICON_PX = 30;

interface CityDrilldownProps {
  country: CountryDetail;
  selectedCity: string | null;
  onSelectCity: (cityName: string) => void;
}

export default function CityDrilldown({
  country,
  selectedCity,
  onSelectCity,
}: CityDrilldownProps) {
  const { readings } = useCitiesWeather(country.code, country.cities);

  const markers = useMemo(
    () =>
      country.cities.map((city: CityRef) => {
        const reading = readings[city.name];
        return {
          city,
          icon: buildMarkerIcon({
            condition: reading?.condition ?? 'no_data',
            label: city.name,
            score: reading?.score ?? 0,
            confidence: reading?.confidence ?? 'none',
            iconPx: CITY_ICON_PX,
            selected: selectedCity === city.name,
          }),
        };
      }),
    [country.cities, readings, selectedCity],
  );

  return (
    <>
      {markers.map(({ city, icon }) => (
        <Marker
          key={`${country.code}-${city.name}`}
          position={[city.lat, city.lng]}
          icon={icon}
          keyboard
          title={city.name}
          alt={`${city.name} weather marker`}
          eventHandlers={{ click: () => onSelectCity(city.name) }}
          zIndexOffset={500}
        />
      ))}
    </>
  );
}
