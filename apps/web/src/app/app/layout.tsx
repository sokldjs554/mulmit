import { AppShell } from "@/components/layout/shell";

export default function Layout({ children }: LayoutProps<"/app">) {
  return <AppShell>{children}</AppShell>;
}
