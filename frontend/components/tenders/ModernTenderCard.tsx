"use client";

import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Calendar, Building2, FileText, ExternalLink, Clock } from "lucide-react";
import Link from "next/link";

interface TenderCardProps {
  tender: {
    id: number;
    title: string | null;
    tender_number: string;
    ministry: string;
    category: string;
    published_at: string;
    deadline?: string | null;
    summary_ar?: string | null;
    url: string;
  };
}

export function ModernTenderCard({ tender }: TenderCardProps) {
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return new Intl.DateTimeFormat("ar-KW", {
      year: "numeric",
      month: "long",
      day: "numeric",
    }).format(date);
  };

  const getCategoryColor = (category: string) => {
    const colors: Record<string, string> = {
      opening: "bg-green-500/10 text-green-700 border-green-500/20",
      closing: "bg-amber-500/10 text-amber-700 border-amber-500/20",
      pre_tenders: "bg-blue-500/10 text-blue-700 border-blue-500/20",
      winning: "bg-purple-500/10 text-purple-700 border-purple-500/20",
    };
    return colors[category] || "bg-gray-500/10 text-gray-700 border-gray-500/20";
  };

  const getCategoryLabel = (category: string) => {
    const labels: Record<string, string> = {
      opening: "مناقصة مفتوحة",
      closing: "على وشك الإغلاق",
      pre_tenders: "ما قبل المناقصة",
      winning: "مناقصة فائزة",
    };
    return labels[category] || category;
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
                {tender.tender_number}
              </Badge>
              <Badge className={getCategoryColor(tender.category)}>
                {getCategoryLabel(tender.category)}
              </Badge>
            </div>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Ministry */}
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Building2 className="h-4 w-4" />
          <span>{tender.ministry}</span>
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
