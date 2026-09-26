import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { TooltipProvider } from "@/components/ui/tooltip";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Auto Browser Live",
  description: "Watch what an agent does in the browser, in real time.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <TooltipProvider delayDuration={200}>
          <header className="border-b">
            <div className="mx-auto flex h-11 max-w-[1600px] items-center gap-3 px-4">
              <Link href="/" className="font-medium tracking-tight">Auto Browser</Link>
              <span className="text-muted-foreground">live view</span>
            </div>
          </header>
          <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-4">{children}</main>
        </TooltipProvider>
      </body>
    </html>
  );
}
