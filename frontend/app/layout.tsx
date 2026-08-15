import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Aivatar — Creative Workspace",
  description: "Private AI video production workspace",
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "48x48" },
      { url: "/icon-aivatar.png", type: "image/png", sizes: "512x512" },
    ],
    apple: "/icon-aivatar.png",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
