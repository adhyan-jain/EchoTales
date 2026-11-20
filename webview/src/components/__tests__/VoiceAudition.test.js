import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

jest.mock('../../api', () => ({
  api: {
    voiceAudition: jest.fn(),
    voiceSample: jest.fn(),
    setNarrator: jest.fn(),
    triggerStage: jest.fn(),
    listProjectVoices: jest.fn(),
    uploadProjectVoice: jest.fn(),
    outputFileUrl: (novel, path) => `/files/${novel}/${path}`,
  },
}));
jest.mock('../../lib/jobs', () => ({ waitForJob: jest.fn() }));

/* eslint-disable import/first */
import { api } from '../../api';
import { waitForJob } from '../../lib/jobs';
import NarratorAudition from '../NarratorAudition';
import LineAudition from '../LineAudition';
import ProjectVoicesPanel from '../ProjectVoicesPanel';
import { ToastProvider } from '../ui/Toast';
/* eslint-enable import/first */

const wrap = (ui) => render(<ToastProvider>{ui}</ToastProvider>);
const notFound = () => Object.assign(new Error('nf'), { status: 404 });

const CANDIDATES = {
  narrator: 'hifitts92',
  passage: 'The corridor swallowed the lantern light.',
  candidates: [
    { voice_id: 'hifitts92', name: 'Cori Samuel', gender: 'female', bank: 'hifitts', licence: 'CC BY 4.0', f0_hz: 201, sample: 'audition/narrator/hifitts92/p1_dark.wav' },
    { voice_id: 'libritts_r2803', name: 'Reader Two', gender: 'male', bank: 'libritts_r', licence: 'CC BY 4.0', f0_hz: 112, sample: null },
  ],
};

beforeEach(() => {
  jest.resetAllMocks();
  api.voiceAudition.mockResolvedValue(CANDIDATES);
  api.listProjectVoices.mockResolvedValue({ statement: 's', limits: {}, voices: [] });
});

describe('NarratorAudition', () => {
  test('lists the shortlisted candidates, each with a labelled player, and marks the current narrator', async () => {
    wrap(<NarratorAudition novelId="b" />);
    expect(await screen.findByRole('radio', { name: /Cori Samuel/ })).toBeChecked();
    expect(screen.getByText('current narrator')).toBeInTheDocument();
    expect(screen.getByLabelText('Sample of Cori Samuel')).toHaveAttribute('src', '/files/b/audition/narrator/hifitts92/p1_dark.wav');
    expect(screen.getByText('No sample voiced yet.')).toBeInTheDocument();
    expect(screen.getAllByText(/CC BY 4.0/).length).toBe(2);
    expect(screen.getByText(/The corridor swallowed/)).toBeInTheDocument();
  });

  test('picking another candidate enables Use as narrator, which writes that voice and reloads', async () => {
    wrap(<NarratorAudition novelId="b" />);
    const use = await screen.findByRole('button', { name: 'Use as narrator' });
    expect(use).toBeDisabled(); // the chosen one is already the narrator
    fireEvent.click(screen.getByRole('radio', { name: /Reader Two/ }));
    expect(use).toBeEnabled();
    api.setNarrator.mockResolvedValue({ narrator: 'libritts_r2803' });
    api.voiceAudition.mockResolvedValue({ ...CANDIDATES, narrator: 'libritts_r2803' });
    fireEvent.click(use);
    await waitFor(() => expect(api.setNarrator).toHaveBeenCalledWith('b', 'libritts_r2803'));
    // The old row's label is replaced when the list reloads; wait for the Use button to go off (nothing left to change).
    await waitFor(() => expect(screen.getByRole('button', { name: 'Use as narrator' })).toBeDisabled());
    expect(screen.getByText('current narrator').closest('li')).toHaveTextContent('Reader Two');
  });

  test('the radio group is reachable by keyboard: native radios in one named group', async () => {
    wrap(<NarratorAudition novelId="b" />);
    const radios = await screen.findAllByRole('radio');
    expect(radios).toHaveLength(2);
    expect(new Set(radios.map((r) => r.name))).toEqual(new Set(['narrator']));
    expect(screen.getByRole('group', { name: 'Candidates' })).toBeInTheDocument();
  });

  test('finding candidates queues one narrator job, waits for it, and reloads the list', async () => {
    api.voiceAudition.mockResolvedValueOnce({ narrator: '', passage: 'p', candidates: [] });
    api.triggerStage.mockResolvedValue({ job_id: 'j1' });
    waitForJob.mockResolvedValue({ status: 'SUCCEEDED' });
    wrap(<NarratorAudition novelId="b" />);
    expect(await screen.findByText(/No candidates yet/)).toBeInTheDocument();
    api.voiceAudition.mockResolvedValue(CANDIDATES);
    fireEvent.click(screen.getByRole('button', { name: 'Find narrator candidates' }));
    await waitFor(() => expect(api.triggerStage).toHaveBeenCalledWith('b', 'voice_audition', { target: 'narrator' }));
    expect(await screen.findByRole('radio', { name: /Cori Samuel/ })).toBeInTheDocument();
  });

  test('a failed audition job says so and keeps the technical text behind a disclosure', async () => {
    api.triggerStage.mockResolvedValue({ job_id: 'j1' });
    waitForJob.mockResolvedValue({ status: 'FAILED', error_summary: 'no voice bank found under data/voice' });
    wrap(<NarratorAudition novelId="b" />);
    fireEvent.click(await screen.findByRole('button', { name: 'Find new candidates' }));
    expect(await screen.findByText(/did not finish/)).toBeInTheDocument();
    expect(screen.getByText(/no voice bank found/)).toBeInTheDocument();
  });

  test('a load failure is announced', async () => {
    api.voiceAudition.mockRejectedValue(Object.assign(new Error('x'), { status: 0 }));
    wrap(<NarratorAudition novelId="b" />);
    expect(await screen.findByRole('alert')).toHaveTextContent(/reach the EchoTales server/);
  });
});

describe('LineAudition', () => {
  const open = async (props = {}) => {
    wrap(<LineAudition novelId="b" assignedVoiceId="hifitts92" onUseVoice={jest.fn()} {...props} />);
    await screen.findByRole('option', { name: /hifitts92 \(assigned\)/ });
  };

  test('offers the assigned voice first, then uploaded voices, then the shortlist, without repeats', async () => {
    api.listProjectVoices.mockResolvedValue({ voices: [{ voice_id: 'project:me', name: 'Me', gender: 'female', age: 30, consent_at: 'x' }] });
    await open();
    const labels = screen.getAllByRole('option').filter((o) => o.closest('select').id === 'la-voice').map((o) => o.textContent);
    expect(labels).toEqual(['hifitts92 (assigned)', 'Me (your own voice)', 'Reader Two (male, libritts_r)']);
  });

  test('hearing a line queues a sample job with the chosen voice, emotion and words, then plays it', async () => {
    await open();
    api.voiceSample.mockRejectedValueOnce(notFound()).mockResolvedValueOnce({ path: 'audition/lines/k.wav' });
    api.triggerStage.mockResolvedValue({ job_id: 'j2' });
    waitForJob.mockResolvedValue({ status: 'SUCCEEDED' });
    fireEvent.change(screen.getByLabelText('Delivery'), { target: { value: 'anger' } });
    fireEvent.change(screen.getByLabelText('Line to hear'), { target: { value: '  Get out.  ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Hear this line' }));
    await waitFor(() =>
      expect(api.triggerStage).toHaveBeenCalledWith('b', 'voice_audition', {
        target: 'line', voice_id: 'hifitts92', emotion: 'anger', text: 'Get out.',
      })
    );
    expect(await screen.findByLabelText('Sample of the line')).toHaveAttribute('src', '/files/b/audition/lines/k.wav');
  });

  test('a sample that already exists is played without queueing a job', async () => {
    await open();
    api.voiceSample.mockResolvedValue({ path: 'audition/lines/k.wav' });
    fireEvent.click(screen.getByRole('button', { name: 'Hear this line' }));
    expect(await screen.findByLabelText('Sample of the line')).toBeInTheDocument();
    expect(api.triggerStage).not.toHaveBeenCalled();
  });

  test('another voice can be tried and then kept for the character; the assigned one cannot be re-applied', async () => {
    const onUseVoice = jest.fn();
    await open({ onUseVoice });
    api.voiceSample.mockResolvedValue({ path: 'audition/lines/k.wav' });
    fireEvent.click(screen.getByRole('button', { name: 'Hear this line' }));
    await screen.findByLabelText('Sample of the line');
    expect(screen.queryByRole('button', { name: /Use this voice/ })).toBeNull();
    fireEvent.change(screen.getByLabelText('Voice'), { target: { value: 'libritts_r2803' } });
    expect(screen.queryByLabelText('Sample of the line')).toBeNull(); // stale once the voice changes
    fireEvent.click(screen.getByRole('button', { name: 'Hear this line' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Use this voice for the character' }));
    expect(onUseVoice).toHaveBeenCalledWith('libritts_r2803');
  });

  test('an empty line cannot be sent', async () => {
    await open();
    fireEvent.change(screen.getByLabelText('Line to hear'), { target: { value: '   ' } });
    expect(screen.getByRole('button', { name: 'Hear this line' })).toBeDisabled();
  });

  test('a failed sample job shows the failure, not a player', async () => {
    await open();
    api.voiceSample.mockRejectedValue(notFound());
    api.triggerStage.mockResolvedValue({ job_id: 'j3' });
    waitForJob.mockResolvedValue({ status: 'FAILED', error_summary: "voice 'x' is not in the voice bank" });
    fireEvent.click(screen.getByRole('button', { name: 'Hear this line' }));
    expect(await screen.findByText(/did not finish/)).toBeInTheDocument();
    expect(screen.queryByLabelText('Sample of the line')).toBeNull();
    expect(screen.getByRole('button', { name: 'Hear this line' })).toBeEnabled();
  });
});

describe('uploaded voice preview', () => {
  const mine = {
    statement: "This is my voice or I have the speaker's permission.",
    limits: { min_seconds: 3, max_seconds: 60 },
    voices: [{ voice_id: 'project:me', name: 'Me', gender: 'female', age: 30, consent_at: '2026-11-20T10:00:00', clip: 'voices/me.wav' }],
  };

  test('plays the uploaded recording and keeps the consent wording', async () => {
    api.listProjectVoices.mockResolvedValue(mine);
    wrap(<ProjectVoicesPanel novelId="b" />);
    expect(await screen.findByLabelText('Your recording of Me')).toHaveAttribute('src', '/files/b/voices/me.wav');
    expect(screen.getByLabelText(mine.statement)).toBeInTheDocument();
  });

  test('a synthesized sample is made on request and then played', async () => {
    api.listProjectVoices.mockResolvedValue(mine);
    api.voiceSample.mockRejectedValueOnce(notFound()).mockResolvedValueOnce({ path: 'audition/lines/p.wav' });
    api.triggerStage.mockResolvedValue({ job_id: 'j4' });
    waitForJob.mockResolvedValue({ status: 'SUCCEEDED' });
    wrap(<ProjectVoicesPanel novelId="b" />);
    fireEvent.click(await screen.findByRole('button', { name: 'Hear a synthesized sample' }));
    expect(await screen.findByLabelText('Synthesized sample of Me')).toHaveAttribute('src', '/files/b/audition/lines/p.wav');
    expect(api.triggerStage).toHaveBeenCalledWith('b', 'voice_audition', expect.objectContaining({ target: 'line', voice_id: 'project:me', emotion: 'neutral' }));
  });
});
