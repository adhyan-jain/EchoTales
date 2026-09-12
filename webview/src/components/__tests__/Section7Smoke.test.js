import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

// Section 7 verification gap: nobody had actually mounted these components
// in a JS runtime before this test existed -- ESLint and a production
// `build` catch syntax/type errors, not runtime errors from a bad prop
// access, a hook misuse, or a mocked API shape mismatch. This is the
// closest thing to "opened it in a browser and clicked around" available
// without a browser tool in this session.

jest.mock('../../api', () => ({
  api: {
    login: jest.fn(),
    authStatus: jest.fn(),
    createProject: jest.fn(),
    characters: jest.fn(),
    setVoice: jest.fn(),
    selectReference: jest.fn(),
    hasToken: jest.fn(() => false),
  },
}));

// eslint-disable-next-line import/first
import { api } from '../../api';
// eslint-disable-next-line import/first
import Login from '../Login';
// eslint-disable-next-line import/first
import NewProject from '../NewProject';
// eslint-disable-next-line import/first
import CharacterDashboard from '../CharacterDashboard';
// eslint-disable-next-line import/first
import { ToastProvider } from '../ui/Toast';

// CharacterDashboard uses useToast() to surface override results -- it must
// be mounted under a ToastProvider the way index.js actually wraps the app,
// or the hook throws instead of the component under test rendering at all.
function renderDashboard(props) {
  return render(
    <ToastProvider>
      <CharacterDashboard {...props} />
    </ToastProvider>
  );
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe('Login', () => {
  test('renders and submits a password', async () => {
    api.login.mockResolvedValueOnce({ token: 'tok123' });
    const onLoggedIn = jest.fn();
    render(<Login onLoggedIn={onLoggedIn} />);

    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'hunter2' } });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => expect(onLoggedIn).toHaveBeenCalledTimes(1));
    expect(api.login).toHaveBeenCalledWith('hunter2');
  });

  test('shows an inline error on failure, does not crash, does not call onLoggedIn', async () => {
    api.login.mockRejectedValueOnce(new Error('wrong password'));
    const onLoggedIn = jest.fn();
    render(<Login onLoggedIn={onLoggedIn} />);

    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'bad' } });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    expect(await screen.findByText(/wrong password/i)).toBeInTheDocument();
    expect(onLoggedIn).not.toHaveBeenCalled();
  });
});

describe('NewProject', () => {
  // Content type is a set of clickable cards now, not a <select> -- and
  // "Roleplay" is deliberately disabled (coming soon, per the client brief),
  // so the non-default case this test exercises is "Short story" instead.
  test('derives a slug id from the title and submits content_type', async () => {
    api.createProject.mockResolvedValueOnce({
      id: 'my-cool-story',
      title: 'My Cool Story!',
      content_type: 'short_story',
    });
    const onCreated = jest.fn();
    render(<NewProject onCreated={onCreated} />);

    fireEvent.change(screen.getByPlaceholderText(/reverend insanity/i), {
      target: { value: 'My Cool Story!' },
    });
    expect(screen.getByText('my-cool-story')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /short story/i }));
    fireEvent.click(screen.getByRole('button', { name: /create project/i }));

    await waitFor(() =>
      expect(api.createProject).toHaveBeenCalledWith('my-cool-story', 'My Cool Story!', 'short_story')
    );
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith({
      id: 'my-cool-story',
      title: 'My Cool Story!',
      content_type: 'short_story',
    }));

    // Roleplay is present but not selectable yet.
    expect(screen.getByRole('button', { name: /roleplay/i })).toBeDisabled();

    // The honesty note about ingest being a separate step must actually render.
    expect(screen.getByText(/ingested separately, via the CLI/i)).toBeInTheDocument();
    // ...and there's no fake upload/progress -- the file input is disabled,
    // with the real CLI command shown instead.
    expect(screen.getByText(/upload isn't wired up yet/i)).toBeInTheDocument();
  });

  test('shows an inline error on failure', async () => {
    api.createProject.mockRejectedValueOnce(new Error('project already exists'));
    render(<NewProject onCreated={jest.fn()} />);

    fireEvent.change(screen.getByPlaceholderText(/reverend insanity/i), {
      target: { value: 'Dup' },
    });
    fireEvent.click(screen.getByRole('button', { name: /create project/i }));

    expect(await screen.findByText(/project already exists/i)).toBeInTheDocument();
  });
});

describe('CharacterDashboard', () => {
  const baseCharacters = () => ({
    novel_id: 'reverend-insanity',
    characters: [
      {
        self_id: 'reverend-insanity:self1',
        persona_id: 'reverend-insanity:self1:body1',
        label: 'Fang Yuan',
        prominence: 'PRINCIPAL',
        voice: {
          speaker_id: 'reverend-insanity:self1',
          speaker_label: 'Fang Yuan',
          voice: 'p227',
          sample_audio_path: 'data/audio/reverend-insanity/ch1/x.wav',
        },
        traits: [
          {
            key: 'eye_color',
            value: 'red',
            evidence: 'attested ch18; 60 passages',
            confidence: 0.9,
            provenance: 'NARRATOR',
          },
        ],
        reference_images: [
          { id: 'r1', source_url: 'https://example.com/a.png', thumbnail_url: '', title: 'A', selected: true, user_uploaded: false },
          { id: 'r2', source_url: 'https://example.com/b.png', thumbnail_url: '', title: 'B', selected: false, user_uploaded: false },
        ],
      },
    ],
  });

  test('lists the cast, then drills into a character to show voice, references, and evidence', async () => {
    api.characters.mockResolvedValueOnce(baseCharacters());

    renderDashboard({ novelId: "reverend-insanity" });

    // Cast list first -- name shown via the row, not the full detail yet.
    const row = await screen.findByText('Fang Yuan');
    expect(screen.queryByText(/eye_color/)).not.toBeInTheDocument();

    fireEvent.click(row);

    expect(await screen.findByText(/eye_color: red/)).toBeInTheDocument();
    expect(screen.getByText(/attested ch18; 60 passages/)).toBeInTheDocument();
    expect(screen.getByText(/90% confidence/)).toBeInTheDocument();

    // "Replace" on the unselected reference image calls the select endpoint.
    api.selectReference.mockResolvedValueOnce({ id: 'r2', source_url: 'https://example.com/b.png' });
    api.characters.mockResolvedValueOnce(baseCharacters());
    const replaceButtons = screen.getAllByRole('button', { name: 'Replace' });
    expect(replaceButtons.length).toBe(1); // the selected candidate has no Replace button
    fireEvent.click(replaceButtons[0]);
    await waitFor(() =>
      expect(api.selectReference).toHaveBeenCalledWith(
        'reverend-insanity',
        'reverend-insanity:self1',
        'r2',
        'selected via dashboard'
      )
    );

    // img2img isn't wired up server-side yet -- rendered honestly disabled.
    expect(screen.getAllByRole('button', { name: 'Edit reference' })[0]).toBeDisabled();
  });

  test('incidental characters are collapsed behind a real count until expanded', async () => {
    api.characters.mockResolvedValueOnce({
      novel_id: 'reverend-insanity',
      characters: [
        ...baseCharacters().characters,
        { self_id: 'x1', label: 'Innkeeper', prominence: 'INCIDENTAL', traits: [], reference_images: [] },
        { self_id: 'x2', label: 'Guard', prominence: 'INCIDENTAL', traits: [], reference_images: [] },
      ],
    });

    renderDashboard({ novelId: "reverend-insanity" });

    await screen.findByText('Fang Yuan');
    expect(screen.queryByText('Innkeeper')).not.toBeInTheDocument();

    const toggle = screen.getByText('Show 2 incidental characters');
    fireEvent.click(toggle);

    expect(await screen.findByText('Innkeeper')).toBeInTheDocument();
    expect(screen.getByText('Guard')).toBeInTheDocument();
  });

  test('a fresh project with no character data yet degrades to an honest empty state, not a crash', async () => {
    const err = new Error('not found');
    err.status = 404;
    api.characters.mockRejectedValueOnce(err);

    renderDashboard({ novelId: "brand-new-project" });

    expect(await screen.findByText(/haven.t been generated/i)).toBeInTheDocument();
  });

  test('a real backend error is shown, not swallowed', async () => {
    api.characters.mockRejectedValueOnce(new Error('HTTP 500'));
    renderDashboard({ novelId: "reverend-insanity" });
    expect(await screen.findByText(/HTTP 500/)).toBeInTheDocument();
  });
});
