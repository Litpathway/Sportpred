import type { Metadata } from "next";
import { Providers } from "@/components/providers";
import { Shell } from "@/components/shell";
import "./globals.css";

export const metadata: Metadata = { title: { default: "SportPredict AI — Football intelligence", template: "%s | SportPredict AI" }, description: "Transparent football predictions, calibrated probabilities and auditable match analysis." };
export default function RootLayout({children}: {children: React.ReactNode}) {
  return <html lang="en"><body><Providers><Shell>{children}</Shell></Providers></body></html>;
}
