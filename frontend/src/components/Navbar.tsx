import Link from "next/link";

const links = [
  { href: "/", label: "Accueil" },
  { href: "/programs", label: "Formations" },
  { href: "/chat", label: "Chat" },
  { href: "/candidate", label: "Espace candidat" },
  { href: "/manager", label: "Espace responsable" },
];

export default function Navbar() {
  return (
    <header className="nav">
      <Link href="/" className="brand">SmartCampus AI</Link>
      <nav>{links.map((l) => <Link key={l.href} href={l.href}>{l.label}</Link>)}</nav>
    </header>
  );
}
