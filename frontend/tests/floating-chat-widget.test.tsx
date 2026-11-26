import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import FloatingChatWidget from "../src/components/FloatingChatWidget";

const { mockPathname } = vi.hoisted(() => ({ mockPathname: vi.fn(() => "/") }));

vi.mock("next/navigation", () => ({
  usePathname: mockPathname,
}));

vi.mock("../src/components/ChatBox", () => ({
  default: ({ onClose, focusInput }: { onClose?: () => void; focusInput?: boolean }) => (
    <div data-testid="chat-widget-content" data-focus-input={String(focusInput)}>
      <button className="chat-close" type="button" aria-label="Fermer l’assistant" onClick={onClose}>Fermer</button>
    </div>
  ),
}));

afterEach(cleanup);

beforeEach(() => {
  mockPathname.mockReturnValue("/");
});

it("opens the chat widget and restores focus when it closes", () => {
  render(<FloatingChatWidget />);

  const launcher = screen.getByRole("button", { name: "Ouvrir le chat d’orientation" });
  fireEvent.click(launcher);

  const panel = document.getElementById("smartcampus-chat-panel");
  expect(panel?.hasAttribute("hidden")).toBe(false);
  expect(screen.getByTestId("chat-widget-content").getAttribute("data-focus-input")).toBe("true");
  expect(document.activeElement).toBe(screen.getByRole("button", { name: "Fermer l’assistant" }));

  fireEvent.keyDown(window, { key: "Escape" });

  expect(panel?.hasAttribute("hidden")).toBe(true);
  expect(document.activeElement).toBe(launcher);
});

it("does not show the floating widget on the dedicated chat page", () => {
  mockPathname.mockReturnValue("/chat");

  render(<FloatingChatWidget />);

  expect(screen.queryByRole("button", { name: "Ouvrir le chat d’orientation" })).toBeNull();
});
