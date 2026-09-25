import React, { useEffect, useId, useRef } from 'react';

export default function Modal({ open, onClose, title, children, footer }) {
  const titleId = useId();
  const panelRef = useRef(null);

  // Focus moves into the dialog on open and back to the opener on close, so
  // a keyboard user is not left on a control hidden behind the overlay.
  useEffect(() => {
    if (!open) return undefined;
    const opener = document.activeElement;
    panelRef.current?.focus();
    return () => {
      if (opener && opener !== document.body && document.contains(opener)) opener.focus();
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e) => e.key === 'Escape' && onClose?.();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center overscroll-contain bg-black/60 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto overscroll-contain rounded-2xl border border-border bg-surface shadow-popover animate-reveal focus:outline-none"
        onClick={(e) => e.stopPropagation()}
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
