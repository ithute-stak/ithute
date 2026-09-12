"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Shared popover state for menus that must remain open while the user interacts
 * with them. A menu closes only when the trigger is pressed again, the user
 * presses Escape, or a pointer event happens outside the trigger/panel root.
 *
 * Keeping the trigger and panel under the same root also prevents the common
 * click-through/focus race that made a few legacy menus appear and disappear
 * immediately on touchpads and mobile browsers.
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

    const onPointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (!rootRef.current?.contains(target)) close(false);
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      close(true);
    };

    document.addEventListener("pointerdown", onPointerDown, true);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown, true);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [close, open]);

  return { open, setOpen, toggle, close, rootRef, triggerRef };
}
