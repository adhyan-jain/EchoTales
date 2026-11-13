import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { MemoryRouter } from 'react-router-dom';

// Behaviour fixes from the 2026-11 UI pass that have no better home: the
// server-unreachable gate, Toast's unknown-tone fallback, and AudioPlayer's
// failure state.

jest.mock('../../api', () => ({
  api: {
    authStatus: jest.fn(),
    hasToken: jest.fn(() => false),
  },
  UNAUTHORIZED_EVENT: 'echotales:unauthorized',
}));

// eslint-disable-next-line import/first
import { api } from '../../api';
// eslint-disable-next-line import/first
import AuthGate from '../app/AuthGate';
// eslint-disable-next-line import/first
import AudioPlayer from '../ui/AudioPlayer';
// eslint-disable-next-line import/first
import { ToastProvider, useToast } from '../ui/Toast';

describe('AuthGate', () => {
  test('an unreachable server can be retried without reloading the page', async () => {
    api.hasToken.mockReturnValue(false);
    api.authStatus
      .mockRejectedValueOnce(Object.assign(new Error('x'), { status: 0 }))
      .mockResolvedValueOnce({ auth_required: false });
    render(
      <MemoryRouter>
        <AuthGate />
      </MemoryRouter>
    );
    fireEvent.click(await screen.findByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(api.authStatus).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByText(/Can’t reach the EchoTales server/)).not.toBeInTheDocument());
  });
});

describe('Toast', () => {
  function Pusher({ tone }) {
    const push = useToast();
    return <button onClick={() => push('hello', tone)}>go</button>;
  }

  test('an unknown tone falls back to the info styling instead of rendering unstyled', () => {
    render(
      <ToastProvider>
        <Pusher tone="neutral" />
      </ToastProvider>
    );
    fireEvent.click(screen.getByText('go'));
    expect(screen.getByText('hello').className).toMatch(/border-border bg-surface/);
  });
});

describe('AudioPlayer', () => {
  test('a clip that cannot be played says so instead of silently doing nothing', async () => {
    const play = jest.spyOn(window.HTMLMediaElement.prototype, 'play').mockImplementation(() => Promise.reject(new Error('NotSupportedError')));
    render(<AudioPlayer label="Elena" duration="0:14" src="/nope.wav" />);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Play' }));
    });
    expect(await screen.findByText('Can’t play this clip')).toBeInTheDocument();
    play.mockRestore();
  });

  test('a media error event shows the same state', async () => {
    const { container } = render(<AudioPlayer label="Elena" duration="0:14" src="/nope.wav" />);
    // eslint-disable-next-line testing-library/no-node-access -- an <audio> element has no accessible role
    fireEvent.error(container.querySelector('audio'));
    expect(await screen.findByText('Can’t play this clip')).toBeInTheDocument();
  });
});
