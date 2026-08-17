import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api';
import History from './History';

const ITEM = {
  id: 1,
  listing_title: 'IKEA Billy bookcase',
  listing_price: 450,
  listing_currency: 'ZAR',
  risk_level: 'low',
  risk_score: 12,
  created_at: '2026-08-01T12:00:00Z',
};

describe('History', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('calls api.listAnalyses on mount and renders the returned items', async () => {
    vi.spyOn(api, 'listAnalyses').mockResolvedValue([ITEM]);

    render(<History onOpen={vi.fn()} />);

    await waitFor(() => expect(api.listAnalyses).toHaveBeenCalled());
    expect(await screen.findByText('IKEA Billy bookcase')).toBeInTheDocument();
  });

  it('calls onOpen with the clicked analysis', async () => {
    const events = userEvent.setup();
    vi.spyOn(api, 'listAnalyses').mockResolvedValue([ITEM]);
    const onOpen = vi.fn();

    render(<History onOpen={onOpen} />);
    await events.click(await screen.findByText('IKEA Billy bookcase'));

    expect(onOpen).toHaveBeenCalledWith(ITEM);
  });

  it('shows an error message if api.listAnalyses fails, not a blank/broken screen', async () => {
    vi.spyOn(api, 'listAnalyses').mockRejectedValue(new Error('boom'));

    render(<History onOpen={vi.fn()} />);

    expect(await screen.findByText('Unable to load your history.')).toBeInTheDocument();
  });
});
