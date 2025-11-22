"use client";

import { useQuery } from "@tanstack/react-query";
import { getTenders } from "@/lib/api";
import { ModernTenderCard } from "@/components/tenders/ModernTenderCard";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Bell, AlertTriangle, Clock, TrendingUp, Calendar } from "lucide-react";
import { useLanguage } from "@/contexts/LanguageContext";
import { formatDate } from "@/lib/utils";

export default function NotificationsPage() {
  const { t, language } = useLanguage();

  // Fetch all tenders (backend max limit is 100)
  const { data: tenders, isLoading, error } = useQuery({
    queryKey: ["all-tenders-notifications"],
    queryFn: () => getTenders({ limit: 100 }),
  });

  // Filter postponed tenders
  const postponedTenders = tenders?.filter(t => t.is_postponed) || [];
  
  // Filter recent tenders (last 7 days)
  const sevenDaysAgo = new Date();
  sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);
  const recentTenders = tenders?.filter(t => 
    t.published_at && new Date(t.published_at) > sevenDaysAgo
  ).sort((a, b) => 
    new Date(b.published_at!).getTime() - new Date(a.published_at!).getTime()
  ) || [];

  // Filter upcoming deadlines (next 14 days)
  const now = new Date();
  const fourteenDaysLater = new Date();
  fourteenDaysLater.setDate(now.getDate() + 14);
  const upcomingDeadlines = tenders?.filter(t => 
    t.deadline && 
    new Date(t.deadline) > now && 
    new Date(t.deadline) < fourteenDaysLater
  ).sort((a, b) => 
    new Date(a.deadline!).getTime() - new Date(b.deadline!).getTime()
  ) || [];

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <Bell className="h-8 w-8 text-blue-600" />
          <h1 className="text-4xl font-bold">
            {t("Notifications & Updates", "الإشعارات والتحديثات")}
          </h1>
        </div>
        <p className="text-muted-foreground text-lg">
          {t(
            "Stay updated with postponements, new tenders, and upcoming deadlines",
            "ابق على اطلاع بالتأجيلات والمناقصات الجديدة والمواعيد القادمة"
          )}
        </p>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        <Card className="border-red-200 bg-red-50">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-red-600" />
              {t("Postponed", "مؤجلة")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-red-600">
              {postponedTenders.length}
            </div>
          </CardContent>
        </Card>

        <Card className="border-green-200 bg-green-50">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-green-600" />
              {t("New (7 days)", "جديدة (7 أيام)")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-green-600">
              {recentTenders.length}
            </div>
          </CardContent>
        </Card>

        <Card className="border-orange-200 bg-orange-50">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Clock className="h-4 w-4 text-orange-600" />
              {t("Deadlines (14 days)", "مواعيد (14 يوم)")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-orange-600">
              {upcomingDeadlines.length}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Loading State */}
      {isLoading && (
        <div className="space-y-6">
          {[1, 2, 3].map((i) => (
            <div key={i}>
              <Skeleton className="h-8 w-48 mb-4" />
              <Skeleton className="h-32 w-full" />
            </div>
          ))}
        </div>
      )}

      {/* Error State */}
      {error && (
        <Card className="border-red-200 bg-red-50">
          <CardContent className="p-6 text-center text-red-600">
            {t("Error loading notifications", "خطأ في تحميل الإشعارات")}
          </CardContent>
        </Card>
      )}

      {/* Content */}
      {!isLoading && !error && (
        <div className="space-y-8">
          {/* Postponed Tenders */}
          {postponedTenders.length > 0 && (
            <div>
              <div className="flex items-center gap-3 mb-4">
                <AlertTriangle className="h-6 w-6 text-red-600" />
                <h2 className="text-2xl font-bold">
                  {t("Postponed Tenders", "المناقصات المؤجلة")}
                </h2>
                <Badge variant="destructive">{postponedTenders.length}</Badge>
              </div>
              <div className="space-y-4">
                {postponedTenders.map((tender) => (
                  <div key={tender.id}>
                    <ModernTenderCard tender={tender} />
                    {tender.postponement_reason && (
                      <Card className="mt-2 border-red-200 bg-red-50">
                        <CardContent className="p-3 text-sm">
                          <span className="font-semibold">
                            {t("Reason:", "السبب:")}
                          </span>{" "}
                          {tender.postponement_reason}
                        </CardContent>
                      </Card>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Upcoming Deadlines */}
          {upcomingDeadlines.length > 0 && (
            <div>
              <div className="flex items-center gap-3 mb-4">
                <Clock className="h-6 w-6 text-orange-600" />
                <h2 className="text-2xl font-bold">
                  {t("Upcoming Deadlines (Next 14 Days)", "المواعيد القادمة (14 يوماً)")}
                </h2>
                <Badge variant="secondary" className="bg-orange-100 text-orange-800">
                  {upcomingDeadlines.length}
                </Badge>
              </div>
              <div className="space-y-4">
                {upcomingDeadlines.map((tender) => (
                  <div key={tender.id} className="relative">
                    <ModernTenderCard tender={tender} />
                    {tender.deadline && (
                      <div className="absolute top-4 right-4">
                        <Badge variant="outline" className="border-orange-600 text-orange-600">
                          <Calendar className="h-3 w-3 mr-1" />
                          {formatDate(tender.deadline)}
                        </Badge>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Recent Tenders */}
          {recentTenders.length > 0 && (
            <div>
              <div className="flex items-center gap-3 mb-4">
                <TrendingUp className="h-6 w-6 text-green-600" />
                <h2 className="text-2xl font-bold">
                  {t("Recent Tenders (Last 7 Days)", "المناقصات الأخيرة (آخر 7 أيام)")}
                </h2>
                <Badge variant="secondary" className="bg-green-100 text-green-800">
                  {recentTenders.length}
                </Badge>
              </div>
              <div className="space-y-4">
                {recentTenders.map((tender) => (
                  <ModernTenderCard key={tender.id} tender={tender} />
                ))}
              </div>
            </div>
          )}

          {/* Empty State */}
          {postponedTenders.length === 0 && 
           recentTenders.length === 0 && 
           upcomingDeadlines.length === 0 && (
            <Card className="border-dashed">
              <CardContent className="p-12 text-center">
                <Bell className="h-16 w-16 text-muted-foreground mx-auto mb-4" />
                <h3 className="text-xl font-semibold mb-2">
                  {t("No Notifications", "لا توجد إشعارات")}
                </h3>
                <p className="text-muted-foreground">
                  {t(
                    "There are no recent updates or notifications at the moment",
                    "لا توجد تحديثات أو إشعارات حديثة في الوقت الحالي"
                  )}
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
