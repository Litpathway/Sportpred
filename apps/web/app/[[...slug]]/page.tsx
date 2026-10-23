import { AppView } from "@/components/app-view";
export default async function Page({params}: {params: Promise<{slug?: string[]}>}) {
  const {slug = []} = await params;
  return <AppView path={`/${slug.join("/")}`}/>;
}
