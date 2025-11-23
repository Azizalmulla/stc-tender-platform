"use client";
// Updated to connect to production backend
import { useQuery } from "@tanstack/react-query";
import { getTenders, getTenderStats } from "@/lib/api";
import { useState } from "react";
import { ModernTenderCard } from "@/components/tenders/ModernTenderCard";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { TrendingUp, FileText, Calendar, AlertCircle, Download, CheckSquare, Square } from "lucide-react";
import { useLanguage } from "@/contexts/LanguageContext";
import { useToast } from "@/components/ui/use-toast";

export default function HomePage() {
  const { t } = useLanguage();
  const { toast } = useToast();
  const [filters, setFilters] = useState({
    ministry: "",
    category: "",
  });
  const [selectedTenders, setSelectedTenders] = useState<Set<number>>(new Set());
  const [isExporting, setIsExporting] = useState(false);

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

  // Selection handlers
  const toggleTenderSelection = (tenderId: number) => {
    const newSelection = new Set(selectedTenders);
    if (newSelection.has(tenderId)) {
      newSelection.delete(tenderId);
    } else {
      newSelection.add(tenderId);
    }
    setSelectedTenders(newSelection);
  };

  const toggleSelectAll = () => {
    if (selectedTenders.size === tenders?.length) {
      setSelectedTenders(new Set());
    } else {
      setSelectedTenders(new Set(tenders?.map(t => t.id) || []));
    }
  };

  // Export handler
  const handleExportToSTC = async () => {
    if (selectedTenders.size === 0) {
      toast({
        title: t("No tenders selected", "لم يتم اختيار مناقصات"),
        description: t("Please select at least one tender to export", "يرجى اختيار مناقصة واحدة على الأقل للتصدير"),
        variant: "destructive"
      });
      return;
    }

    setIsExporting(true);
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/export/stc-template`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tender_ids: Array.from(selectedTenders) })
      });

      if (!response.ok) {
        throw new Error('Export failed');
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `STC_Tenders_Export_${new Date().toISOString().split('T')[0]}.xlsx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);

      toast({
        title: t("Export successful", "تم التصدير بنجاح"),
        description: t(`Exported ${selectedTenders.size} tenders`, `تم تصدير ${selectedTenders.size} مناقصة`),
      });

      setSelectedTenders(new Set()); // Clear selection
    } catch (error) {
      console.error('Export error:', error);
      toast({
        title: t("Export failed", "فشل التصدير"),
        description: t("Failed to export tenders. Please try again.", "فشل تصدير المناقصات. يرجى المحاولة مرة أخرى."),
        variant: "destructive"
      });
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="container py-4 sm:py-6 md:py-8 space-y-4 sm:space-y-6 md:space-y-8 px-4">
      {/* Hero Section */}
      <div className="space-y-2">
        <h1 className="text-2xl sm:text-3xl md:text-4xl font-bold tracking-tight">
          {t("Government Tenders", "المناقصات الحكومية")}
        </h1>
        <p className="text-sm sm:text-base md:text-lg text-muted-foreground">
          {t(
            "Track and analyze government tenders in Kuwait with AI",
            "تتبع وتحليل المناقصات الحكومية في الكويت بالذكاء الاصطناعي"
          )}
        </p>
      </div>

      {/* Stats Grid */}
      {stats && (
        <div className="grid gap-3 sm:gap-4 grid-cols-2 lg:grid-cols-4">
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
              <CardTitle className="text-sm font-medium">{t("Last 7 Days", "آخر 7 أيام")}</CardTitle>
              <TrendingUp className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-green-600">
                +{stats.recent_7_days}
              </div>
              <p className="text-xs text-muted-foreground">
                {t("new tenders", "مناقصة جديدة")}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">{t("Categories", "التصنيفات")}</CardTitle>
              <Calendar className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.categories.length}</div>
              <p className="text-xs text-muted-foreground">
                {t("different categories", "تصنيف مختلف")}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">{t("Upcoming Deadlines", "المواعيد القريبة")}</CardTitle>
              <AlertCircle className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-amber-600">
                {stats.upcoming_deadlines.length}
              </div>
              <p className="text-xs text-muted-foreground">
                {t("ending soon", "تنتهي قريباً")}
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
        <div className="flex items-center justify-between mb-3 sm:mb-4">
          <h2 className="text-xl sm:text-2xl font-bold">
            {t("Latest Tenders", "أحدث المناقصات")}
          </h2>
          
          {/* Export Toolbar */}
          {tenders && tenders.length > 0 && (
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={toggleSelectAll}
                className="gap-2"
              >
                {selectedTenders.size === tenders.length ? (
                  <CheckSquare className="h-4 w-4" />
                ) : (
                  <Square className="h-4 w-4" />
                )}
                <span className="hidden sm:inline">
                  {selectedTenders.size === tenders.length 
                    ? t("Deselect All", "إلغاء تحديد الكل")
                    : t("Select All", "تحديد الكل")}
                </span>
              </Button>
              
              <Button
                onClick={handleExportToSTC}
                disabled={selectedTenders.size === 0 || isExporting}
                className="gap-2"
              >
                <Download className="h-4 w-4" />
                <span className="hidden sm:inline">
                  {isExporting 
                    ? t("Exporting...", "جاري التصدير...")
                    : t(`Export to STC`, `تصدير لـ STC`)
                  }
                </span>
                {selectedTenders.size > 0 && (
                  <Badge variant="secondary" className="ml-1">
                    {selectedTenders.size}
                  </Badge>
                )}
              </Button>
            </div>
          )}
        </div>
        
        {tendersLoading ? (
          <div className="grid gap-4 sm:gap-6 md:grid-cols-2 lg:grid-cols-3">
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
          <div className="grid gap-4 sm:gap-6 md:grid-cols-2 lg:grid-cols-3">
            {tenders.map((tender) => (
              <ModernTenderCard 
                key={tender.id} 
                tender={tender}
                isSelected={selectedTenders.has(tender.id)}
                onToggleSelection={toggleTenderSelection}
              />
            ))}
          </div>
        ) : (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12">
              <FileText className="h-12 w-12 text-muted-foreground mb-4" />
              <p className="text-lg font-medium">{t("No tenders found", "لا توجد مناقصات")}</p>
              <p className="text-sm text-muted-foreground">{t("Try changing the filters", "جرب تغيير الفلاتر")}</p>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
