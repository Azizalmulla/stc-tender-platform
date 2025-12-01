"use client";

import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Calendar, Building2, FileText, ExternalLink, Clock, AlertTriangle, Users, CheckSquare, Square, Heart } from "lucide-react";
import Link from "next/link";
import { Tender } from "@/lib/api";
import { useLanguage } from "@/contexts/LanguageContext";
import { useSavedTenders } from "@/hooks/useSavedTenders";

interface TenderCardProps {
  tender: Tender;
  isSelected?: boolean;
  onToggleSelection?: (tenderId: number) => void;
}

export function ModernTenderCard({ tender, isSelected = false, onToggleSelection }: TenderCardProps) {
  const { t, language } = useLanguage();
  const { isSaved, toggleSave } = useSavedTenders();
  const saved = isSaved(tender.id);
  
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
    <Card className={`group hover:shadow-lg transition-all duration-300 ${isSelected ? 'border-primary border-2' : 'hover:border-primary/50'}`}>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          {/* Selection Checkbox */}
          {onToggleSelection && (
            <button
              onClick={(e) => {
                e.preventDefault();
                onToggleSelection(tender.id);
              }}
              className="mt-1 hover:opacity-70 transition-opacity"
            >
              {isSelected ? (
                <CheckSquare className="h-5 w-5 text-primary" />
              ) : (
                <Square className="h-5 w-5 text-muted-foreground" />
              )}
            </button>
          )}
          
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
        <div className="flex items-center gap-4 text-sm flex-wrap">
          <div className="flex items-center gap-2 text-muted-foreground">
            <Calendar className="h-4 w-4" />
            <span>{formatDate(tender.published_at)}</span>
          </div>
          {tender.deadline && (
            <>
              <Separator orientation="vertical" className="h-4" />
              <div className="flex items-center gap-2 text-amber-600">
                <Clock className="h-4 w-4" />
                <span>{t('Deadline:', 'ينتهي:')} {formatDate(tender.deadline)}</span>
              </div>
            </>
          )}
        </div>

        {/* Pre-Tender Meeting Info */}
        {(tender.meeting_date || tender.meeting_location) && (
          <div className="flex items-start gap-2 text-sm p-3 bg-purple-50 dark:bg-purple-950/20 rounded-lg border border-purple-200 dark:border-purple-900">
            <Users className="h-4 w-4 text-purple-600 mt-0.5 flex-shrink-0" />
            <div className="flex-1 space-y-1">
              <div className="font-medium text-purple-900 dark:text-purple-100">
                {t('Pre-Tender Meeting', 'اجتماع ما قبل المناقصة')}
              </div>
              {tender.meeting_date && (
                <div className="text-purple-700 dark:text-purple-300">
                  📅 {formatDate(tender.meeting_date)}
                </div>
              )}
              {tender.meeting_location && (
                <div className="text-purple-700 dark:text-purple-300">
                  📍 {tender.meeting_location}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Summary */}
        {(language === 'en' ? tender.summary_en : tender.summary_ar) && (
          <>
            <Separator />
            <p className="text-sm text-muted-foreground line-clamp-3 leading-relaxed">
              {language === 'en' ? tender.summary_en : tender.summary_ar}
            </p>
          </>
        )}
      </CardContent>

      <CardFooter className="gap-2">
        <Button asChild className="flex-1 gap-2" variant="default">
          <Link href={`/tender/${tender.id}`}>
            {t('View Details', 'عرض التفاصيل')}
          </Link>
        </Button>
        <Button 
          variant="outline" 
          size="icon"
          onClick={(e) => {
            e.preventDefault();
            toggleSave(tender.id);
          }}
          className={saved ? 'text-red-500 hover:text-red-600' : 'text-muted-foreground hover:text-red-500'}
        >
          <Heart className={`h-4 w-4 ${saved ? 'fill-current' : ''}`} />
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
