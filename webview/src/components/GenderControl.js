import React, { useState } from 'react';
import Label from './ui/Label';

// The three values the server's `set_gender` correction accepts (corrections.py::_apply_set_gender).
const OPTIONS = [
  { value: 'male', label: 'Male' },
  { value: 'female', label: 'Female' },
  { value: 'unknown', label: 'Unknown' },
];

/* A character's gender picks the voice and the look. The automatic pass guesses it from titles and pronouns; once a
   reviewer sets it here the pass never overwrites it, which the tag beside the control says. `onChange` returns a
   promise so the select stays off until the server has the value. */
export default function GenderControl({ gender, byReviewer, onChange, disabled = false }) {
  const [saving, setSaving] = useState(false);
  const value = OPTIONS.some((o) => o.value === gender) ? gender : 'unknown';

  const change = (e) => {
    setSaving(true);
    Promise.resolve(onChange(e.target.value))
      .catch(() => {})
      .finally(() => setSaving(false));
  };

  return (
    <div className="flex flex-wrap items-center gap-3">
      <label htmlFor="character-gender" className="text-xs font-semibold uppercase tracking-[0.14em] text-muted">
        Gender
      </label>
      <select
        id="character-gender"
        value={value}
        disabled={disabled || saving}
        onChange={change}
        className="h-9 rounded-xl border border-border bg-transparent px-3 font-sans text-sm text-text"
      >
        {OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      {byReviewer && <Label tone="warning">Set by a reviewer</Label>}
    </div>
  );
}
