import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { ScanStatus } from '../features/folders/ScanStatus';

it.each(['pending', 'scanning', 'blocked', 'error', 'oversized', undefined])('shows quarantine for %s', state => {
  render(<ScanStatus state={state} />);
  expect(screen.getByText(/Quarantined:/)).toBeVisible();
  expect(screen.queryByText(/Scan complete:/)).not.toBeInTheDocument();
});

it('describes a clean result without guaranteeing safety', () => {
  render(<ScanStatus state="clean" />);
  expect(screen.getByText(/no known threats detected/)).toHaveTextContent('does not guarantee safety');
});
