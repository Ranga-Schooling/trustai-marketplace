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

const FAILED_ITEM = {
  id: 7,
  title: 'iPhone 15 Pro',
  price: 15,
  currency: 'USD',
  source: 'Gumtree',
  created_at: '2026-08-02T09:00:00Z',
};

// D-20, issue #80: History now loads both endpoints on mount, so every
// test needs both mocked -- listFailedListings defaults to empty here so
// the pre-existing analyses-only tests don't have to know about it.
beforeEach(() => {
  vi.spyOn(api, 'listFailedListings').mockResolvedValue([]);
});

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

  it('renders failed listings with a retry control', async () => {
    vi.spyOn(api, 'listAnalyses').mockResolvedValue([]);
    vi.spyOn(api, 'listFailedListings').mockResolvedValue([FAILED_ITEM]);

    render(<History onOpen={vi.fn()} />);

    expect(await screen.findByText('iPhone 15 Pro')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry analysis/i })).toBeInTheDocument();
  });

  it('retrying a failed listing calls api.retryAnalysis and opens the result', async () => {
    const events = userEvent.setup();
    const newAnalysis = { id: 42, risk_level: 'high' };
    vi.spyOn(api, 'listAnalyses').mockResolvedValue([]);
    vi.spyOn(api, 'listFailedListings').mockResolvedValue([FAILED_ITEM]);
    vi.spyOn(api, 'retryAnalysis').mockResolvedValue(newAnalysis);
    const onOpen = vi.fn();

    render(<History onOpen={onOpen} />);
    await events.click(await screen.findByRole('button', { name: /retry analysis/i }));

    await waitFor(() => expect(api.retryAnalysis).toHaveBeenCalledWith(FAILED_ITEM.id));
    expect(onOpen).toHaveBeenCalledWith(newAnalysis);
  });

  it('shows an error if retry fails, without losing the failed-listing row', async () => {
    const events = userEvent.setup();
    vi.spyOn(api, 'listAnalyses').mockResolvedValue([]);
    vi.spyOn(api, 'listFailedListings').mockResolvedValue([FAILED_ITEM]);
    vi.spyOn(api, 'retryAnalysis').mockRejectedValue(new Error('still broken'));

    render(<History onOpen={vi.fn()} />);
    await events.click(await screen.findByRole('button', { name: /retry analysis/i }));

    expect(await screen.findByText('Unable to retry that listing right now.')).toBeInTheDocument();
    expect(screen.getByText('iPhone 15 Pro')).toBeInTheDocument();
  });
});
