import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "../src/lib/api/errors";
import { chatSessionStore } from "../src/lib/api/chatSession";
import { tokenStore } from "../src/lib/api/token";

const api = vi.hoisted(() => ({
  guest: vi.fn(),
  sessions: vi.fn(),
  history: vi.fn(),
  sendMessage: vi.fn(),
}));

vi.mock("@/lib/api/services", () => ({
  authApi: { guest: api.guest },
  chatApi: {
    sessions: api.sessions,
    history: api.history,
    sendMessage: api.sendMessage,
  },
}));

import ChatBox from "../src/components/ChatBox";

beforeEach(() => {
  localStorage.clear();
  tokenStore.clear();
  chatSessionStore.clear();
  api.guest.mockReset();
  api.sessions.mockReset().mockResolvedValue({ items: [], total: 0 });
  api.history.mockReset().mockResolvedValue({ id: "conversation-1", messages: [] });
  api.sendMessage.mockReset();
});

afterEach(() => {
  cleanup();
  tokenStore.clear();
  chatSessionStore.clear();
});

it("restores the saved conversation from the backend", async () => {
  tokenStore.set("guest-token");
  chatSessionStore.set("conversation-1");
  api.history.mockResolvedValue({
    id: "conversation-1",
    messages: [
      { id: "message-1", role: "user", content: "Je préparais mon bac." },
      { id: "message-2", role: "assistant", content: "Vous préparez le bac." },
      { id: "message-3", role: "system", content: "Do not display this." },
    ],
  });

  render(<ChatBox />);

  expect(await screen.findByText("Je préparais mon bac.")).toBeTruthy();
  expect(screen.getByText("Vous préparez le bac.")).toBeTruthy();
  expect(screen.queryByText("Do not display this.")).toBeNull();
  expect(screen.getByRole("log", { name: "Historique de la conversation" })).toBeTruthy();
  expect(api.history).toHaveBeenCalledWith("conversation-1");
});

it("finds the active backend conversation when no local conversation id is saved", async () => {
  tokenStore.set("guest-token");
  api.sessions.mockResolvedValue({
    items: [{ id: "active-conversation", status: "active" }],
    total: 1,
  });
  api.history.mockResolvedValue({
    id: "active-conversation",
    messages: [{ id: "message-1", role: "user", content: "Conversation récupérée." }],
  });

  render(<ChatBox />);

  expect(await screen.findByText("Conversation récupérée.")).toBeTruthy();
  expect(api.sessions).toHaveBeenCalledTimes(1);
  expect(api.history).toHaveBeenCalledWith("active-conversation");
});

it("offers retry after a transient send failure without duplicating the user bubble", async () => {
  api.guest.mockResolvedValue({
    access_token: "guest-token",
    token_type: "bearer",
    role: "guest",
    session_id: "guest-1",
    expires_at: "2026-11-27T00:00:00Z",
  });
  api.sendMessage
    .mockRejectedValueOnce(new ApiError(0, "NETWORK_ERROR", "Server unavailable"))
    .mockResolvedValueOnce({
      session_id: "conversation-1",
      reply: "Je peux vous aider.",
      language: "fr",
      sources: [],
      profile_updates: {},
      next_action: "ask_question",
    });

  render(<ChatBox />);
  const input = screen.getByRole("textbox", { name: "Message" });
  const sendButton = screen.getByRole("button", { name: "Envoyer" });
  await waitFor(() => expect(input.hasAttribute("disabled")).toBe(false));
  fireEvent.change(input, { target: { value: "J'ai besoin d'aide." } });
  fireEvent.click(sendButton);

  fireEvent.click(await screen.findByRole("button", { name: "Réessayer" }));
  expect(await screen.findByText("Je peux vous aider.")).toBeTruthy();
  expect(screen.getAllByText("J'ai besoin d'aide.")).toHaveLength(1);
  expect(api.guest).toHaveBeenCalledTimes(1);
  expect(api.sendMessage).toHaveBeenCalledTimes(2);
});

it("explains the message cooldown without offering an immediate retry", async () => {
  api.guest.mockResolvedValue({
    access_token: "guest-token",
    token_type: "bearer",
    role: "guest",
    session_id: "guest-1",
    expires_at: "2026-11-27T00:00:00Z",
  });
  api.sendMessage.mockRejectedValue(
    new ApiError(
      429,
      "TOO_MANY_REQUESTS",
      "Débit de messages invité dépassé (limite : 10 messages par minute). Veuillez ralentir.",
    ),
  );

  render(<ChatBox />);

  const input = screen.getByRole("textbox", { name: "Message" });
  await waitFor(() => expect(input.hasAttribute("disabled")).toBe(false));
  fireEvent.change(input, { target: { value: "Bonjour" } });
  fireEvent.click(screen.getByRole("button", { name: "Envoyer" }));

  expect(await screen.findByText(
    "Débit de messages invité dépassé (limite : 10 messages par minute). Veuillez ralentir. (TOO_MANY_REQUESTS)",
  )).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Réessayer" })).toBeNull();
});

it("shows when the guest conversation quota requires account registration", async () => {
  api.guest.mockResolvedValue({
    access_token: "guest-token",
    token_type: "bearer",
    role: "guest",
    session_id: "guest-1",
    expires_at: "2026-11-27T00:00:00Z",
  });
  api.sendMessage.mockRejectedValue(
    new ApiError(
      429,
      "TOO_MANY_REQUESTS",
      "Quota de messages invité dépassé (limite : 100 messages). Veuillez créer un compte pour continuer.",
    ),
  );

  render(<ChatBox />);

  const input = screen.getByRole("textbox", { name: "Message" });
  await waitFor(() => expect(input.hasAttribute("disabled")).toBe(false));
  fireEvent.change(input, { target: { value: "Bonjour" } });
  fireEvent.click(screen.getByRole("button", { name: "Envoyer" }));

  expect(await screen.findByText(
    "Quota de messages invité dépassé (limite : 100 messages). Veuillez créer un compte pour continuer. (TOO_MANY_REQUESTS)",
  )).toBeTruthy();
});
