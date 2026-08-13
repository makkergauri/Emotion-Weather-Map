import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import Breadcrumb from './Breadcrumb';

describe('Breadcrumb', () => {
  it('shows the full trail', () => {
    render(<Breadcrumb crumbs={[{ label: 'World' }, { label: 'India' }, { label: 'Bhopal' }]} />);
    expect(screen.getByText('World')).toBeInTheDocument();
    expect(screen.getByText('Bhopal')).toBeInTheDocument();
  });

  it('makes ancestors clickable and the current location inert', () => {
    render(
      <Breadcrumb
        crumbs={[{ label: 'World', onSelect: vi.fn() }, { label: 'India', onSelect: vi.fn() }]}
      />,
    );
    // Two crumbs, one button: the last one is where you already are.
    expect(screen.getAllByRole('button')).toHaveLength(1);
    expect(screen.getByText('India')).toHaveAttribute('aria-current', 'page');
  });

  it('navigates up when an ancestor is clicked', async () => {
    const onSelect = vi.fn();
    render(<Breadcrumb crumbs={[{ label: 'World', onSelect }, { label: 'India' }]} />);

    await userEvent.click(screen.getByRole('button', { name: 'World' }));
    expect(onSelect).toHaveBeenCalledOnce();
  });
});
