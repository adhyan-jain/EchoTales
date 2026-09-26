import React, { useEffect, useId, useRef } from 'react';
import useDialogFocus from '../../lib/useDialogFocus';

export default function Modal({ open, onClose, title, children, footer }) {
  const titleId = useId();
  const panelRef = useRef(null);
  const downOnBackdrop = useRef(false);
  useDialogFocus(open, panelRef);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => e.key === 'Escape' && onClose?.();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  // Bottom sheet on phones (thumb reach, room for the keyboard), centred
  // card from sm up.
  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center overscroll-contain bg-black/60 backdrop-blur-sm sm:items-center sm:p-4"
      // Close only when the press *started and ended* on the backdrop: a
      // text-selection drag from the textarea that ends outside the panel
      // used to dismiss the dialog and lose the typed note.
      onMouseDown={(e) => {
        downOnBackdrop.current = e.target === e.currentTarget;
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget && downOnBackdrop.current) onClose?.();
        downOnBackdrop.current = false;
      }}
    >
      <div
        className="max-h-[85dvh] w-full max-w-lg overflow-y-auto overscroll-contain rounded-t-2xl border border-border bg-surface shadow-popover animate-reveal focus:outline-none sm:rounded-2xl"
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
      >
        {title && (
          <div className="border-b border-border px-5 py-4">
            <h2 id={titleId} className="font-display text-xl font-semibold text-text">{title}</h2>
          </div>
        )}
        <div className="p-5">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-border px-5 py-4">{footer}</div>}
      </div>
    </div>
  );
}
