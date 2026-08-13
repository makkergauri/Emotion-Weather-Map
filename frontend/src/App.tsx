/**
 * The app shell: navigation state, and the wiring between map and panel.
 *
 * Two pieces of state describe the whole interface. `drilledInto` is where the
 * camera is, `selection` is what the panel is showing. They're separate on
 * purpose — closing the panel shouldn't zoom you back out to the world, and
 * that would be impossible to express with one variable.
 */

import { useCallback, useEffect, useState } from 'react';
import Breadcrumb, { type Crumb } from './components/Breadcrumb';
import GlobalMood from './components/GlobalMood';
import Legend from './components/Legend';
import RegionDetail from './components/RegionDetail';
import WorldMap from './components/WorldMap';
import {
  useCityDetail,
  useCountries,
  useCountryDetail,
  useGlobalSummary,
} from './hooks/useRegionData';

type Selection = { kind: 'country'; code: string } | { kind: 'city'; name: string } | null;

export default function App() {
  const [drilledInto, setDrilledInto] = useState<string | null>(null);
  const [selection, setSelection] = useState<Selection>(null);

  const countries = useCountries();
  const globalSummary = useGlobalSummary();
  const countryDetail = useCountryDetail(drilledInto);
  const cityDetail = useCityDetail(
    selection?.kind === 'city' ? selection.name : null,
    drilledInto,
  );

  const showingCity = selection?.kind === 'city';
  const panelResource = showingCity ? cityDetail : countryDetail;

  const selectCountry = useCallback((code: string) => {
    setDrilledInto(code);
    setSelection({ kind: 'country', code });
  }, []);

  const selectCity = useCallback((name: string) => {
    setSelection({ kind: 'city', name });
  }, []);

  const returnToWorld = useCallback(() => {
    setDrilledInto(null);
    setSelection(null);
  }, []);

  const returnToCountry = useCallback(() => {
    if (drilledInto) setSelection({ kind: 'country', code: drilledInto });
  }, [drilledInto]);

  // Escape steps out one level at a time, matching the breadcrumb rather than
  // dumping you back at the world view from three levels in.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      if (showingCity) returnToCountry();
      else if (selection) setSelection(null);
      else if (drilledInto) returnToWorld();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [showingCity, selection, drilledInto, returnToCountry, returnToWorld]);

  const crumbs: Crumb[] = [{ label: 'World', onSelect: returnToWorld }];
  if (countryDetail.data && drilledInto) {
    crumbs.push({ label: countryDetail.data.name, onSelect: returnToCountry });
  }
  if (showingCity && selection.kind === 'city') {
    crumbs.push({ label: selection.name });
  }

  return (
    <div className="app">
      <header className="header">
        <div>
          <h1 className="wordmark">Emotion Weather</h1>
          <Breadcrumb crumbs={crumbs} />
        </div>
        <GlobalMood summary={globalSummary.data} />
      </header>

      <WorldMap
        countries={countries.data ?? []}
        activeCountry={countryDetail.data}
        drilledIntoCode={drilledInto}
        selectedKey={
          selection?.kind === 'city'
            ? selection.name
            : selection?.kind === 'country'
              ? selection.code
              : null
        }
        onSelectCountry={selectCountry}
        onSelectCity={selectCity}
        onExitDrilldown={returnToWorld}
      />

      <Legend />

      {countries.loading && !countries.data && (
        <p className="status">
          <span className="status__dot" />
          Reading stations&hellip;
        </p>
      )}

      {countries.error && (
        <p className="status status--error">
          {countries.error}
          <button type="button" className="status__retry" onClick={countries.reload}>
            Retry
          </button>
        </p>
      )}

      {selection && (
        <RegionDetail
          data={panelResource.data}
          loading={panelResource.loading}
          error={panelResource.error}
          onRetry={panelResource.reload}
          onClose={() => setSelection(null)}
          onSelectCity={selectCity}
        />
      )}
    </div>
  );
}