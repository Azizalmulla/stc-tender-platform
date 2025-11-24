"use client";

import { useQuery } from "@tanstack/react-query";
import { getNotifications } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Bell, AlertTriangle, Clock, TrendingUp } from "lucide-react";
import { useLanguage } from "@/contexts/LanguageContext";
import { NotificationCard } from "@/components/notifications/NotificationCard";

export default function NotificationsPage() {

  const { t, language } = useLanguage();

  const { data, isLoading, error } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => getNotifications({ limit: 50, enrich_with_ai: false }),  // Disabled AI - too slow for 50 items
    staleTime: 5 * 60 * 1000,  // Cache for 5 minutes
  });

  const notifications = data?.items || [];
  const postponedCount = data?.postponed ?? 0;
  const newCount = data?.new ?? 0;
  const deadlinesCount = data?.deadlines ?? 0;

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
              {postponedCount}
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
              {newCount}
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
              {deadlinesCount}
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
        <div className="space-y-4">
          {notifications.length > 0 ? (
            <div className="space-y-4">
              {notifications.map((notification) => (
                <NotificationCard key={notification.id} notification={notification} />
              ))}
            </div>
          ) : (
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
