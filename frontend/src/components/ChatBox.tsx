"use client";
// Coquille du chat : affichage des messages, saisie, bouton micro. La logique des agents est côté backend (Membre 5).
import { useRef, useState } from "react";
import { chatApi } from "@/lib/api/services";
import { ApiError } from "@/lib/api/errors";

interface Msg { role: "user" | "assistant" | "error"; text: string }

export default function ChatBox() {
  const [messages, setMessages] = useState<Msg[]>([
    { role: "assistant", text: "Bonjour ! Posez-moi vos questions sur les formations de l'IIT et de l'ISB (français, tunisien ou Arabizi)." },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const sessionId = useRef<string | undefined>(undefined);

  async function send() {
    const text = input.trim();
    if (!text || sending) return;
    setInput(""); setSending(true);
    setMessages((m) => [...m, { role: "user", text }]);
    try {
      const res = await chatApi.sendMessage({ session_id: sessionId.current, message: text });
      sessionId.current = res.session_id;
      setMessages((m) => [...m, { role: "assistant", text: res.reply }]);
    } catch (e) {
      const msg = e instanceof ApiError ? `${e.userMessage} (${e.code})` : "Erreur inconnue.";
      setMessages((m) => [...m, { role: "error", text: msg }]);
    } finally { setSending(false); }
  }

  return (
    <div className="chat">
      <div className="chat-messages">
        {messages.map((m, i) => <div key={i} className={`bubble bubble-${m.role}`}>{m.text}</div>)}
        {sending && <div className="bubble bubble-assistant muted">…</div>}
      </div>
      <div className="chat-input">
        <button className="btn btn-light" disabled title="Message vocal : bientôt disponible" aria-label="Micro">🎤</button>
        <input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()}
               placeholder="Écrivez votre message…" aria-label="Message" />
        <button className="btn" onClick={send} disabled={sending || !input.trim()}>Envoyer</button>
      </div>
    </div>
  );
}
