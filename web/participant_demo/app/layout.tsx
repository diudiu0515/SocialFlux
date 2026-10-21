import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "SocialFlux · 对话理解标注",
  description: "阅读一段对话，独立记录你的判断。SocialFlux 受邀标注者体验。",
  robots: {index: false, follow: false},
  icons: {icon: "/favicon.svg"},
};
export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
