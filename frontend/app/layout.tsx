import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "unMeet — find buyers asking for you", template: "%s · unMeet" },
  description:
    "unMeet reads public conversations and sends you the ones where someone is asking for a tool like yours or complaining about a competitor.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
