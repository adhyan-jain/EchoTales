import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import VisualStyleSetting from '../VisualStyleSetting';
import { ToastProvider } from '../ui/Toast';

jest.mock('../../api', () => ({ api: { setGenre: jest.fn() } }));
// eslint-disable-next-line import/first
import { api } from '../../api';

const GENRES = [
  { id: 'xianxia', label: 'Xianxia / cultivation' },
  { id: 'modern_apocalypse', label: 'Modern apocalypse / urban fantasy' },
];
const PROJECT = { id: 'p', visual_genre: null, detected_genre: 'modern_apocalypse', effective_genre: 'modern_apocalypse', genres: GENRES };

const mount = (project = PROJECT, onChanged = jest.fn()) => {
  render(
    <ToastProvider>
      <VisualStyleSetting novelId="p" project={project} onChanged={onChanged} />
    </ToastProvider>
  );
  return onChanged;
};

test('shows what the project renders as and what detection proposes', () => {
  mount();
  expect(screen.getByTestId('effective-genre')).toHaveTextContent('Rendering as Modern apocalypse / urban fantasy');
  expect(screen.getByRole('combobox', { name: 'Genre' })).toHaveValue('');
  expect(screen.getByRole('option', { name: /Detected from the text \(Modern apocalypse/ })).toBeInTheDocument();
});

test('choosing a genre saves it and refreshes the project', async () => {
  api.setGenre.mockResolvedValue({});
  const onChanged = mount();
  fireEvent.change(screen.getByRole('combobox', { name: 'Genre' }), { target: { value: 'xianxia' } });
  await waitFor(() => expect(api.setGenre).toHaveBeenCalledWith('p', 'xianxia'));
  await waitFor(() => expect(onChanged).toHaveBeenCalled());
  expect(await screen.findByText('Visual style set to Xianxia / cultivation.')).toBeInTheDocument();
});

test('going back to detected sends null, and a failure is reported', async () => {
  api.setGenre.mockRejectedValue(Object.assign(new Error('HTTP 500'), { status: 500 }));
  const onChanged = mount({ ...PROJECT, visual_genre: 'xianxia', effective_genre: 'xianxia' });
  fireEvent.change(screen.getByRole('combobox', { name: 'Genre' }), { target: { value: '' } });
  await waitFor(() => expect(api.setGenre).toHaveBeenCalledWith('p', null));
  expect(await screen.findByText(/The server hit a problem handling that/)).toBeInTheDocument();
  expect(onChanged).not.toHaveBeenCalled();
});

test('renders nothing for an older server that does not report genres', () => {
  const { container } = render(
    <ToastProvider>
      <VisualStyleSetting novelId="p" project={{ id: 'p' }} onChanged={jest.fn()} />
    </ToastProvider>
  );
  expect(container.querySelector('#visual-genre')).toBeNull();
});
