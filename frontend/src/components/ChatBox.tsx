"use client";
import { useEffect, useRef, useState } from "react";
import { authApi, chatApi } from "@/lib/api/services";
import { ApiError } from "@/lib/api/errors";
import { chatSessionStore } from "@/lib/api/chatSession";
import { tokenStore } from "@/lib/api/token";

type MessageRole = "user" | "assistant" | "error";
interface Msg {
  id: string;
  role: MessageRole;
  text: string;
  retryMessage?: string;
  retryHistory?: boolean;
}

const WELCOME_MESSAGE =
  "Bonjour ! Posez-moi vos questions sur les formations de l'IIT et de l'ISB (français, tunisien ou Arabizi).";

function isRetryable(error: unknown): boolean {
  return !(error instanceof ApiError) || error.status === 0 || error.status === 408
    || error.status === 429 || error.status >= 500;
}

export default function ChatBox({
  onClose,
  focusInput = false,
}: {
  onClose?: () => void;
  focusInput?: boolean;
} = {}) {
  const [messages, setMessages] = useState<Msg[]>([
    { id: "welcome", role: "assistant", text: WELCOME_MESSAGE },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [restoring, setRestoring] = useState(true);
  const sessionId = useRef<string | undefined>(undefined);
  const messageEnd = useRef<HTMLDivElement>(null);
  const inputElement = useRef<HTMLInputElement>(null);
  const messageCounter = useRef(0);
  const restoreAttempt = useRef(0);

  function createMessage(role: MessageRole, text: string, extra: Partial<Msg> = {}): Msg {
    messageCounter.current += 1;
    return { id: `message-${messageCounter.current}`, role, text, ...extra };
  }

  async function restoreHistory() {
    const attempt = ++restoreAttempt.current;
    setRestoring(true);
    setMessages((current) => current.filter((message) => !message.retryHistory));

    try {
      if (!tokenStore.get()) {
        chatSessionStore.clear();
        sessionId.current = undefined;
        return;
      }

      let id = chatSessionStore.get();
      if (!id) {
        const sessions = await chatApi.sessions();
        id = sessions.items.find((session) => session.status === "active")?.id ?? null;
      }
      if (attempt !== restoreAttempt.current) return;
      if (!id) return;

      const history = await chatApi.history(id);
      if (attempt !== restoreAttempt.current) return;

      sessionId.current = history.id;
      chatSessionStore.set(history.id);
      const restored = history.messages.flatMap((message): Msg[] =>
        message.role === "system"
          ? []
          : [{ id: message.id, role: message.role, text: message.content }],
      );
      setMessages(restored.length ? restored : [{ id: "welcome", role: "assistant", text: WELCOME_MESSAGE }]);
    } catch (error) {
      if (attempt !== restoreAttempt.current) return;
      if (error instanceof ApiError && [401, 403, 404].includes(error.status)) {
        chatSessionStore.clear();
        sessionId.current = undefined;
      }
      const detail = error instanceof ApiError
        ? `${error.userMessage} (${error.code})`
        : "Erreur inconnue.";
      const errorMessage = createMessage("error", `Impossible de restaurer la conversation. ${detail}`, {
        retryHistory: isRetryable(error),
      });
      setMessages((current) => [...current, errorMessage]);
    } finally {
      if (attempt === restoreAttempt.current) setRestoring(false);
    }
  }

  useEffect(() => {
    void restoreHistory();
    return () => { restoreAttempt.current += 1; };
  }, []);

  useEffect(() => {
    const reduceMotion = typeof window.matchMedia === "function"
      && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const behavior = reduceMotion ? "auto" : "smooth";
    messageEnd.current?.scrollIntoView?.({ behavior, block: "end" });
  }, [messages, sending, restoring]);

  useEffect(() => {
    if (focusInput && !restoring && document.activeElement?.classList.contains("chat-close")) {
      inputElement.current?.focus();
    }
  }, [focusInput, restoring]);

  async function send(text = input.trim(), appendUserMessage = true) {
    if (!text || sending || restoring) return;
    setInput("");
    setSending(true);
    if (appendUserMessage) {
      const userMessage = createMessage("user", text);
      setMessages((current) => [...current, userMessage]);
    }

    try {
      if (!tokenStore.get()) {
        const guest = await authApi.guest();
        tokenStore.set(guest.access_token);
        chatSessionStore.clear();
        sessionId.current = undefined;
      }
      const response = await chatApi.sendMessage({ session_id: sessionId.current, message: text });
      sessionId.current = response.session_id;
      chatSessionStore.set(response.session_id);
      const assistantMessage = createMessage("assistant", response.reply);
      setMessages((current) => [...current, assistantMessage]);
    } catch (error) {
      const detail = error instanceof ApiError
        ? `${error.userMessage} (${error.code})`
        : "Erreur inconnue.";
      const errorMessage = createMessage("error", detail, {
        retryMessage: isRetryable(error) ? text : undefined,
      });
      setMessages((current) => [...current, errorMessage]);
    } finally {
      setSending(false);
    }
  }

  function retryMessage(message: Msg) {
    if (!message.retryMessage) return;
    setMessages((current) => current.filter((item) => item.id !== message.id));
    void send(message.retryMessage, false);
  }

  return (
    <div className="chat">
      <div className="chat-topbar">
        <div className="chat-topbar-copy">
          <strong>Assistant d&apos;orientation</strong>
          <span>Formations de l&apos;IIT et de l&apos;ISB</span>
        </div>
        <span className="chat-topbar-label">SmartCampus</span>
        {onClose && (
          <button className="chat-close" type="button" aria-label="Fermer l’assistant" onClick={onClose}>
            <svg aria-hidden="true" viewBox="0 0 20 20" fill="none">
              <path d="m5 5 10 10M15 5 5 15" />
            </svg>
          </button>
        )}
      </div>
      <div
        className="chat-messages"
        role="log"
        aria-label="Historique de la conversation"
        aria-live="polite"
        aria-relevant="additions text"
      >
        {messages.map((message) => (
          <div className={`bubble bubble-${message.role}`} key={message.id} role={message.role === "error" ? "alert" : undefined}>
            <div>{message.text}</div>
            {message.retryMessage && (
              <button className="btn btn-light btn-sm retry-button" onClick={() => retryMessage(message)}>
                Réessayer
              </button>
            )}
            {message.retryHistory && (
              <button className="btn btn-light btn-sm retry-button" onClick={() => void restoreHistory()}>
                Réessayer
              </button>
            )}
          </div>
        ))}
        {restoring && <div className="chat-status" role="status">Restauration de la conversation…</div>}
        {sending && <div className="chat-status" role="status">L&apos;assistant prépare une réponse…</div>}
        <div ref={messageEnd} />
      </div>
      <div className="chat-input">
        <span className="voice-status" title="La saisie vocale sera disponible prochainement">
          <span aria-hidden="true">🎤</span>
          <span>Vocal bientôt</span>
        </span>
        <input
          ref={inputElement}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => event.key === "Enter" && void send()}
          placeholder="Écrivez votre message…"
          aria-label="Message"
          disabled={sending || restoring}
        />
        <button className="btn" onClick={() => void send()} disabled={sending || restoring || !input.trim()}>
          Envoyer
        </button>
      </div>
    </div>
  );
}
