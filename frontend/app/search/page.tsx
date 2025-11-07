"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { searchHybrid } from "@/lib/api";
import Link from "next/link";
import { formatDate, formatDateArabic } from "@/lib/utils";

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [lang, setLang] = useState<"ar" | "en">("ar");

  const { data: results, isLoading } = useQuery({
    queryKey: ["search", searchTerm],
    queryFn: () => searchHybrid(searchTerm, 30),
    enabled: searchTerm.length > 2,
  });

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim().length > 2) {
      setSearchTerm(query.trim());
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100">
      {/* Header */}
      <header className="border-b bg-white/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <Link href="/" className="flex items-center gap-2">
              <span className="text-xl font-bold text-slate-900">←</span>
              <div>
                <h1 className="text-lg font-semibold text-slate-900">
                  Search Tenders
                </h1>
                <p className="text-xs text-slate-500">
                  Keyword & Semantic Search
                </p>
              </div>
            </Link>

            <button
              onClick={() => setLang(lang === "ar" ? "en" : "ar")}
              className="px-3 py-1.5 text-sm font-medium rounded-md bg-slate-100 hover:bg-slate-200 transition-colors"
            >
              {lang === "ar" ? "English" : "العربية"}
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Search Form */}
        <div className="mb-8">
          <form onSubmit={handleSearch}>
            <div className="relative">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={
                  lang === "ar"
                    ? "ابحث عن عطاءات..."
                    : "Search for tenders..."
                }
                className="w-full px-6 py-4 text-lg border-2 border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-transparent bg-white"
              />
              <button
                type="submit"
                disabled={query.trim().length < 3}
                className="absolute right-3 top-1/2 -translate-y-1/2 px-6 py-2 bg-slate-900 text-white rounded-md hover:bg-slate-800 disabled:bg-slate-300 disabled:cursor-not-allowed transition-colors font-medium"
              >
                {lang === "ar" ? "بحث" : "Search"}
              </button>
            </div>
          </form>

          {/* Search Tips */}
          <div className="mt-4 flex flex-wrap gap-2">
            <span className="text-sm text-slate-600">
              {lang === "ar" ? "جرّب:" : "Try:"}
            </span>
            {[
              { ar: "تقنية المعلومات", en: "IT technology" },
              { ar: "وزارة الصحة", en: "Ministry of Health" },
              { ar: "البنية التحتية", en: "infrastructure" },
            ].map((term, idx) => (
              <button
                key={idx}
                onClick={() => {
                  setQuery(lang === "ar" ? term.ar : term.en);
                  setSearchTerm(lang === "ar" ? term.ar : term.en);
                }}
                className="px-3 py-1 text-sm bg-white border border-slate-200 rounded-md hover:border-slate-300 hover:bg-slate-50 transition-colors"
              >
                {lang === "ar" ? term.ar : term.en}
              </button>
            ))}
          </div>
        </div>

        {/* Results */}
        {searchTerm && (
          <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
            <div className="border-b border-slate-200 px-6 py-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-slate-900">
                  {lang === "ar" ? "نتائج البحث" : "Search Results"}
                </h2>
                {results && (
                  <span className="text-sm text-slate-500">
                    {results.length}{" "}
                    {lang === "ar" ? "نتيجة" : "results"}
                  </span>
                )}
              </div>
            </div>

            {isLoading ? (
              <div className="p-8 text-center text-slate-500">
                {lang === "ar" ? "جاري البحث..." : "Searching..."}
              </div>
            ) : results && results.length > 0 ? (
              <div className="divide-y divide-slate-200">
                {results.map((tender) => (
                  <Link
                    key={tender.id}
                    href={`/tender/${tender.id}`}
                    className="block p-6 hover:bg-slate-50 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-2">
                          <h3 className="text-base font-medium text-slate-900">
                            {lang === "ar"
                              ? tender.title || "Untitled"
                              : tender.title || "Untitled"}
                          </h3>
                          {tender.score && (
                            <span className="px-2 py-0.5 text-xs bg-emerald-50 text-emerald-700 rounded font-medium">
                              {Math.round(tender.score * 100)}% match
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-slate-600 line-clamp-2 mb-3">
                          {lang === "ar"
                            ? tender.summary_ar || tender.summary_en
                            : tender.summary_en || tender.summary_ar}
                        </p>
                        <div className="flex flex-wrap gap-2 text-xs">
                          {tender.ministry && (
                            <span className="px-2 py-1 bg-blue-50 text-blue-700 rounded">
                              {tender.ministry}
                            </span>
                          )}
                          {tender.category && (
                            <span className="px-2 py-1 bg-purple-50 text-purple-700 rounded">
                              {tender.category}
                            </span>
                          )}
                          {tender.deadline && (
                            <span className="px-2 py-1 bg-amber-50 text-amber-700 rounded">
                              Deadline:{" "}
                              {lang === "ar"
                                ? formatDateArabic(tender.deadline)
                                : formatDate(tender.deadline)}
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="text-right flex-shrink-0">
                        <div className="text-sm text-slate-500">
                          {lang === "ar"
                            ? formatDateArabic(tender.published_at)
                            : formatDate(tender.published_at)}
                        </div>
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            ) : searchTerm ? (
              <div className="p-8 text-center text-slate-500">
                {lang === "ar"
                  ? "لم يتم العثور على نتائج"
                  : "No results found"}
              </div>
            ) : null}
          </div>
        )}

        {/* Empty State */}
        {!searchTerm && (
          <div className="bg-white rounded-lg p-12 text-center border border-slate-200">
            <div className="max-w-md mx-auto">
              <div className="text-lg font-medium text-slate-900 mb-2">
                {lang === "ar"
                  ? "ابحث عن العطاءات الحكومية"
                  : "Search Government Tenders"}
              </div>
              <p className="text-sm text-slate-500">
                {lang === "ar"
                  ? "استخدم الكلمات المفتاحية أو البحث الدلالي للعثور على العطاءات ذات الصلة"
                  : "Use keywords or semantic search to find relevant tenders"}
              </p>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
