import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import ScriptLine from '../ScriptLine';
import { DELIVERY_EMOTIONS } from '../../lib/delivery';

const base = {
  span_id: 'n:1:0:1', type: 'DIALOGUE', text: '"Go," she said.', speaker: 'Mira', speaker_id: 'n:mira', marks: [], method: 'EXPLICIT',
};

function mount(span = base, props = {}) {
  const onSetDelivery = jest.fn();
  render(
    <ScriptLine
      span={span}
      editMode
      onMarkHover={jest.fn()} onMarkMove={jest.fn()} onMarkLeave={jest.fn()}
      onMentionClick={jest.fn()} onSpeakerClick={jest.fn()} onFlagLine={jest.fn()} onRetype={jest.fn()}
      onSetDelivery={onSetDelivery}
      {...props}
    />
  );
  return onSetDelivery;
}

test('a dialogue line offers an emotion and an intensity 1 to 3 while editing', () => {
  mount();
  const emotion = screen.getByRole('combobox', { name: 'Line emotion' });
  expect(emotion).toHaveValue('');
  expect(screen.getByRole('option', { name: 'Not set (the reader’s guess)' })).toBeInTheDocument();
  expect(screen.getByRole('option', { name: 'angry' })).toHaveValue('anger');
  expect(screen.getAllByRole('option').filter((o) => DELIVERY_EMOTIONS.some((e) => e.value === o.value)).length).toBe(DELIVERY_EMOTIONS.length);
  const intensity = screen.getByRole('combobox', { name: 'Line intensity' });
  expect([...intensity.querySelectorAll('option')].map((o) => o.value)).toEqual(['1', '2', '3']);
  expect(intensity).toBeDisabled(); // an intensity of nothing means nothing
});

test('choosing an emotion sends it with the intensity shown (2 by default)', () => {
  const onSetDelivery = mount();
  fireEvent.change(screen.getByRole('combobox', { name: 'Line emotion' }), { target: { value: 'anger' } });
  expect(onSetDelivery).toHaveBeenCalledWith(expect.objectContaining({ span_id: 'n:1:0:1' }), 'anger', 2);
});

test('the current delivery is shown, and changing only the intensity keeps the emotion', () => {
  const onSetDelivery = mount({ ...base, delivery: { emotion: 'fear', intensity: 1, pending: false } });
  expect(screen.getByRole('combobox', { name: 'Line emotion' })).toHaveValue('fear');
  const intensity = screen.getByRole('combobox', { name: 'Line intensity' });
  expect(intensity).toHaveValue('1');
  fireEvent.change(intensity, { target: { value: '3' } });
  expect(onSetDelivery).toHaveBeenCalledWith(expect.anything(), 'fear', 3);
});

test('a change not yet applied says so', () => {
  mount({ ...base, delivery: { emotion: 'anger', intensity: 3, pending: true } });
  expect(screen.getByText('Not applied yet')).toBeInTheDocument();
});

test('narration and reading mode have no delivery control', () => {
  mount({ ...base, type: 'NARRATION_ACTION', speaker: null });
  expect(screen.queryByRole('combobox', { name: 'Line emotion' })).not.toBeInTheDocument();
});

test('without a handler (the read page) there is no control', () => {
  mount(base, { onSetDelivery: undefined });
  expect(screen.queryByRole('combobox', { name: 'Line emotion' })).not.toBeInTheDocument();
});
