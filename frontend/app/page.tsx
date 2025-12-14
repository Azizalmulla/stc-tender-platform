"use client";
// Updated to connect to production backend
import { useQuery } from "@tanstack/react-query";
import { getTenders, getTenderStats, Tender } from "@/lib/api";
import { useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { ModernTenderCard } from "@/components/tenders/ModernTenderCard";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { TrendingUp, FileText, Calendar, AlertCircle, Download, CheckSquare, Square, Loader2, BarChart3, Heart } from "lucide-react";
import Link from "next/link";
import { useLanguage } from "@/contexts/LanguageContext";
import { useToast } from "@/components/ui/use-toast";
import { useSavedTenders } from "@/hooks/useSavedTenders";

const PAGE_SIZE = 50;

export default function HomePage() {
  const { t } = useLanguage();
  const { toast } = useToast();
  const { savedTenderIds, savedCount } = useSavedTenders();
  const searchParams = useSearchParams();
  const [showSavedOnly, setShowSavedOnly] = useState(false);
  
  // Initialize filters from URL params
  const [filters, setFilters] = useState({
    ministry: searchParams.get("ministry") || "",
    category: searchParams.get("category") || "",
    sector: searchParams.get("sector") || "",
    status: searchParams.get("status") || "",  // "active" or "expired"
    value_range: searchParams.get("value_range") || "",
    urgency: searchParams.get("urgency") || "",
  });
  
  // Update filters when URL params change
  useEffect(() => {
    setFilters({
      ministry: searchParams.get("ministry") || "",
      category: searchParams.get("category") || "",
      sector: searchParams.get("sector") || "",
      status: searchParams.get("status") || "",
      value_range: searchParams.get("value_range") || "",
      urgency: searchParams.get("urgency") || "",
    });
  }, [searchParams]);
  const [selectedTenders, setSelectedTenders] = useState<Set<number>>(new Set());
  const [isExporting, setIsExporting] = useState(false);
  
  // Pagination state
  const [allTenders, setAllTenders] = useState<Tender[]>([]);
  const [currentPage, setCurrentPage] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);

  // Initial data fetch
  const { data: initialTenders, isLoading: tendersLoading } = useQuery({
    queryKey: ["tenders", filters],
    queryFn: () =>
      getTenders({
        ministry: filters.ministry || undefined,
        category: filters.category || undefined,
        sector: filters.sector || undefined,
        deadline_status: filters.status || undefined,
        value_min: filters.value_range === "under_100k" ? undefined : filters.value_range === "100k_1m" ? 100000 : filters.value_range === "over_1m" ? 1000000 : undefined,
        value_max: filters.value_range === "under_100k" ? 100000 : filters.value_range === "100k_1m" ? 1000000 : undefined,
        urgency: filters.urgency || undefined,
        limit: PAGE_SIZE,
        skip: 0,
      }),
  });

  // Reset pagination when filters change or initial data loads
  useEffect(() => {
    if (initialTenders) {
      setAllTenders(initialTenders);
      setCurrentPage(0);
      setHasMore(initialTenders.length === PAGE_SIZE);
    }
  }, [initialTenders]);

  // Load more function
  const loadMore = async () => {
    if (isLoadingMore || !hasMore) return;
    
    setIsLoadingMore(true);
    try {
      const nextPage = currentPage + 1;
      const moreTenders = await getTenders({
        ministry: filters.ministry || undefined,
        category: filters.category || undefined,
        sector: filters.sector || undefined,
        deadline_status: filters.status || undefined,
        value_min: filters.value_range === "under_100k" ? undefined : filters.value_range === "100k_1m" ? 100000 : filters.value_range === "over_1m" ? 1000000 : undefined,
        value_max: filters.value_range === "under_100k" ? 100000 : filters.value_range === "100k_1m" ? 1000000 : undefined,
        urgency: filters.urgency || undefined,
        limit: PAGE_SIZE,
        skip: nextPage * PAGE_SIZE,
      });
      
      if (moreTenders.length > 0) {
        setAllTenders(prev => [...prev, ...moreTenders]);
        setCurrentPage(nextPage);
        setHasMore(moreTenders.length === PAGE_SIZE);
      } else {
        setHasMore(false);
      }
    } catch (error) {
      console.error("Error loading more tenders:", error);
      toast({
        title: t("Error", "خطأ"),
        description: t("Failed to load more tenders", "فشل تحميل المزيد من المناقصات"),
        variant: "destructive",
      });
    } finally {
      setIsLoadingMore(false);
    }
  };

  // Use allTenders for display
  const tenders = allTenders;

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
      a.download = "STC_Tenders_Master.xlsx";  // Always same filename - master file
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);

      toast({
        title: t("Master file updated", "تم تحديث الملف الرئيسي"),
        description: t(
          `Added ${selectedTenders.size} tenders to STC Master. Download the updated file.`,
          `تمت إضافة ${selectedTenders.size} مناقصة إلى ملف STC الرئيسي. قم بتنزيل الملف المحدث.`
        ),
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
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
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
        <Link href="/analytics">
          <Button variant="outline" className="gap-2">
            <BarChart3 className="w-4 h-4" />
            {t("Analytics", "التحليلات")}
          </Button>
        </Link>
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
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {/* Ministry Search */}
            <div>
              <label className="text-sm font-medium mb-2 block">
                {t("Ministry / Entity", "الوزارة / الجهة")}
              </label>
              <Input
                placeholder={t("Search by ministry...", "ابحث حسب الوزارة...")}
                value={filters.ministry}
                onChange={(e) => setFilters({ ...filters, ministry: e.target.value })}
              />
            </div>

            {/* Sector Filter - STC specific sectors */}
            <div>
              <label className="text-sm font-medium mb-2 block">
                {t("Sector", "القطاع")}
              </label>
              <select
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                value={filters.sector}
                onChange={(e) => setFilters({ ...filters, sector: e.target.value })}
              >
                <option value="">{t("All Sectors", "جميع القطاعات")}</option>
                <option value="telecom">{t("Telecom infrastructure", "بنية الاتصالات التحتية")}</option>
                <option value="datacenter">{t("Data center & cloud", "مركز البيانات والسحابة")}</option>
                <option value="callcenter">{t("Contact center / call center", "مركز الاتصال")}</option>
                <option value="network">{t("Networking & security", "الشبكات والأمن")}</option>
                <option value="smartcity">{t("Smart city / IoT", "المدينة الذكية")}</option>
              </select>
            </div>

            {/* Status Filter */}
            <div>
              <label className="text-sm font-medium mb-2 block">
                {t("Status", "الحالة")}
              </label>
              <select
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                value={filters.status}
                onChange={(e) => setFilters({ ...filters, status: e.target.value })}
              >
                <option value="">{t("All Statuses", "جميع الحالات")}</option>
                <option value="open">{t("Open", "مفتوحة")}</option>
                <option value="closed">{t("Closed", "مغلقة")}</option>
                <option value="awarded">{t("Awarded", "تم الترسية")}</option>
                <option value="cancelled">{t("Cancelled", "ملغاة")}</option>
              </select>
            </div>

            {/* Value Range Filter */}
            <div>
              <label className="text-sm font-medium mb-2 block">
                {t("Value Range (KD)", "نطاق القيمة (د.ك)")}
              </label>
              <select
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                value={filters.value_range}
                onChange={(e) => setFilters({ ...filters, value_range: e.target.value })}
              >
                <option value="">{t("All Values", "جميع القيم")}</option>
                <option value="under_100k">{t("< 100K KD", "< 100 ألف د.ك")}</option>
                <option value="100k_1m">{t("100K - 1M KD", "100 ألف - 1 مليون د.ك")}</option>
                <option value="over_1m">{t("1M+ KD", "1 مليون+ د.ك")}</option>
              </select>
            </div>

            {/* Urgency Filter */}
            <div>
              <label className="text-sm font-medium mb-2 block">
                {t("Urgency", "الاستعجال")}
              </label>
              <select
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                value={filters.urgency}
                onChange={(e) => setFilters({ ...filters, urgency: e.target.value })}
              >
                <option value="">{t("All Deadlines", "جميع المواعيد")}</option>
                <option value="7_days">{t("Deadline < 7 days", "الموعد < 7 أيام")}</option>
                <option value="14_days">{t("Deadline < 14 days", "الموعد < 14 يوم")}</option>
              </select>
            </div>

            {/* Clear Filters Button */}
            <div className="flex items-end">
              {(filters.ministry || filters.category || filters.sector || filters.status || filters.value_range || filters.urgency) && (
                <Button
                  variant="outline"
                  className="w-full"
                  onClick={() => setFilters({ ministry: "", category: "", sector: "", status: "", value_range: "", urgency: "" })}
                >
                  {t("Clear Filters", "مسح الفلاتر")}
                </Button>
              )}
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
          <div className="flex items-center gap-3">
            <h2 className="text-xl sm:text-2xl font-bold">
              {t("Latest Tenders", "أحدث المناقصات")}
            </h2>
            <Button
              variant={showSavedOnly ? "default" : "outline"}
              size="sm"
              onClick={() => setShowSavedOnly(!showSavedOnly)}
              className="gap-2"
            >
              <Heart className={`h-4 w-4 ${showSavedOnly ? 'fill-current' : ''}`} />
              {t("Saved", "المحفوظة")}
              {savedCount > 0 && (
                <Badge variant={showSavedOnly ? "secondary" : "outline"} className="ml-1">
                  {savedCount}
                </Badge>
              )}
            </Button>
          </div>
          
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
          <>
            <div className="grid gap-4 sm:gap-6 md:grid-cols-2 lg:grid-cols-3">
              {(showSavedOnly 
                ? tenders.filter(t => savedTenderIds.includes(t.id))
                : tenders
              ).map((tender) => (
                <ModernTenderCard 
                  key={tender.id} 
                  tender={tender}
                  isSelected={selectedTenders.has(tender.id)}
                  onToggleSelection={toggleTenderSelection}
                />
              ))}
            </div>
            {showSavedOnly && tenders.filter(t => savedTenderIds.includes(t.id)).length === 0 && (
              <div className="text-center py-12 text-muted-foreground">
                <Heart className="h-12 w-12 mx-auto mb-4 opacity-20" />
                <p>{t("No saved tenders yet", "لا توجد مناقصات محفوظة بعد")}</p>
                <p className="text-sm mt-1">{t("Click the heart icon on any tender to save it", "انقر على أيقونة القلب لحفظ أي مناقصة")}</p>
              </div>
            )}
            
            {/* Load More Button */}
            {hasMore && (
              <div className="flex justify-center mt-8">
                <Button
                  variant="outline"
                  size="lg"
                  onClick={loadMore}
                  disabled={isLoadingMore}
                  className="gap-2 px-8"
                >
                  {isLoadingMore ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      {t("Loading...", "جاري التحميل...")}
                    </>
                  ) : (
                    <>
                      {t("Load More Tenders", "تحميل المزيد من المناقصات")}
                      <Badge variant="secondary">{tenders.length} {t("loaded", "محمّل")}</Badge>
                    </>
                  )}
                </Button>
              </div>
            )}
            
            {/* All loaded message */}
            {!hasMore && tenders.length > PAGE_SIZE && (
              <div className="flex justify-center mt-8">
                <p className="text-muted-foreground">
                  ✅ {t(`All ${tenders.length} tenders loaded`, `تم تحميل جميع المناقصات (${tenders.length})`)}
                </p>
              </div>
            )}
          </>
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
