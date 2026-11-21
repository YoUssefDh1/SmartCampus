import type { Metadata } from "next";
import Navbar from "@/components/Navbar";
import "./globals.css";

export const metadata: Metadata = {
  title: "SmartCampus AI",
  description: "Plateforme agentique d'orientation universitaire (IIT / ISB)",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body>
        <Navbar />
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
