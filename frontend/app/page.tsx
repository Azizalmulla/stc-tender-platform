"use client";

import { useQuery } from "@tanstack/react-query";
import { getTenders, getTenderStats } from "@/lib/api";
import { useState } from "react";
import { ModernTenderCard } from "@/components/tenders/ModernTenderCard";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { TrendingUp, FileText, Calendar, AlertCircle } from "lucide-react";
import { useLanguage } from "@/contexts/LanguageContext";

export default function HomePage() {
  const { t } = useLanguage();
  const [filters, setFilters] = useState({
    ministry: "",
    category: "",
  });

  const { data: tenders, isLoading: tendersLoading } = useQuery({
    queryKey: ["tenders", filters],
    queryFn: () =>
      getTenders({
        ministry: filters.ministry || undefined,
        category: filters.category || undefined,
        limit: 50,
      }),
  });

  const { data: stats } = useQuery({
    queryKey: ["stats"],
    queryFn: getTenderStats,
  });

  return (
    <div className="container py-8 space-y-8">
      {/* Hero Section */}
      <div className="space-y-2">
        <h1 className="text-4xl font-bold tracking-tight">
          {t("Government Tenders", "المناقصات الحكومية")}
        </h1>
        <p className="text-lg text-muted-foreground">
          {t(
            "Track and analyze government tenders in Kuwait with AI",
            "تتبع وتحليل المناقصات الحكومية في الكويت بالذكاء الاصطناعي"
          )}
        </p>
      </div>

      {/* Stats Grid */}
      {stats && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">
                {t("Total Tenders", "إجمالي المناقصات")}
              </CardTitle>
              <FileText className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.total_tenders.toLocaleString()}</div>
              <p className="text-xs text-muted-foreground">
                {t("in system", "في النظام")}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">آخر 7 أيام</CardTitle>
              <TrendingUp className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-green-600">
                +{stats.recent_7_days}
              </div>
              <p className="text-xs text-muted-foreground">
                مناقصة جديدة
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">التصنيفات</CardTitle>
              <Calendar className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.categories.length}</div>
              <p className="text-xs text-muted-foreground">
                تصنيف مختلف
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">المواعيد القريبة</CardTitle>
              <AlertCircle className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-amber-600">
                {stats.upcoming_deadlines.length}
              </div>
              <p className="text-xs text-muted-foreground">
                تنتهي قريباً
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Filters */}
      <Card>
        <CardHeader>
          <CardTitle>{t("Filter Tenders", "تصفية المناقصات")}</CardTitle>
          <CardDescription>
            {t(
              "Search for tenders by ministry or category",
              "ابحث عن المناقصات حسب الوزارة أو التصنيف"
            )}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1">
              <Input
                placeholder={t("Search by ministry...", "ابحث حسب الوزارة...")}
                value={filters.ministry}
                onChange={(e) => setFilters({ ...filters, ministry: e.target.value })}
              />
            </div>
            <div className="flex gap-2">
              {filters.ministry || filters.category ? (
                <Button
                  variant="outline"
                  onClick={() => setFilters({ ministry: "", category: "" })}
                >
                  {t("Clear Filters", "مسح الفلاتر")}
                </Button>
              ) : null}
            </div>
          </div>
          
          {stats && stats.categories.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-4">
              {stats.categories.map((cat) => (
                <Badge
                  key={cat.name}
                  variant={filters.category === cat.name ? "default" : "outline"}
                  className="cursor-pointer"
                  onClick={() =>
                    setFilters({
                      ...filters,
                      category: filters.category === cat.name ? "" : cat.name,
                    })
                  }
                >
                  {cat.name} ({cat.count})
                </Badge>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Tenders Grid */}
      <div>
        <h2 className="text-2xl font-bold mb-4">
          {t("Latest Tenders", "أحدث المناقصات")}
        </h2>
        
        {tendersLoading ? (
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {[...Array(6)].map((_, i) => (
              <Card key={i}>
                <CardHeader>
                  <Skeleton className="h-4 w-3/4" />
                  <Skeleton className="h-3 w-1/2" />
                </CardHeader>
                <CardContent>
                  <Skeleton className="h-20 w-full" />
                </CardContent>
              </Card>
            ))}
          </div>
        ) : tenders && tenders.length > 0 ? (
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {tenders.map((tender) => (
              <ModernTenderCard key={tender.id} tender={tender} />
            ))}
          </div>
        ) : (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12">
              <FileText className="h-12 w-12 text-muted-foreground mb-4" />
              <p className="text-lg font-medium">لا توجد مناقصات</p>
              <p className="text-sm text-muted-foreground">جرب تغيير الفلاتر</p>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
