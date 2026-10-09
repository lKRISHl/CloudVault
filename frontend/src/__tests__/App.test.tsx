import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import App from '../app/App';

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

describe('App Component', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ detail: 'Refresh token missing' }),
      }),
    );
    window.history.pushState({}, '', '/login');
  });

  it('renders without crashing', async () => {
    render(<App />);
    const heading = await screen.findByRole('heading', { level: 1 });
    expect(heading).toHaveTextContent(/CloudVault/i);
  });

  it('displays the correct tagline', async () => {
    render(<App />);
    expect(await screen.findByText(/AI-Native Cloud File Storage/i)).toBeInTheDocument();
  });
});
