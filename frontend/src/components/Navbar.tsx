"use client";
import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "Accueil" },
  { href: "/programs", label: "Formations" },
  { href: "/candidate", label: "Espace candidat" },
  { href: "/manager", label: "Espace responsable" },
  { href: "/chat", label: "Chat" },
];

export default function Navbar() {
  const [menuOpen, setMenuOpen] = useState(false);
  const pathname = usePathname();

  return (
    <header className="nav">
      <Link href="/" className="brand" aria-label="SmartCampus, accueil">
        <span className="brand-wordmark">Smart<span>Campus</span></span>
      </Link>
      <button
        className="nav-toggle"
        type="button"
        aria-expanded={menuOpen}
        aria-controls="main-navigation"
        aria-label={menuOpen ? "Fermer le menu" : "Ouvrir le menu"}
        onClick={() => setMenuOpen((open) => !open)}
      >
        <span className={`menu-icon${menuOpen ? " menu-icon-open" : ""}`} aria-hidden="true">
          <span />
          <span />
        </span>
        <span>{menuOpen ? "Fermer" : "Menu"}</span>
      </button>
      <nav id="main-navigation" aria-label="Navigation principale" className={menuOpen ? "nav-open" : ""}>
        {links.map((link) => {
          const current = pathname === link.href || (link.href !== "/" && pathname.startsWith(`${link.href}/`));
          const assistantLink = link.href === "/chat";
          return (
            <Link
              key={link.href}
              href={link.href}
              className={`nav-link${current ? " nav-link-active" : ""}${assistantLink ? " nav-link-assistant" : ""}`}
              aria-current={current ? "page" : undefined}
              onClick={() => setMenuOpen(false)}
            >
              {assistantLink && (
                <svg aria-hidden="true" viewBox="0 0 20 20" fill="none">
                  <path d="M17 9.5a6.5 6.5 0 0 1-6.5 6.5H6l-3 1.7v-4.2A6.5 6.5 0 1 1 17 9.5Z" />
                  <path d="M6.5 9.5h7M6.5 7h4" />
                </svg>
              )}
              {link.label}
              {assistantLink && <span className="assistant-link-arrow" aria-hidden="true">↗</span>}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
