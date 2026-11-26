import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import Navbar from "../src/components/Navbar";

vi.mock("next/navigation", () => ({
  usePathname: () => "/programs/engineering",
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    onClick,
    ...props
  }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a
      href={href}
      onClick={(event) => {
        event.preventDefault();
        onClick?.(event);
      }}
      {...props}
    >
      {children}
    </a>
  ),
}));

afterEach(cleanup);

it("exposes a controllable mobile navigation menu", () => {
  render(<Navbar />);

  const toggle = screen.getByRole("button", { name: "Ouvrir le menu" });
  expect(toggle.getAttribute("aria-expanded")).toBe("false");
  expect(screen.getByRole("link", { name: "Formations" }).getAttribute("aria-current")).toBe("page");
  fireEvent.click(toggle);
  expect(toggle.getAttribute("aria-expanded")).toBe("true");
  expect(screen.getByRole("navigation", { name: "Navigation principale" })).toBeTruthy();

  fireEvent.click(screen.getByRole("link", { name: "Formations" }));
  expect(toggle.getAttribute("aria-expanded")).toBe("false");
});
