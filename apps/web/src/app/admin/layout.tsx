import { AdminShell } from "@/components/layout/shell";

export default function Layout({ children }: LayoutProps<"/admin">) {
  return <AdminShell>{children}</AdminShell>;
}
