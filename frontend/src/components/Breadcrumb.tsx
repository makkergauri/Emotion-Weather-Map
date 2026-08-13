/**
 * The trail back out of a drill-down: World / India / Bhopal.
 *
 * Also the primary way to navigate up — the map has no back button, so every
 * crumb except the last is a real control.
 */

export interface Crumb {
  label: string;
  /** Omitted on the current location, which renders as plain text. */
  onSelect?: () => void;
}

export default function Breadcrumb({ crumbs }: { crumbs: Crumb[] }) {
  return (
    <nav className="breadcrumb" aria-label="Location">
      {crumbs.map((crumb, index) => {
        const isCurrent = index === crumbs.length - 1;
        return (
          <span key={crumb.label} style={{ display: 'contents' }}>
            {index > 0 && (
              <span className="breadcrumb__sep" aria-hidden="true">
                /
              </span>
            )}
            {isCurrent || !crumb.onSelect ? (
              <span className="breadcrumb__crumb breadcrumb__crumb--current" aria-current="page">
                {crumb.label}
              </span>
            ) : (
              <button type="button" className="breadcrumb__crumb" onClick={crumb.onSelect}>
                {crumb.label}
              </button>
            )}
          </span>
        );
      })}
    </nav>
  );
}
