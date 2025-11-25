"use client";

import { useQuery } from "@tanstack/react-query";
import { getTenders } from "@/lib/api";
import { ModernTenderCard } from "@/components/tenders/ModernTenderCard";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Calendar, MapPin, Users, AlertCircle } from "lucide-react";
import { useLanguage } from "@/contexts/LanguageContext";

export default function PTMPage() {
  const { t, language } = useLanguage();

  // Fetch all tenders and filter for those with meeting dates (backend max limit is 100)
  const { data: allTenders, isLoading, error } = useQuery({
    queryKey: ["all-tenders-for-ptm"],
    queryFn: () => getTenders({ limit: 100 }),
  });

  // Filter tenders that have pre-tender meetings (meeting_date OR meeting_location exists)
  const ptms = allTenders?.filter(t => t.meeting_date || t.meeting_location) || [];

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <Users className="h-8 w-8 text-purple-600" />
          <h1 className="text-4xl font-bold">
            {t("Pre-Tender Meetings", "اجتماعات ما قبل المناقصة")}
          </h1>
        </div>
        <p className="text-muted-foreground text-lg">
          {t(
            "Schedule and details of upcoming pre-tender meetings",
            "جدول وتفاصيل اجتماعات ما قبل المناقصة القادمة"
          )}
        </p>
      </div>

      {/* Stats Card */}
      <Card className="mb-8 bg-gradient-to-r from-purple-50 to-blue-50 border-purple-200">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Calendar className="h-5 w-5 text-purple-600" />
            {t("Meeting Statistics", "إحصائيات الاجتماعات")}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="text-center">
              <div className="text-3xl font-bold text-purple-600">
                {ptms?.length || 0}
              </div>
              <div className="text-sm text-muted-foreground">
                {t("Total Meetings", "إجمالي الاجتماعات")}
              </div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-blue-600">
                {ptms?.filter(p => p.meeting_date && new Date(p.meeting_date) > new Date()).length || 0}
              </div>
              <div className="text-sm text-muted-foreground">
                {t("Upcoming", "القادمة")}
              </div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-gray-600">
                {ptms?.filter(p => p.meeting_date && new Date(p.meeting_date) <= new Date()).length || 0}
              </div>
              <div className="text-sm text-muted-foreground">
                {t("Past", "السابقة")}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Loading State */}
      {isLoading && (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <Card key={i}>
              <CardContent className="p-6">
                <Skeleton className="h-6 w-3/4 mb-4" />
                <Skeleton className="h-4 w-1/2 mb-2" />
                <Skeleton className="h-4 w-2/3" />
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Error State */}
      {error && (
        <Card className="border-red-200 bg-red-50">
          <CardContent className="p-6">
            <div className="flex items-center gap-3 text-red-600">
              <AlertCircle className="h-6 w-6" />
              <div>
                <p className="font-semibold">
                  {t("Error loading meetings", "خطأ في تحميل الاجتماعات")}
                </p>
                <p className="text-sm">
                  {t("Please try again later", "يرجى المحاولة مرة أخرى لاحقاً")}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Empty State */}
      {!isLoading && !error && (!ptms || ptms.length === 0) && (
        <Card className="border-dashed">
          <CardContent className="p-12 text-center">
            <Users className="h-16 w-16 text-muted-foreground mx-auto mb-4" />
            <h3 className="text-xl font-semibold mb-2">
              {t("No Pre-Tender Meetings", "لا توجد اجتماعات ما قبل المناقصة")}
            </h3>
            <p className="text-muted-foreground">
              {t(
                "There are no scheduled pre-tender meetings at the moment",
                "لا توجد اجتماعات مجدولة في الوقت الحالي"
              )}
            </p>
          </CardContent>
        </Card>
      )}

      {/* PTM List */}
      {!isLoading && ptms && ptms.length > 0 && (
        <div className="space-y-4">
          {/* Upcoming Meetings */}
          {ptms.filter(p => p.meeting_date && new Date(p.meeting_date) > new Date()).length > 0 && (
            <div>
              <h2 className="text-2xl font-bold mb-4 flex items-center gap-2">
                <Calendar className="h-6 w-6 text-green-600" />
                {t("Upcoming Meetings", "الاجتماعات القادمة")}
              </h2>
              <div className="space-y-4">
                {ptms
                  .filter(p => p.meeting_date && new Date(p.meeting_date) > new Date())
                  .sort((a, b) => new Date(a.meeting_date!).getTime() - new Date(b.meeting_date!).getTime())
                  .map((ptm) => (
                    <ModernTenderCard key={ptm.id} tender={ptm} />
                  ))}
              </div>
            </div>
          )}

          {/* Past Meetings */}
          {ptms.filter(p => !p.meeting_date || new Date(p.meeting_date) <= new Date()).length > 0 && (
            <div className="mt-8">
              <h2 className="text-2xl font-bold mb-4 flex items-center gap-2 text-muted-foreground">
                <Calendar className="h-6 w-6" />
                {t("Past Meetings", "الاجتماعات السابقة")}
              </h2>
              <div className="space-y-4">
                {ptms
                  .filter(p => !p.meeting_date || new Date(p.meeting_date) <= new Date())
                  .sort((a, b) => {
                    if (!a.meeting_date) return 1;
                    if (!b.meeting_date) return -1;
                    return new Date(b.meeting_date).getTime() - new Date(a.meeting_date).getTime();
                  })
                  .map((ptm) => (
                    <div key={ptm.id} className="opacity-60">
                      <ModernTenderCard tender={ptm} />
                    </div>
                  ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
