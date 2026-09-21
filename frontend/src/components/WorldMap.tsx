/**
 * The map, and the camera work that makes the drill-down feel like one place
 * rather than two screens.
 *
 * There is a single MapContainer for the whole app. Zooming into a country does
 * not mount a new map; it flies the camera and lets the city layer fade in over
 * the receded country pins. That continuity is the thing the transition is for.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  MapContainer,
  Marker,
  TileLayer,
  ZoomControl,
  useMap,
  useMapEvents,
} from 'react-leaflet';
import type { CountryDetail, CountrySummary } from '../types';
import CityDrilldown from './CityDrilldown';
import { buildMarkerIcon } from './markerIcon';

const WORLD_CENTER: [number, number] = [22, 12];
const WORLD_ZOOM = 2;
const COUNTRY_ICON_PX = 44;
const FLY_DURATION_SECONDS = 1.2;

// City pins are meaningless at world zoom — they stack on top of their own
// country pin — so the drill-down layer hides itself if you zoom back out.
const CITY_VISIBLE_MIN_ZOOM = 4;

/**
 * Per-country label nudges, in pixels.
 *
 * Two collisions survive at world zoom, and both come from a long name sitting
 * next to a close neighbour: the UK's label runs under Germany's icon, and the
 * UAE's runs into India's. Lifting those two above their own icons clears both.
 *
 * Hand-tuned rather than solved generally — a real collision-avoidance pass is a
 * lot of machinery for two labels on a fixed set of twelve countries.
 */
const LABEL_NUDGE_PX: Record<string, number> = {
  gb: -72,
  ae: -72,
};

// Used for the first hop, before exact bounds are known. Close enough to reveal
// the city layer for every country in the catalogue, including Singapore.
const COUNTRY_FALLBACK_ZOOM = 5;

// Dark tiles because the app is a night-sky instrument, and because pale basemaps
// wash out the amber/violet condition colours the whole design depends on.
//
// The 'nolabels' variant specifically: CARTO labels places in local languages, so
// the default tiles mix Latin, Cyrillic and CJK across one view. Our own markers
// carry the only names that matter here, and a clean basemap suits a chart better
// than a half-translated atlas.
const TILE_URL = 'https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png';
const TILE_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>';

function usePrefersReducedMotion(): boolean {
  const [prefers, setPrefers] = useState(
    () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false,
  );

  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)');
    const onChange = (event: MediaQueryListEvent) => setPrefers(event.matches);
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, []);

  return prefers;
}

/**
 * Drives the camera from props. Lives inside MapContainer because that is the
 * only place useMap() has a map to talk to.
 */
function MapCamera({
  bounds,
  centre,
  cameraKey,
}: {
  bounds: [[number, number], [number, number]] | null;
  centre: [number, number] | null;
  cameraKey: string;
}) {
  const map = useMap();
  const reduceMotion = usePrefersReducedMotion();

  useEffect(() => {
    // 0 is Leaflet's "jump straight there". Someone who has asked for reduced
    // motion still needs to arrive at the destination, just without the flight.
    const duration = reduceMotion ? 0 : FLY_DURATION_SECONDS;

    if (bounds) {
      map.flyToBounds(bounds, { duration, padding: [70, 70], easeLinearity: 0.22 });
    } else if (centre) {
      map.flyTo(centre, COUNTRY_FALLBACK_ZOOM, { duration, easeLinearity: 0.22 });
    } else {
      map.flyTo(WORLD_CENTER, WORLD_ZOOM, { duration, easeLinearity: 0.22 });
    }
    // Keyed on the region, not the bounds array: the parent hands back a fresh
    // array every render and re-flying on each one would fight the animation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cameraKey, map]);

  return null;
}

/** Reports the live zoom level so markers can adapt to it. */
function ZoomWatcher({ onZoom }: { onZoom: (zoom: number) => void }) {
  const map = useMapEvents({
    zoomend: () => onZoom(map.getZoom()),
  });
  return null;
}

interface WorldMapProps {
  countries: CountrySummary[];
  activeCountry: CountryDetail | null;
  /**
   * The country the user clicked, available immediately. `activeCountry` only
   * arrives once its detail request lands, which can take seconds when the RSS
   * fallback is doing the work — far too long for the camera to sit still.
   */
  drilledIntoCode: string | null;
  selectedKey: string | null;
  onSelectCountry: (code: string) => void;
  onSelectCity: (cityName: string) => void;
  /** Called when the user zooms all the way back out of a drill-down. */
  onExitDrilldown: () => void;
}

export default function WorldMap({
  countries,
  activeCountry,
  drilledIntoCode,
  selectedKey,
  onSelectCountry,
  onSelectCity,
  onExitDrilldown,
}: WorldMapProps) {
  const drilledInto = drilledIntoCode;
  const [zoom, setZoom] = useState(WORLD_ZOOM);

  // Read inside the zoom handler rather than closed over, so the callback always
  // sees the current drill-down without being torn down and rebuilt on every
  // selection change.
  const drilledIntoRef = useRef(drilledInto);
  drilledIntoRef.current = drilledInto;

  /**
   * Zooming back out to the world is how people leave a country — they don't
   * hunt for the breadcrumb. Without this the app stays "in" India while showing
   * the whole planet, and the breadcrumb lies until something else is clicked.
   *
   * Deliberately driven by the zoomend event rather than an effect on `zoom`:
   * when a country is first selected the camera hasn't moved yet, so an effect
   * would see world zoom, call this, and cancel the drill-down instantly.
   */
  const handleZoomEnd = (nextZoom: number) => {
    setZoom(nextZoom);
    if (nextZoom <= WORLD_ZOOM && drilledIntoRef.current) {
      onExitDrilldown();
    }
  };

  // Exact bounds are better, but only exist once the detail has loaded. Until
  // then the camera aims at the centroid from the summary list, so the flight
  // starts on the click rather than on the response.
  const pendingCentre = useMemo(() => {
    if (!drilledInto || activeCountry?.code === drilledInto) return null;
    const country = countries.find((c) => c.code === drilledInto);
    return country ? ([country.lat, country.lng] as [number, number]) : null;
  }, [drilledInto, activeCountry, countries]);

  // Cities are only drawn once the camera is close enough for them to mean
  // anything. Country labels follow the same rule: they are hidden only when
  // city labels would be drawn over them, not merely because a country is
  // selected. Otherwise zooming out mid-drill-down blanks every name on the map.
  const citiesVisible = Boolean(activeCountry) && zoom >= CITY_VISIBLE_MIN_ZOOM;

  const markers = useMemo(
    () =>
      countries.map((country) => ({
        country,
        icon: buildMarkerIcon({
          condition: country.condition,
          label: country.name,
          score: country.score,
          confidence: country.confidence,
          iconPx: COUNTRY_ICON_PX,
          selected: selectedKey === country.code,
          // Everything except the country you're inside steps back — but only
          // once the city layer is actually on screen to step back for.
          receded: citiesVisible && drilledInto !== country.code,
          showLabel: !(citiesVisible && drilledInto !== country.code),
          labelOffsetY: LABEL_NUDGE_PX[country.code] ?? 0,
        }),
      })),
    [countries, selectedKey, drilledInto, citiesVisible],
  );

  return (
    <MapContainer
      className="map"
      center={WORLD_CENTER}
      zoom={WORLD_ZOOM}
      minZoom={2}
      maxZoom={9}
      zoomControl={false}
      worldCopyJump
      // Keeps the viewport from drifting into the grey void above the poles.
      maxBounds={[
        [-85, -200],
        [85, 200],
      ]}
      maxBoundsViscosity={0.7}
    >
      <TileLayer url={TILE_URL} attribution={TILE_ATTRIBUTION} />
      <ZoomControl position="bottomright" />
      <ZoomWatcher onZoom={handleZoomEnd} />

      <MapCamera
        bounds={activeCountry?.code === drilledInto ? (activeCountry?.bounds ?? null) : null}
        centre={pendingCentre}
        cameraKey={drilledInto ?? 'world'}
      />

      {markers.map(({ country, icon }) => (
        <Marker
          key={country.code}
          position={[country.lat, country.lng]}
          icon={icon}
          keyboard
          title={country.name}
          alt={`${country.name} weather marker`}
          eventHandlers={{ click: () => onSelectCountry(country.code) }}
        />
      ))}

      {activeCountry && citiesVisible && (
        <CityDrilldown
          country={activeCountry}
          selectedCity={selectedKey}
          onSelectCity={onSelectCity}
        />
      )}
    </MapContainer>
  );
}