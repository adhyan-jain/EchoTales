import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

jest.mock('../../api', () => ({
  api: { listProjectVoices: jest.fn(), uploadProjectVoice: jest.fn() },
}));

// eslint-disable-next-line import/first
import { api } from '../../api';
// eslint-disable-next-line import/first
import ProjectVoicesPanel from '../ProjectVoicesPanel';
// eslint-disable-next-line import/first
import { ToastProvider } from '../ui/Toast';

const STATEMENT = "This is my voice or I have the speaker's permission.";

const mount = () =>
  render(
    <ToastProvider>
      <ProjectVoicesPanel novelId="b" />
    </ToastProvider>
  );

const fill = (file = new File(['x'], 'me.wav', { type: 'audio/wav' })) => {
  fireEvent.change(screen.getByLabelText('Voice name'), { target: { value: 'My voice' } });
  fireEvent.change(screen.getByLabelText('Recording'), { target: { files: [file] } });
  return file;
};

beforeEach(() => {
  jest.clearAllMocks();
  api.listProjectVoices.mockResolvedValue({
    statement: STATEMENT,
    limits: { min_seconds: 3, max_seconds: 60, max_bytes: 20971520 },
    voices: [],
  });
});

test('shows the consent statement as the checkbox label and the limits of a recording', async () => {
  mount();
  expect(await screen.findByLabelText(STATEMENT)).not.toBeChecked();
  expect(screen.getByText(/between 3 and 60 seconds/)).toBeInTheDocument();
  expect(screen.getByText(/WAV or FLAC/)).toBeInTheDocument();
});

test('the upload stays off until a name, a recording and the consent box are all given', async () => {
  mount();
  const consent = await screen.findByLabelText(STATEMENT);
  const upload = screen.getByRole('button', { name: 'Add this voice' });
  expect(upload).toBeDisabled();
  fill();
  expect(upload).toBeDisabled(); // everything but the consent
  fireEvent.click(consent);
  expect(upload).toBeEnabled();
  fireEvent.click(consent);
  expect(upload).toBeDisabled();
});

test('uploading sends the file with the details and the consent, then lists the voice', async () => {
  api.uploadProjectVoice.mockResolvedValue({ voice_id: 'project:my-voice' });
  mount();
  const consent = await screen.findByLabelText(STATEMENT);
  const file = fill();
  fireEvent.change(screen.getByLabelText('Gender'), { target: { value: 'male' } });
  fireEvent.change(screen.getByLabelText('Age'), { target: { value: '41' } });
  fireEvent.click(consent);
  api.listProjectVoices.mockResolvedValue({
    statement: STATEMENT,
    limits: { min_seconds: 3, max_seconds: 60 },
    voices: [{ voice_id: 'project:my-voice', name: 'My voice', gender: 'male', age: 41, consent_at: '2026-11-19T10:00:00+0000' }],
  });
  fireEvent.click(screen.getByRole('button', { name: 'Add this voice' }));
  await waitFor(() =>
    expect(api.uploadProjectVoice).toHaveBeenCalledWith('b', file, { name: 'My voice', gender: 'male', age: 41, consent: true })
  );
  expect(await screen.findByText('My voice')).toBeInTheDocument();
  expect(screen.getByText(/Consent recorded/)).toBeInTheDocument();
  // The form clears so the same recording is not added twice by accident.
  expect(screen.getByLabelText(STATEMENT)).not.toBeChecked();
  expect(screen.getByLabelText('Voice name')).toHaveValue('');
});

test('a refusal from the server is shown and the form is kept for another try', async () => {
  api.uploadProjectVoice.mockRejectedValue(
    Object.assign(new Error('x'), { status: 400, serverMessage: 'the recording is 1.0 s; it must be between 3 and 60 s' })
  );
  mount();
  const consent = await screen.findByLabelText(STATEMENT);
  fill();
  fireEvent.click(consent);
  fireEvent.click(screen.getByRole('button', { name: 'Add this voice' }));
  expect(await screen.findByText('the recording is 1.0 s; it must be between 3 and 60 s')).toBeInTheDocument();
  expect(screen.getByLabelText('Voice name')).toHaveValue('My voice');
});

test('with no voices yet it says the list is empty', async () => {
  mount();
  expect(await screen.findByText(/No voices of your own yet/)).toBeInTheDocument();
});
