import { useEffect, useInsertionEffect, useRef } from 'react';

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Focus behaviour every modal surface shares (dialog, nav drawer, entities
 * drawer): remember the opener, move focus in unless a child already took it
 * (autoFocus), keep Tab inside, and return focus on close.
 *
 * The opener is read in an insertion effect: it runs before the layout phase
 * where a child's autoFocus is applied, and unlike a render-time ref write it
 * is safe under concurrent rendering (React review, 2026-09-26). Reading it
 * in a normal effect recorded the dialog's own field as the "opener".
 */
export default function useDialogFocus(open, panelRef) {
  const openerRef = useRef(null);

  useInsertionEffect(() => {
    if (open) openerRef.current = document.activeElement;
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    const panel = panelRef.current;
    if (panel && !panel.contains(document.activeElement)) panel.focus();
    const opener = openerRef.current;
    return () => {
      if (opener && opener !== document.body && document.contains(opener)) opener.focus();
    };
  }, [open, panelRef]);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      const panel = panelRef.current;
      if (e.key !== 'Tab' || !panel) return;
      const items = Array.from(panel.querySelectorAll(FOCUSABLE));
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (!panel.contains(active) || active === panel) {
        // Focus fell outside (a removed node, body after a re-render): pull it back in.
        e.preventDefault();
        (e.shiftKey ? last : first).focus();
      } else if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, panelRef]);
}
