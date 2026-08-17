import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api';
import ListingForm from './ListingForm';

describe('ListingForm', () => {
  beforeEach(() => {
    vi.spyOn(api, 'createAnalysis').mockResolvedValue({ id: 1, risk_level: 'low' });
    vi.spyOn(api, 'previewListingUrl').mockResolvedValue({
      title: 'Fetched title',
      description: 'Fetched description',
      source: 'Fetched source',
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('calls api.createAnalysis with the submitted fields and reports the result', async () => {
    const events = userEvent.setup();
    const onResult = vi.fn();

    render(<ListingForm onResult={onResult} />);
    await events.type(screen.getByLabelText(/title/i), 'iPhone 14 Pro');
    await events.type(screen.getByLabelText(/price/i), '6500');
    // Source has a non-empty default value ("Marketplace") -- clear it first.
    await events.clear(screen.getByLabelText(/source/i));
    await events.type(screen.getByLabelText(/source/i), 'Gumtree');
    await events.type(screen.getByLabelText(/description/i), 'Barely used, comes with box.');
    await events.click(screen.getByRole('button', { name: 'Analyze listing' }));

    await waitFor(() => {
      expect(api.createAnalysis).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'iPhone 14 Pro',
          price: 6500,
          currency: 'USD',
          source: 'Gumtree',
          description: 'Barely used, comes with box.',
        }),
      );
    });
    await waitFor(() => expect(onResult).toHaveBeenCalledWith({ id: 1, risk_level: 'low' }));
  });

  it('calls api.previewListingUrl and prefills untouched fields when fetching a URL', async () => {
    const events = userEvent.setup();

    render(<ListingForm onResult={vi.fn()} />);
    await events.type(screen.getByLabelText(/optional url/i), 'https://example.com/listing/1');
    await events.click(screen.getByRole('button', { name: 'Fetch details' }));

    await waitFor(() => {
      expect(api.previewListingUrl).toHaveBeenCalledWith('https://example.com/listing/1');
    });
    expect(await screen.findByLabelText(/title/i)).toHaveValue('Fetched title');
    expect(screen.getByLabelText(/source/i)).toHaveValue('Fetched source');
  });
});
