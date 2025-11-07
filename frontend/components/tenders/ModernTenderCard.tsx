"use client";

import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Calendar, Building2, FileText, ExternalLink, Clock, AlertTriangle, Users } from "lucide-react";
import Link from "next/link";
import { Tender } from "@/lib/api";
import { useLanguage } from "@/contexts/LanguageContext";

interface TenderCardProps {
  tender: Tender;
}

export function ModernTenderCard({ tender }: TenderCardProps) {
  const { t } = useLanguage();
  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'غير محدد';
    const date = new Date(dateString);
    return new Intl.DateTimeFormat("ar-KW", {
      year: "numeric",
      month: "long",
      day: "numeric",
    }).format(date);
  };

  const getCategoryColor = (category: string | null) => {
    if (!category) return "bg-gray-500/10 text-gray-700 border-gray-500/20";
    const colors: Record<string, string> = {
      opening: "bg-green-500/10 text-green-700 border-green-500/20",
      closing: "bg-amber-500/10 text-amber-700 border-amber-500/20",
      pre_tenders: "bg-blue-500/10 text-blue-700 border-blue-500/20",
      winning: "bg-purple-500/10 text-purple-700 border-purple-500/20",
    };
    return colors[category] || "bg-gray-500/10 text-gray-700 border-gray-500/20";
  };
  
  const isPreTenderMeeting = tender.category === "pre_tenders";

  const getCategoryLabel = (category: string | null) => {
    if (!category) return t('Unknown', 'غير محدد');
    const labels: Record<string, { en: string; ar: string }> = {
      opening: { en: "Open Tender", ar: "مناقصة مفتوحة" },
      closing: { en: "Closing Soon", ar: "على وشك الإغلاق" },
      pre_tenders: { en: "Pre-Tender Meeting", ar: "اجتماع ما قبل المناقصة" },
      winning: { en: "Awarded", ar: "مناقصة فائزة" },
    };
    const label = labels[category];
    return label ? t(label.en, label.ar) : category;
  };

  return (
    <Card className="group hover:shadow-lg transition-all duration-300 hover:border-primary/50">
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 space-y-2">
            <CardTitle className="text-xl leading-relaxed group-hover:text-primary transition-colors">
              {tender.title || 'بدون عنوان'}
            </CardTitle>
            <div className="flex items-center gap-2 flex-wrap">
              <Badge variant="secondary" className="gap-1">
                <FileText className="h-3 w-3" />
                {tender.tender_number || t('Not specified', 'غير محدد')}
              </Badge>
              
              {/* Pre-Tender Meeting Badge */}
              {isPreTenderMeeting && (
                <Badge className="bg-blue-500/10 text-blue-700 border-blue-500/20 gap-1">
                  <Users className="h-3 w-3" />
                  {getCategoryLabel(tender.category)}
                </Badge>
              )}
              
              {/* Regular Category Badge */}
              {!isPreTenderMeeting && (
                <Badge className={getCategoryColor(tender.category)}>
                  {getCategoryLabel(tender.category)}
                </Badge>
              )}
              
              {/* Postponed Badge */}
              {(tender as any).is_postponed && (
                <Badge className="bg-red-500/10 text-red-700 border-red-500/20 gap-1">
                  <AlertTriangle className="h-3 w-3" />
                  {t('Postponed', 'مؤجل')}
                </Badge>
              )}
            </div>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Ministry */}
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Building2 className="h-4 w-4" />
          <span>{tender.ministry || 'غير محدد'}</span>
        </div>

        {/* Dates */}
        <div className="flex items-center gap-4 text-sm">
          <div className="flex items-center gap-2 text-muted-foreground">
            <Calendar className="h-4 w-4" />
            <span>{formatDate(tender.published_at)}</span>
          </div>
          {tender.deadline && (
            <>
              <Separator orientation="vertical" className="h-4" />
              <div className="flex items-center gap-2 text-amber-600">
                <Clock className="h-4 w-4" />
                <span>ينتهي: {formatDate(tender.deadline)}</span>
              </div>
            </>
          )}
        </div>

        {/* Summary */}
        {tender.summary_ar && (
          <>
            <Separator />
            <p className="text-sm text-muted-foreground line-clamp-3 leading-relaxed">
              {tender.summary_ar}
            </p>
          </>
        )}
      </CardContent>

      <CardFooter className="gap-2">
        <Button asChild className="flex-1 gap-2" variant="default">
          <Link href={`/tenders/${tender.id}`}>
            عرض التفاصيل
          </Link>
        </Button>
        <Button asChild variant="outline" size="icon">
          <a href={tender.url} target="_blank" rel="noopener noreferrer">
            <ExternalLink className="h-4 w-4" />
          </a>
        </Button>
      </CardFooter>
    </Card>
  );
}
