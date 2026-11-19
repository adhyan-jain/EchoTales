import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

jest.mock('../../api', () => ({
  api: { characters: jest.fn(), setGender: jest.fn(), setVoice: jest.fn(), selectReference: jest.fn(), searchReferences: jest.fn() },
}));

// eslint-disable-next-line import/first
import { api } from '../../api';
// eslint-disable-next-line import/first
import CharacterDashboard from '../CharacterDashboard';
// eslint-disable-next-line import/first
import GenderControl from '../GenderControl';
// eslint-disable-next-line import/first
import { ToastProvider } from '../ui/Toast';

beforeEach(() => jest.clearAllMocks());

describe('GenderControl', () => {
  test('shows the current gender and offers the three choices the server accepts', () => {
    render(<GenderControl gender="female" byReviewer={false} onChange={jest.fn()} />);
    const select = screen.getByRole('combobox', { name: 'Gender' });
    expect(select).toHaveValue('female');
    expect(screen.getAllByRole('option').map((o) => o.value)).toEqual(['male', 'female', 'unknown']);
    expect(screen.queryByText('Set by a reviewer')).not.toBeInTheDocument();
  });

  test('says when a reviewer set it, because the automatic pass will not change it', () => {
    render(<GenderControl gender="male" byReviewer onChange={jest.fn()} />);
    expect(screen.getByText('Set by a reviewer')).toBeInTheDocument();
  });

  test('choosing another gender reports it, and the select is off while saving', async () => {
    let finish;
    const onChange = jest.fn(() => new Promise((r) => { finish = r; }));
    render(<GenderControl gender="unknown" byReviewer={false} onChange={onChange} />);
    fireEvent.change(screen.getByRole('combobox', { name: 'Gender' }), { target: { value: 'male' } });
    expect(onChange).toHaveBeenCalledWith('male');
    expect(screen.getByRole('combobox', { name: 'Gender' })).toBeDisabled();
    finish();
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Gender' })).toBeEnabled());
  });

  test('a unknown value from an older server still renders as unknown', () => {
    render(<GenderControl gender={undefined} byReviewer={false} onChange={jest.fn()} />);
    expect(screen.getByRole('combobox', { name: 'Gender' })).toHaveValue('unknown');
  });
});

describe('CharacterDashboard gender', () => {
  const character = {
    id: 't:mira', self_id: 't:mira', label: 'Mira', prominence: 'PRINCIPAL', voice: null, traits: [], reference_images: [],
    gender: 'unknown', gender_by_reviewer: false,
  };

  test('a reviewer sets gender from the character page, and the list is reloaded', async () => {
    api.characters.mockResolvedValue({ characters: [character] });
    api.setGender.mockResolvedValue({});
    render(
      <ToastProvider>
        <CharacterDashboard novelId="t" selectedId="t:mira" onSelect={jest.fn()} />
      </ToastProvider>
    );
    const select = await screen.findByRole('combobox', { name: 'Gender' });
    api.characters.mockResolvedValue({ characters: [{ ...character, gender: 'female', gender_by_reviewer: true }] });
    fireEvent.change(select, { target: { value: 'female' } });
    await waitFor(() => expect(api.setGender).toHaveBeenCalledWith('t', 't:mira', 'female'));
    expect(await screen.findByText('Set by a reviewer')).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Gender' })).toHaveValue('female');
  });

  test('a failed save is reported and the shown value stays what the server has', async () => {
    api.characters.mockResolvedValue({ characters: [character] });
    api.setGender.mockRejectedValue(Object.assign(new Error('x'), { status: 500 }));
    render(
      <ToastProvider>
        <CharacterDashboard novelId="t" selectedId="t:mira" onSelect={jest.fn()} />
      </ToastProvider>
    );
    fireEvent.change(await screen.findByRole('combobox', { name: 'Gender' }), { target: { value: 'male' } });
    expect(await screen.findByText(/The server hit a problem/)).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Gender' })).toHaveValue('unknown');
  });
});
