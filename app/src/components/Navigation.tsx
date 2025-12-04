"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/", label: "Explore", icon: "search" },
  { href: "/experiment", label: "Classification", icon: "flask" },
];

export default function Navigation() {
  const pathname = usePathname();

  return (
    <nav className="bg-white dark:bg-zinc-900 border-b border-zinc-200 dark:border-zinc-800 mb-6">
      <div className="max-w-7xl mx-auto px-4">
        <div className="flex items-center justify-between h-14">
          <div className="flex items-center gap-2">
            <span className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
              Flora Explorer
            </span>
          </div>
          <div className="flex gap-1">
            {TABS.map((tab) => {
              const isActive = pathname === tab.href;
              return (
                <Link
                  key={tab.href}
                  href={tab.href}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2 ${
                    isActive
                      ? "bg-green-600 text-white"
                      : "text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800"
                  }`}
                >
                  {tab.icon === "search" && (
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                    </svg>
                  )}
                  {tab.icon === "flask" && (
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
                    </svg>
                  )}
                  {tab.label}
                </Link>
              );
            })}
          </div>
        </div>
      </div>
    </nav>
  );
}
