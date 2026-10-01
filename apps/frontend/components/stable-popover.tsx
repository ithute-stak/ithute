"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Shared popover state for menus that must remain open while the user interacts
 * with them. A menu closes only when the trigger is pressed again, the user
 * presses Escape, or a click happens outside the trigger/panel root.
 *
 * Important: outside dismissal is handled on the native `click` event rather
 * than capture-phase `pointerdown`. Closing a popover during pointerdown can
 * cause React to re-render the surrounding shell before the browser delivers
 * the target's click, which makes unrelated buttons/links appear to require a
 * second click. Waiting for click lets the intended control run first and then
 * dismisses the open popover.
 */
export function useStablePopover(initialOpen = false) {
  const [open, setOpen] = useState(initialOpen);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  const close = useCallback((restoreFocus = false) => {
    setOpen(false);
    if (restoreFocus) {
      window.requestAnimationFrame(() => triggerRef.current?.focus());
    }
  }, []);

  const toggle = useCallback(() => {
    setOpen((value) => !value);
  }, []);

  useEffect(() => {
    if (!open) return;

    const onClick = (event: MouseEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (!rootRef.current?.contains(target)) close(false);
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      close(true);
    };

    document.addEventListener("click", onClick);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("click", onClick);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [close, open]);

  return { open, setOpen, toggle, close, rootRef, triggerRef };
}
