"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Button } from "@/components/ui/button";
import { MessageSquare, FileText, Search, Languages } from "lucide-react";
import { useLanguage } from "@/contexts/LanguageContext";

export function Header() {
  const pathname = usePathname();
  const { language, setLanguage, t } = useLanguage();

  const navItems = [
    { href: "/", label: t("Tenders", "المناقصات"), icon: FileText },
    { href: "/search", label: t("Search", "البحث"), icon: Search },
    { href: "/chat", label: t("AI Assistant", "المساعد الذكي"), icon: MessageSquare },
  ];

  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container flex h-16 items-center justify-between">
        {/* Logo */}
        <Link href="/" className="flex items-center space-x-3 space-x-reverse">
          <Image
            src="/stc-logo.png"
            alt="STC Logo"
            width={120}
            height={40}
            className="h-10 w-auto"
            priority
          />
        </Link>

        {/* Navigation */}
        <nav className="hidden md:flex items-center gap-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href;
            
            return (
              <Link key={item.href} href={item.href}>
                <Button
                  variant={isActive ? "default" : "ghost"}
                  className="gap-2"
                >
                  <Icon className="h-4 w-4" />
                  <span>{item.label}</span>
                </Button>
              </Link>
            );
          })}
        </nav>

        {/* Language Toggle */}
        <Button
          variant="outline"
          size="sm"
          onClick={() => setLanguage(language === "en" ? "ar" : "en")}
          className="gap-2"
        >
          <Languages className="h-4 w-4" />
          <span>{language === "en" ? "العربية" : "English"}</span>
        </Button>
      </div>
    </header>
  );
}
