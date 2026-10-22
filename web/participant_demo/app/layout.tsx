import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "SocialFlux · 人工标注与 GT",
  description: "T1–3 独立作答、私有证据核验与 GT；T4 轨迹五维评分及 Claude 对照。",
  robots: {index: false, follow: false},
  icons: {icon: "/favicon.svg"},
};
export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
