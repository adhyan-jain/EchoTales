import React, { useEffect, useId, useState } from 'react';
import Modal from './Modal';
import Button from './Button';
import Input from './Input';

/**
 * In-app replacement for window.prompt (Review's flag and create-mention
 * actions). `validate(value)` returns an error string or null; an invalid
 * submission keeps the dialog open with the error announced next to the
 * field, instead of closing and toasting (the create-mention "not in this
 * line" case) or silently dropping the action (an empty flag note, which the
 * first version of this dialog did). Focus entry, Escape and focus restore
 * come from Modal.
 */
export default function PromptModal({
  open,
  title,
  label,
  description,
  initialValue = '',
  placeholder = '',
  submitLabel = 'Submit',
  multiline = false,
  validate,
  onSubmit,
  onClose,
}) {
  const [value, setValue] = useState(initialValue);
  const [error, setError] = useState(null);
  const fieldId = useId();
  const errorId = useId();
  const descId = useId();

  useEffect(() => {
    if (open) {
      setValue(initialValue);
      setError(null);
    }
  }, [open, initialValue]);

  if (!open) return null;

  const handleSubmit = (e) => {
    e.preventDefault();
    const trimmed = value.trim();
    const problem = validate ? validate(trimmed) : trimmed ? null : 'This field is required.';
    if (problem) {
      setError(problem);
      return;
    }
    onSubmit(trimmed);
  };

  const describedBy = [description ? descId : null, error ? errorId : null].filter(Boolean).join(' ') || undefined;
  const fieldProps = {
    id: fieldId,
    value,
    placeholder,
    autoFocus: true,
    'aria-invalid': error ? true : undefined,
    'aria-describedby': describedBy,
    onChange: (e) => {
      setValue(e.target.value);
      if (error) setError(null);
    },
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      footer={
        <>
          <Button variant="secondary" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form={`${fieldId}-form`}>
            {submitLabel}
          </Button>
        </>
      }
    >
      <form id={`${fieldId}-form`} onSubmit={handleSubmit} className="space-y-3" noValidate>
        <label htmlFor={fieldId} className="block text-sm font-medium text-text">
          {label}
        </label>
        {description && (
          <p id={descId} className="rounded-xl border border-border bg-surface2 px-3 py-2 text-sm text-muted">
            {description}
          </p>
        )}
        {multiline ? (
          <textarea
            {...fieldProps}
            // Enter submits like the single-line field; Shift+Enter adds a
            // line. Plain Enter only inserted a newline, so the keyboard
            // path to submit a flag didn't exist (QA run, 2026-09-26).
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) handleSubmit(e);
            }}
            rows={3}
            className="w-full rounded-xl border border-border bg-surface px-3 py-2 text-sm text-text placeholder:text-muted focus:border-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
          />
        ) : (
          <Input {...fieldProps} className="w-full" />
        )}
        {multiline && <p className="text-xs text-muted">Enter to submit · Shift+Enter for a new line</p>}
        {error && (
          <p id={errorId} role="alert" className="text-sm text-danger">
            {error}
          </p>
        )}
      </form>
    </Modal>
  );
}
