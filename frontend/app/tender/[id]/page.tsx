"use client";

import { useQuery } from "@tanstack/react-query";
import { getTenderDetail } from "@/lib/api";
import { useState } from "react";
import Link from "next/link";
import { formatDate, formatDateArabic } from "@/lib/utils";

export default function TenderDetailPage({
  params,
}: {
  params: { id: string };
}) {
  const [lang, setLang] = useState<"ar" | "en">("ar");

  const { data: tender, isLoading } = useQuery({
    queryKey: ["tender", params.id],
    queryFn: () => getTenderDetail(parseInt(params.id)),
  });

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 flex items-center justify-center">
        <div className="text-slate-500">Loading...</div>
      </div>
    );
  }

  if (!tender) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 flex items-center justify-center">
        <div className="text-center">
          <h2 className="text-xl font-semibold text-slate-900 mb-2">
            Tender Not Found
          </h2>
          <Link href="/" className="text-blue-600 hover:underline">
            Back to Home
          </Link>
        </div>
      </div>
    );
  }

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
                  Tender Details
                </h1>
                <p className="text-xs text-slate-500">#{tender.id}</p>
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

      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Title Section */}
        <div className="bg-white rounded-lg p-8 mb-6 border border-slate-200">
          <h1 className="text-2xl font-bold text-slate-900 mb-4">
            {tender.title || "Untitled"}
          </h1>

          <div className="flex flex-wrap gap-2 mb-6">
            {tender.ministry && (
              <span className="px-3 py-1.5 bg-blue-50 text-blue-700 rounded text-sm font-medium">
                {tender.ministry}
              </span>
            )}
            {tender.category && (
              <span className="px-3 py-1.5 bg-purple-50 text-purple-700 rounded text-sm font-medium">
                {tender.category}
              </span>
            )}
            {tender.lang && (
              <span className="px-3 py-1.5 bg-slate-100 text-slate-700 rounded text-sm font-medium">
                {tender.lang === "ar" ? "Arabic" : "English"}
              </span>
            )}
          </div>

          {/* Key Info Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 py-4 border-t border-slate-200">
            {tender.published_at && (
              <div>
                <div className="text-sm text-slate-500 mb-1">
                  {lang === "ar" ? "تاريخ النشر" : "Published"}
                </div>
                <div className="text-base font-medium text-slate-900">
                  {lang === "ar"
                    ? formatDateArabic(tender.published_at)
                    : formatDate(tender.published_at)}
                </div>
              </div>
            )}
            {tender.deadline && (
              <div>
                <div className="text-sm text-slate-500 mb-1">
                  {lang === "ar" ? "الموعد النهائي" : "Deadline"}
                </div>
                <div className="text-base font-medium text-amber-600">
                  {lang === "ar"
                    ? formatDateArabic(tender.deadline)
                    : formatDate(tender.deadline)}
                </div>
              </div>
            )}
            {tender.tender_number && (
              <div>
                <div className="text-sm text-slate-500 mb-1">
                  {lang === "ar" ? "رقم العطاء" : "Tender Number"}
                </div>
                <div className="text-base font-medium text-slate-900">
                  {tender.tender_number}
                </div>
              </div>
            )}
            {tender.document_price_kd && (
              <div>
                <div className="text-sm text-slate-500 mb-1">
                  {lang === "ar" ? "سعر الوثائق" : "Document Price"}
                </div>
                <div className="text-base font-medium text-slate-900">
                  {tender.document_price_kd} KD
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Summary */}
        {(tender.summary_ar || tender.summary_en) && (
          <div className="bg-white rounded-lg p-6 mb-6 border border-slate-200">
            <h2 className="text-lg font-semibold text-slate-900 mb-3">
              {lang === "ar" ? "الملخص" : "Summary"}
            </h2>
            <p className="text-slate-700 leading-relaxed">
              {lang === "ar"
                ? tender.summary_ar || tender.summary_en
                : tender.summary_en || tender.summary_ar}
            </p>
          </div>
        )}

        {/* Key Facts */}
        {((lang === "ar" && tender.facts_ar) ||
          (lang === "en" && tender.facts_en)) && (
          <div className="bg-white rounded-lg p-6 mb-6 border border-slate-200">
            <h2 className="text-lg font-semibold text-slate-900 mb-3">
              {lang === "ar" ? "الحقائق الرئيسية" : "Key Facts"}
            </h2>
            <ul className="space-y-2">
              {(lang === "ar" ? tender.facts_ar : tender.facts_en)?.map(
                (fact, idx) => (
                  <li key={idx} className="flex items-start gap-2">
                    <span className="text-slate-400 mt-1">•</span>
                    <span className="text-slate-700">{fact}</span>
                  </li>
                )
              )}
            </ul>
          </div>
        )}

        {/* Full Body */}
        {tender.body && (
          <div className="bg-white rounded-lg p-6 mb-6 border border-slate-200">
            <h2 className="text-lg font-semibold text-slate-900 mb-3">
              {lang === "ar" ? "التفاصيل الكاملة" : "Full Details"}
            </h2>
            <div className="prose prose-sm max-w-none text-slate-700 whitespace-pre-wrap">
              {tender.body}
            </div>
          </div>
        )}

        {/* Attachments */}
        {tender.attachments && (
          <div className="bg-white rounded-lg p-6 mb-6 border border-slate-200">
            <h2 className="text-lg font-semibold text-slate-900 mb-3">
              {lang === "ar" ? "المرفقات" : "Attachments"}
            </h2>
            <div className="space-y-2">
              {Array.isArray(tender.attachments) ? (
                tender.attachments.map((attachment: any, idx: number) => (
                  <a
                    key={idx}
                    href={attachment.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block px-4 py-3 border border-slate-200 rounded-md hover:border-slate-300 hover:bg-slate-50 transition-colors"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-slate-900">
                        {attachment.name || "Document"}
                      </span>
                      <span className="text-xs text-slate-500">
                        {lang === "ar" ? "تحميل ↓" : "Download ↓"}
                      </span>
                    </div>
                  </a>
                ))
              ) : (
                <p className="text-sm text-slate-500">
                  {lang === "ar"
                    ? "لا توجد مرفقات"
                    : "No attachments available"}
                </p>
              )}
            </div>
          </div>
        )}

        {/* Source Link */}
        <div className="bg-white rounded-lg p-6 border border-slate-200">
          <a
            href={tender.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-4 py-2 bg-slate-900 text-white rounded-md hover:bg-slate-800 transition-colors text-sm font-medium"
          >
            {lang === "ar" ? "عرض المصدر الأصلي ↗" : "View Original Source ↗"}
          </a>
        </div>
      </main>
    </div>
  );
}
