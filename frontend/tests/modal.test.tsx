import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, expect, it } from "vitest";
import Modal from "../src/components/ui/Modal";

function ModalHarness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>Ouvrir la fenêtre</button>
      {open && (
        <Modal title="Dialogue de test" onClose={() => setOpen(false)}>
          <button>Premier élément</button>
          <button>Dernier élément</button>
        </Modal>
      )}
    </>
  );
}

afterEach(cleanup);

it("traps keyboard focus and restores it when closed with Escape", async () => {
  render(<ModalHarness />);
  const opener = screen.getByRole("button", { name: "Ouvrir la fenêtre" });
  opener.focus();
  fireEvent.click(opener);

  const dialog = await screen.findByRole("dialog", { name: "Dialogue de test" });
  const closeButton = screen.getByRole("button", { name: "Fermer" });
  const lastButton = screen.getByRole("button", { name: "Dernier élément" });
  expect(document.activeElement).toBe(closeButton);

  fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
  expect(document.activeElement).toBe(lastButton);
  fireEvent.keyDown(document, { key: "Tab" });
  expect(document.activeElement).toBe(closeButton);
  fireEvent.keyDown(document, { key: "Escape" });

  expect(await screen.findByRole("button", { name: "Ouvrir la fenêtre" })).toBe(opener);
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(document.body.style.overflow).toBe("");
  expect(dialog.isConnected).toBe(false);
});
