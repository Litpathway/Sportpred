import { AppView } from "@/components/app-view";
import type { Metadata } from "next";

type RouteParams = {params: Promise<{slug?: string[]}>};
export async function generateMetadata({params}: RouteParams): Promise<Metadata> {
  const {slug = []} = await params;
  const path = `/${slug.join("/")}`;
  const titles: Record<string, string> = {
    "/": "Football predictions", "/matches": "Matches",
    "/predictions": "All predictions", "/predictions/high-confidence": "High-confidence predictions",
    "/booking-codes": "Verified codes & publications", "/performance": "Prediction performance",
    "/about": "Methodology", "/login": "Administrator sign-in",
  };
  const title = titles[path] || (path.startsWith("/admin") ? "Administration" : path.startsWith("/matches/") ? "Match analysis" : "Prediction publication");
  return {title, ...(path.startsWith("/admin") || path === "/login" ? {robots: {index:false,follow:false}} : {})};
}
export default async function Page({params}: {params: Promise<{slug?: string[]}>}) {
  const {slug = []} = await params;
  return <AppView path={`/${slug.join("/")}`}/>;
}
