import type { Metadata } from "next";
import { Providers } from "@/components/providers";
import { Shell } from "@/components/shell";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || (process.env.VERCEL_PROJECT_PRODUCTION_URL ? `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}` : "http://localhost:3000")),
  title: { default: "SportPredict — Football predictions", template: "%s | SportPredict" },
  description: "Football fixtures, model probabilities, team form and prediction results.",
  openGraph: { type: "website", siteName: "SportPredict", title: "Football predictions", description: "Football fixtures, model probabilities, team form and prediction results." },
  twitter: { card: "summary_large_image", title: "SportPredict — Football predictions", description: "Match probabilities, team form and recorded results." },
};
export default function RootLayout({children}: {children: React.ReactNode}) {
  return <html lang="en"><body><Providers><Shell>{children}</Shell></Providers></body></html>;
}
