import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import { MemoryRouter } from 'react-router-dom';
import JobFailure from '../components/ui/JobFailure';
import { ProjectProblem } from '../components/app/Chrome';

// Failure copy that people read: a failed job and a project that cannot
// load. Both were raw server text before the 2026-09-26 failure-state QA.

test('a failed job explains itself in plain language and hides the exception behind a disclosure', () => {
  render(<JobFailure kind="render" summary={'ValueError: chapter 999 has no beats'} />);
  expect(screen.getByText(/this render did not finish/i)).toBeInTheDocument();
  expect(screen.getByText(/partial output/i)).toBeInTheDocument();
  const detail = screen.getByText('Technical detail');
  fireEvent.click(detail);
  expect(screen.getByText(/chapter 999 has no beats/)).toBeInTheDocument();
});

test('a very long exception is truncated', () => {
  render(<JobFailure summary={'x'.repeat(5000)} />);
  expect(screen.getByText(/^x+$/).textContent.length).toBe(400);
});

test('a project that does not exist is a dead end with a way out, not an error dump', () => {
  render(
    <MemoryRouter>
      <ProjectProblem error="That wasn’t found on this server." status={404} onRetry={() => {}} />
    </MemoryRouter>
  );
  expect(screen.getByText('Project not found')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'All projects' })).toHaveAttribute('href', '/projects');
  expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument(); // retrying a 404 is pointless
});

test('other load failures offer a retry', () => {
  const retry = jest.fn();
  render(
    <MemoryRouter>
      <ProjectProblem error="The server hit a problem handling that." status={500} onRetry={retry} />
    </MemoryRouter>
  );
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
  expect(retry).toHaveBeenCalled();
});
