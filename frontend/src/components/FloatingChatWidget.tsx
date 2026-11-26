"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import ChatBox from "./ChatBox";

const CHAT_ROUTE = "/chat";

export default function FloatingChatWidget() {
  const pathname = usePathname();
  const [isOpen, setIsOpen] = useState(false);
  const [hasOpened, setHasOpened] = useState(false);
  const launcher = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLElement>(null);
  const wasOpen = useRef(false);
  const isChatPage = pathname === CHAT_ROUTE || pathname.startsWith(`${CHAT_ROUTE}/`);

  useEffect(() => {
    setIsOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (isOpen) {
      panel.current?.querySelector<HTMLButtonElement>(".chat-close")?.focus();
    } else if (wasOpen.current && !isChatPage) {
      launcher.current?.focus();
    }
    wasOpen.current = isOpen;
  }, [isOpen, isChatPage]);

  useEffect(() => {
    if (!isOpen) return;

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setIsOpen(false);
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen]);

  if (isChatPage) return null;

  function toggleWidget() {
    if (!isOpen) setHasOpened(true);
    setIsOpen((open) => !open);
  }

  return (
    <>
      <section
        ref={panel}
        className="chat-widget-panel"
        id="smartcampus-chat-panel"
        aria-label="Assistant d’orientation"
        role="region"
        hidden={!isOpen}
      >
        {hasOpened && <ChatBox onClose={() => setIsOpen(false)} focusInput={isOpen} />}
      </section>
      <button
        ref={launcher}
        type="button"
        className="chat-widget-launcher"
        aria-label={isOpen ? "Fermer le chat d’orientation" : "Ouvrir le chat d’orientation"}
        aria-controls="smartcampus-chat-panel"
        aria-expanded={isOpen}
        onClick={toggleWidget}
      >
        {isOpen ? (
          <svg aria-hidden="true" viewBox="0 0 20 20" fill="none">
            <path d="m5 5 10 10M15 5 5 15" />
          </svg>
        ) : (
          <svg aria-hidden="true" viewBox="0 0 20 20" fill="none">
            <path d="M17 9.5a6.5 6.5 0 0 1-6.5 6.5H6l-3 1.7v-4.2A6.5 6.5 0 1 1 17 9.5Z" />
            <path d="M6.5 9.5h7M6.5 7h4" />
          </svg>
        )}
        <span>{isOpen ? "Fermer" : "Une question ?"}</span>
      </button>
    </>
  );
}
