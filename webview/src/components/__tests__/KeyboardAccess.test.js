import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import EntityPicker from '../EntityPicker';
import EntitySidebar from '../EntitySidebar';
import ScriptLine from '../ScriptLine';

// The review UI's edit actions were mouse-only: picker rows and cast rows were
// clickable <li>s, and mentions/speakers were clickable <mark>/<div>s with no
// key handler (web-design-guidelines audit, 2026-09-26). These tests pin the
// keyboard path for each.

const ENTITIES = [
  { id: 'a', label: 'Fang Yuan', colour: '#b38a2e', count: 12, aliases: ['Fang Yuan'], first_chapter: 1, last_chapter: 9 },
  { id: 'b', label: 'Bai Ning Bing', colour: '#6f9164', count: 4, aliases: ['Bai Ning Bing'], first_chapter: 3, last_chapter: 5 },
];

describe('EntityPicker', () => {
  it('exposes each character as a button and moves through them with arrow keys', () => {
    const onSelect = jest.fn();
    render(<EntityPicker entities={ENTITIES} onSelect={onSelect} onCreateNew={jest.fn()} onCancel={jest.fn()} />);
    const input = screen.getByRole('textbox', { name: /search or type a new name/i });
    expect(input).toHaveFocus();

    fireEvent.keyDown(input, { key: 'ArrowDown' });
    const first = screen.getByRole('button', { name: /fang yuan/i });
    expect(first).toHaveFocus();

    fireEvent.keyDown(first, { key: 'ArrowDown' });
    const second = screen.getByRole('button', { name: /bai ning bing/i });
    expect(second).toHaveFocus();

    fireEvent.click(second);
    expect(onSelect).toHaveBeenCalledWith('b');
  });

  it('closes on Escape from inside the list, not only from the input', () => {
    const onCancel = jest.fn();
    render(<EntityPicker entities={ENTITIES} onSelect={jest.fn()} onCreateNew={jest.fn()} onCancel={onCancel} />);
    fireEvent.keyDown(screen.getByRole('button', { name: /fang yuan/i }), { key: 'Escape' });
    expect(onCancel).toHaveBeenCalled();
  });
});

describe('EntitySidebar', () => {
  it('toggles focus from a real button and labels the merge control', () => {
    const onToggleFocus = jest.fn();
    render(
      <EntitySidebar
        entities={ENTITIES}
        search=""
        onSearchChange={jest.fn()}
        focusId={null}
        onToggleFocus={onToggleFocus}
        editMode
        mergeSourceId={null}
        onStartMerge={jest.fn()}
        onConfirmMerge={jest.fn()}
        onCancelMerge={jest.fn()}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: /^fang yuan/i }));
    expect(onToggleFocus).toHaveBeenCalledWith('a');
    expect(screen.getByRole('button', { name: 'Merge Fang Yuan into another entity' })).toBeInTheDocument();
    expect(screen.getByRole('searchbox', { name: /filter entities/i })).toBeInTheDocument();
  });
});

describe('ScriptLine', () => {
  const span = {
    span_id: 's1',
    type: 'DIALOGUE',
    text: 'Fang Yuan smiled.',
    speaker: 'Fang Yuan',
    speaker_id: 'a',
    method: 'rule',
    marks: [{ id: 'a', mention_id: 'm1', s: 0, e: 9, resolved: true, colour: '#b38a2e', label: 'Fang Yuan', conf: 1 }],
  };
  const noop = () => {};

  it('opens the mention picker from the keyboard, anchored at the element', () => {
    const onMentionClick = jest.fn();
    render(
      <ScriptLine
        span={span}
        editMode
        onMarkHover={noop}
        onMarkMove={noop}
        onMarkLeave={noop}
        onMentionClick={onMentionClick}
        onSpeakerClick={noop}
        onFlagLine={noop}
        onRetype={noop}
      />
    );
    const mark = screen.getByRole('button', { name: /reassign mention fang yuan/i });
    expect(mark).toHaveAttribute('tabindex', '0');
    fireEvent.keyDown(mark, { key: 'Enter' });
    expect(onMentionClick).toHaveBeenCalledTimes(1);
    const [, evt] = onMentionClick.mock.calls[0];
    expect(Number.isFinite(evt.clientX)).toBe(true);
    expect(Number.isFinite(evt.clientY)).toBe(true);
  });

  it('is plain text when not editing', () => {
    render(
      <ScriptLine span={span} editMode={false} onMarkHover={noop} onMarkMove={noop} onMarkLeave={noop} />
    );
    expect(screen.queryByRole('button', { name: /reassign mention/i })).not.toBeInTheDocument();
  });
});
