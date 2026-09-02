import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api } from '../api';
import VisualInspection from './VisualInspection';

const MIB = 1024 * 1024;

function imageFile(name, type, size = 32) {
  return new File([new Uint8Array(size)], name, { type });
}

function selectFiles(files) {
  fireEvent.change(screen.getByLabelText('Choose photos'), {
    target: { files },
  });
}

function renderVisualInspection() {
  return render(<VisualInspection analysisId={42} />);
}

async function submitValidInspection(result) {
  const events = userEvent.setup();
  vi.spyOn(api, 'visualInspect').mockResolvedValue(result);
  const photo = imageFile('private-owner-name.jpg', 'image/jpeg');

  renderVisualInspection();
  selectFiles([photo]);
  await events.click(
    screen.getByRole('checkbox', {
      name: /I consent to sending these photos to OpenAI for visual inspection/i,
    }),
  );
  await events.click(screen.getByRole('button', { name: 'Inspect photos' }));

  return { events, photo };
}

describe('VisualInspection', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the initial upload, disclosure, consent, and submit controls', () => {
    renderVisualInspection();

    expect(
      screen.getByRole('heading', { name: 'Add photos for visual inspection' }),
    ).toBeVisible();
    expect(screen.getByLabelText('Choose photos')).toHaveAttribute(
      'accept',
      'image/jpeg,image/png,image/webp',
    );
    expect(screen.getByText(/Choose 1 to 3 JPEG, PNG, or WebP photos/i)).toBeVisible();
    expect(
      screen.getByText(/Selected photos are sent to OpenAI for visual inspection/i),
    ).toBeVisible();
    expect(
      screen.getByText(/TrustAI does not save the photos or Visual Inspection findings in V1/i),
    ).toBeVisible();
    expect(
      screen.getByText(/processing may be subject to OpenAI's API data-handling policy/i),
    ).toBeVisible();
    expect(screen.getByText(/Do not upload sensitive or personal images/i)).toBeVisible();
    expect(
      screen.getByRole('checkbox', {
        name: /I consent to sending these photos to OpenAI for visual inspection/i,
      }),
    ).not.toBeChecked();
    expect(screen.getByRole('button', { name: 'Inspect photos' })).toBeDisabled();
  });

  it.each([
    ['JPEG', imageFile('photo.jpg', 'image/jpeg')],
    ['PNG', imageFile('photo.png', 'image/png')],
    ['WebP', imageFile('photo.webp', 'image/webp')],
  ])('accepts one valid %s photo', (_format, photo) => {
    renderVisualInspection();

    selectFiles([photo]);

    expect(screen.getByText('1 photo selected')).toBeVisible();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('accepts three valid photos', () => {
    renderVisualInspection();

    selectFiles([
      imageFile('front.jpg', 'image/jpeg'),
      imageFile('back.png', 'image/png'),
      imageFile('label.webp', 'image/webp'),
    ]);

    expect(screen.getByText('3 photos selected')).toBeVisible();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('rejects more than three photos', () => {
    renderVisualInspection();

    selectFiles([
      imageFile('one.jpg', 'image/jpeg'),
      imageFile('two.jpg', 'image/jpeg'),
      imageFile('three.jpg', 'image/jpeg'),
      imageFile('four.jpg', 'image/jpeg'),
    ]);

    expect(screen.getByRole('alert')).toHaveTextContent(/select no more than 3 photos/i);
    expect(screen.getByRole('button', { name: 'Inspect photos' })).toBeDisabled();
  });

  it('rejects an unsupported declared file type', () => {
    renderVisualInspection();

    selectFiles([imageFile('animation.gif', 'image/gif')]);

    expect(screen.getByRole('alert')).toHaveTextContent(/JPEG, PNG, or WebP/i);
    expect(screen.getByRole('button', { name: 'Inspect photos' })).toBeDisabled();
  });

  it('rejects an individual photo larger than 4 MiB', () => {
    renderVisualInspection();

    selectFiles([imageFile('large.jpg', 'image/jpeg', 4 * MIB + 1)]);

    expect(screen.getByRole('alert')).toHaveTextContent(/each photo must be 4 MiB or smaller/i);
    expect(screen.getByRole('button', { name: 'Inspect photos' })).toBeDisabled();
  });

  it('rejects a selection larger than 10 MiB in total', () => {
    renderVisualInspection();

    selectFiles([
      imageFile('one.jpg', 'image/jpeg', 4 * MIB),
      imageFile('two.jpg', 'image/jpeg', 4 * MIB),
      imageFile('three.jpg', 'image/jpeg', 4 * MIB),
    ]);

    expect(screen.getByRole('alert')).toHaveTextContent(/combined photos must be 10 MiB or smaller/i);
    expect(screen.getByRole('button', { name: 'Inspect photos' })).toBeDisabled();
  });

  it('requires both valid files and fresh affirmative consent before submission', async () => {
    const events = userEvent.setup();
    renderVisualInspection();
    const submit = screen.getByRole('button', { name: 'Inspect photos' });
    const consent = screen.getByRole('checkbox', {
      name: /I consent to sending these photos to OpenAI for visual inspection/i,
    });

    expect(submit).toBeDisabled();
    await events.click(consent);
    expect(submit).toBeDisabled();

    selectFiles([imageFile('photo.jpg', 'image/jpeg')]);
    expect(submit).toBeEnabled();

    await events.click(consent);
    expect(submit).toBeDisabled();
  });

  it('submits the selected files for the completed analysis', async () => {
    const result = {
      findings: [
        {
          category: 'visible_damage',
          observation: 'Photo 1 visibly shows a scratch.',
          photo_numbers: [1],
        },
      ],
    };
    const { photo } = await submitValidInspection(result);

    await waitFor(() => {
      expect(api.visualInspect).toHaveBeenCalledWith(42, [photo]);
    });
  });

  it('prevents repeated submission while an inspection is loading', async () => {
    const events = userEvent.setup();
    let resolveInspection;
    vi.spyOn(api, 'visualInspect').mockImplementation(
      () => new Promise((resolve) => {
        resolveInspection = resolve;
      }),
    );
    renderVisualInspection();
    selectFiles([imageFile('photo.jpg', 'image/jpeg')]);
    await events.click(
      screen.getByRole('checkbox', {
        name: /I consent to sending these photos to OpenAI for visual inspection/i,
      }),
    );

    await events.click(screen.getByRole('button', { name: 'Inspect photos' }));

    expect(screen.getByRole('button', { name: 'Inspecting photos…' })).toBeDisabled();
    expect(screen.getByRole('status')).toHaveTextContent('Inspecting photos…');
    expect(api.visualInspect).toHaveBeenCalledOnce();
    await events.click(screen.getByRole('button', { name: 'Inspecting photos…' }));
    expect(api.visualInspect).toHaveBeenCalledOnce();

    resolveInspection({ findings: [] });
    await waitFor(() => {
      expect(screen.queryByText('Inspecting photos…')).not.toBeInTheDocument();
    });
  });

  it('disables file selection while an inspection request is loading', async () => {
    const events = userEvent.setup();
    let rejectInspection;
    vi.spyOn(api, 'visualInspect').mockImplementation(
      () => new Promise((_resolve, reject) => {
        rejectInspection = reject;
      }),
    );
    renderVisualInspection();
    const fileInput = screen.getByLabelText('Choose photos');
    selectFiles([imageFile('photo.jpg', 'image/jpeg')]);
    await events.click(
      screen.getByRole('checkbox', {
        name: /I consent to sending these photos to OpenAI for visual inspection/i,
      }),
    );

    await events.click(screen.getByRole('button', { name: 'Inspect photos' }));

    expect(fileInput).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Inspecting photos…' })).toBeDisabled();

    rejectInspection(new ApiError('private detail', 503));
    await waitFor(() => {
      expect(fileInput).toBeEnabled();
    });
  });

  it('renders structured findings and the bounded Visual Inspection limitations', async () => {
    await submitValidInspection({
      findings: [
        {
          category: 'visible_damage',
          observation: 'Photo 1 visibly shows a scratch on the upper-right corner.',
          photo_numbers: [1],
        },
        {
          category: 'visible_text',
          observation: 'Photo 2 visibly shows a printed serial label.',
          photo_numbers: [2, 3],
        },
      ],
    });

    expect(await screen.findByText('Visible damage')).toBeVisible();
    expect(screen.getByText('Photo 1 visibly shows a scratch on the upper-right corner.')).toBeVisible();
    expect(screen.getByText('Photo 1')).toBeVisible();
    expect(screen.getByText('Visible text')).toBeVisible();
    expect(screen.getByText('Photo 2 visibly shows a printed serial label.')).toBeVisible();
    expect(screen.getByText('Photos 2, 3')).toBeVisible();
    expect(screen.getByText(/Only the uploaded photos are inspected/i)).toBeVisible();
    expect(
      screen.getByText(/does not certify authenticity, establish ownership, or verify hidden or internal condition/i),
    ).toBeVisible();
    expect(screen.getByText(/does not retrieve current market prices/i)).toBeVisible();
    expect(
      screen.getByText(/Visual findings do not change the existing Trust score or recommendation/i),
    ).toBeVisible();
  });

  it.each([
    [415, 'private unsupported provider detail', /file type is not supported/i],
    [413, 'private size detail', /photos are too large/i],
    [422, 'private invalid request detail', /photos could not be processed/i],
    [502, 'private provider response', /visual inspection could not be completed/i],
    [503, 'private configuration detail', /visual inspection is temporarily unavailable/i],
  ])('maps status %s to safe user-facing copy', async (status, privateDetail, safeCopy) => {
    const events = userEvent.setup();
    vi.spyOn(api, 'visualInspect').mockRejectedValue(new ApiError(privateDetail, status));
    renderVisualInspection();
    selectFiles([imageFile('photo.jpg', 'image/jpeg')]);
    await events.click(
      screen.getByRole('checkbox', {
        name: /I consent to sending these photos to OpenAI for visual inspection/i,
      }),
    );

    await events.click(screen.getByRole('button', { name: 'Inspect photos' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(safeCopy);
    expect(alert).not.toHaveTextContent(privateDetail);
  });

  it('clears local files, consent, result, and errors to inspect another set', async () => {
    const { events } = await submitValidInspection({
      findings: [
        {
          category: 'visible_damage',
          observation: 'Photo 1 visibly shows a scratch.',
          photo_numbers: [1],
        },
      ],
    });
    expect(await screen.findByText('Photo 1 visibly shows a scratch.')).toBeVisible();

    await events.click(screen.getByRole('button', { name: 'Inspect another set' }));

    expect(screen.getByLabelText('Choose photos').files).toHaveLength(0);
    expect(
      screen.getByRole('checkbox', {
        name: /I consent to sending these photos to OpenAI for visual inspection/i,
      }),
    ).not.toBeChecked();
    expect(screen.getByRole('button', { name: 'Inspect photos' })).toBeDisabled();
    expect(screen.queryByText('Photo 1 visibly shows a scratch.')).not.toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('does not persist findings across an unmount and remount', async () => {
    vi.spyOn(api, 'visualInspect').mockResolvedValue({
      findings: [
        {
          category: 'visible_detail',
          observation: 'Photo 1 visibly shows a blue case.',
          photo_numbers: [1],
        },
      ],
    });
    const events = userEvent.setup();
    const view = renderVisualInspection();
    selectFiles([imageFile('photo.jpg', 'image/jpeg')]);
    await events.click(
      screen.getByRole('checkbox', {
        name: /I consent to sending these photos to OpenAI for visual inspection/i,
      }),
    );
    await events.click(screen.getByRole('button', { name: 'Inspect photos' }));
    expect(await screen.findByText('Photo 1 visibly shows a blue case.')).toBeVisible();

    view.unmount();
    renderVisualInspection();

    expect(screen.queryByText('Photo 1 visibly shows a blue case.')).not.toBeInTheDocument();
    expect(api.visualInspect).toHaveBeenCalledOnce();
  });

  it('keeps filenames out of a successful rendered result', async () => {
    const privateFilename = 'private-owner-name.jpg';
    const events = userEvent.setup();
    vi.spyOn(api, 'visualInspect').mockResolvedValue({
      findings: [
        {
          category: 'visible_condition',
          observation: 'Photo 1 visibly shows light surface wear.',
          photo_numbers: [1],
        },
      ],
    });
    renderVisualInspection();
    selectFiles([imageFile(privateFilename, 'image/jpeg')]);
    expect(screen.queryByText(privateFilename)).not.toBeInTheDocument();
    await events.click(
      screen.getByRole('checkbox', {
        name: /I consent to sending these photos to OpenAI for visual inspection/i,
      }),
    );
    await events.click(screen.getByRole('button', { name: 'Inspect photos' }));

    expect(await screen.findByText('Photo 1 visibly shows light surface wear.')).toBeVisible();
    expect(screen.queryByText(privateFilename)).not.toBeInTheDocument();
  });

  it('supports labelled controls, live feedback, and keyboard submission', async () => {
    const events = userEvent.setup();
    vi.spyOn(api, 'visualInspect').mockRejectedValue(new ApiError('private detail', 503));
    renderVisualInspection();
    const fileInput = screen.getByLabelText('Choose photos');
    const consent = screen.getByRole('checkbox', {
      name: /I consent to sending these photos to OpenAI for visual inspection/i,
    });
    const submit = screen.getByRole('button', { name: 'Inspect photos' });
    selectFiles([imageFile('photo.jpg', 'image/jpeg')]);

    consent.focus();
    await events.keyboard(' ');
    expect(consent).toBeChecked();
    submit.focus();
    await events.keyboard('{Enter}');

    expect(fileInput).toHaveAccessibleName('Choose photos');
    expect(submit).toHaveAccessibleName('Inspect photos');
    expect(await screen.findByRole('alert')).toHaveAttribute('aria-live', 'assertive');
    expect(api.visualInspect).toHaveBeenCalledOnce();
  });
});
