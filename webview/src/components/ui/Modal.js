import React, { useEffect, useId, useRef } from 'react';

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

export default function Modal({ open, onClose, title, children, footer }) {
  const titleId = useId();
  const panelRef = useRef(null);

  // The opener is captured during render, not in the effect: by the time an
  // effect runs, a child with autoFocus (every PromptModal field) has already
  // taken focus, so the "opener" recorded there was the dialog's own field
  // and focus was restored to a removed node (caught by ReviewDialogs.test,
  // 2026-09-26).
  const openerRef = useRef(null);
  const wasOpen = useRef(false);
  if (open && !wasOpen.current && typeof document !== 'undefined') {
    openerRef.current = document.activeElement;
  }
  wasOpen.current = open;

  // Focus moves into the dialog on open -- unless a child already took it
  // (autoFocus), which the old unconditional panel.focus() stole back -- and
  // returns to the opener on close.
  useEffect(() => {
    if (!open) return undefined;
    const panel = panelRef.current;
    if (panel && !panel.contains(document.activeElement)) panel.focus();
    const opener = openerRef.current;
    return () => {
      if (opener && opener !== document.body && document.contains(opener)) opener.focus();
    };
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') {
        onClose?.();
        return;
      }
      // Keep Tab inside the dialog; the overlay hides the page behind it.
      if (e.key !== 'Tab' || !panelRef.current) return;
      const items = Array.from(panelRef.current.querySelectorAll(FOCUSABLE));
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && (document.activeElement === first || document.activeElement === panelRef.current)) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  // Bottom sheet on phones (thumb reach, room for the keyboard), centred
  // card from sm up.
  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center overscroll-contain bg-black/60 backdrop-blur-sm sm:items-center sm:p-4"
      onClick={onClose}
    >
      <div
        className="max-h-[85dvh] w-full max-w-lg overflow-y-auto overscroll-contain rounded-t-2xl border border-border bg-surface shadow-popover animate-reveal focus:outline-none sm:rounded-2xl"
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
