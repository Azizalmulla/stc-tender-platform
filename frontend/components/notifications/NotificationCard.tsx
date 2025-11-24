"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { 
  Bell, 
  ExternalLink, 
  Clock, 
  AlertTriangle,
  TrendingUp,
  Sparkles,
  Users,
  Tag
} from "lucide-react";
import Link from "next/link";
import { NotificationItem } from "@/lib/api";
import { useLanguage } from "@/contexts/LanguageContext";

interface NotificationCardProps {
  notification: NotificationItem;
}

export function NotificationCard({ notification }: NotificationCardProps) {
  const { t } = useLanguage();

  // Get type icon and color
  const getTypeConfig = () => {
    switch (notification.type) {
      case 'postponed':
        return {
          icon: <AlertTriangle className="h-5 w-5" />,
          color: 'text-red-600',
          bgColor: 'bg-red-50',
          borderColor: 'border-red-200'
        };
      case 'new':
        return {
          icon: <TrendingUp className="h-5 w-5" />,
          color: 'text-green-600',
          bgColor: 'bg-green-50',
          borderColor: 'border-green-200'
        };
      case 'deadline':
        return {
          icon: <Clock className="h-5 w-5" />,
          color: 'text-orange-600',
          bgColor: 'bg-orange-50',
          borderColor: 'border-orange-200'
        };
    }
  };

  // Get urgency badge
  const getUrgencyBadge = () => {
    if (!notification.urgency || !notification.urgency_label) return null;
    
    const colors: Record<string, string> = {
      critical: 'bg-red-600 text-white',
      high: 'bg-orange-500 text-white',
      medium: 'bg-yellow-500 text-white',
      low: 'bg-green-500 text-white',
      expired: 'bg-gray-500 text-white'
    };

    return (
      <Badge className={`${colors[notification.urgency]} gap-1`}>
        <Clock className="h-3 w-3" />
        {notification.urgency_label}
      </Badge>
    );
  };

  // Get relevance badge
  const getRelevanceBadge = () => {
    if (!notification.relevance_score) return null;

    const colors: Record<string, string> = {
      very_high: 'bg-purple-600 text-white',
      high: 'bg-blue-600 text-white',
      medium: 'bg-yellow-600 text-white',
      low: 'bg-gray-500 text-white'
    };

    const labels: Record<string, { en: string; ar: string }> = {
      very_high: { en: 'Very High Relevance', ar: 'صلة عالية جداً' },
      high: { en: 'High Relevance', ar: 'صلة عالية' },
      medium: { en: 'Medium Relevance', ar: 'صلة متوسطة' },
      low: { en: 'Low Relevance', ar: 'صلة منخفضة' }
    };

    const label = labels[notification.relevance_score];

    return (
      <Badge className={`${colors[notification.relevance_score]} gap-1`}>
        <Sparkles className="h-3 w-3" />
        {t(label.en, label.ar)}
        {notification.confidence && (
          <span className="ml-1 opacity-80">
            ({Math.round(notification.confidence * 100)}%)
          </span>
        )}
      </Badge>
    );
  };

  const typeConfig = getTypeConfig();

  // Get notification alert header
  const getAlertHeader = () => {
    const headers: Record<string, { en: string; ar: string }> = {
      new: { en: 'New tender detected for STC', ar: 'مناقصة جديدة تم اكتشافها لـ STC' },
      deadline: { en: 'Upcoming deadline for STC', ar: 'موعد نهائي قادم لـ STC' },
      postponed: { en: 'Tender postponed - STC', ar: 'تأجيل المناقصة - STC' }
    };
    return headers[notification.type];
  };

  const alertHeader = getAlertHeader();

  return (
    <Card className={`${typeConfig.borderColor} ${typeConfig.bgColor} border-2 hover:shadow-lg transition-all`}>
      <CardContent className="p-4 space-y-3">
        {/* Alert Header - "New tender detected for STC" */}
        <div className="flex items-center gap-2 pb-2 border-b">
          <Bell className={`h-4 w-4 ${typeConfig.color}`} />
          <span className={`text-sm font-semibold ${typeConfig.color}`}>
            {t(alertHeader.en, alertHeader.ar)}
          </span>
        </div>

        {/* Tender Details */}
        <div className="space-y-2">
          <div className="text-sm">
            <span className="font-semibold text-muted-foreground">
              {t("Entity:", "الجهة:")}
            </span>{" "}
            <span className="font-medium">
              {notification.ministry || t("Unknown", "غير محدد")}
            </span>
          </div>
          
          <div>
            <span className="text-sm font-semibold text-muted-foreground">
              {t("Title:", "العنوان:")}
            </span>
            <h3 className="font-bold text-lg leading-tight mt-1">
              "{notification.title}"
            </h3>
          </div>
        </div>

        {/* AI Insights */}
        {notification.relevance_score && (
          <div className="space-y-2 border-t pt-3">
            <div className="flex flex-wrap gap-2">
              {getRelevanceBadge()}
              {getUrgencyBadge()}
            </div>

            {/* Keywords */}
            {notification.keywords && notification.keywords.length > 0 && (
              <div className="flex flex-wrap gap-1">
                <Tag className="h-4 w-4 text-muted-foreground" />
                {notification.keywords.map((keyword, idx) => (
                  <Badge key={idx} variant="outline" className="text-xs">
                    {keyword}
                  </Badge>
                ))}
              </div>
            )}

            {/* Recommended Team */}
            {notification.recommended_team && (
              <div className="flex items-center gap-2 text-sm">
                <Users className="h-4 w-4 text-blue-600" />
                <span className="font-semibold text-blue-600">
                  {notification.recommended_team}
                </span>
              </div>
            )}

            {/* AI Reasoning */}
            {notification.reasoning && (
              <p className="text-sm text-muted-foreground italic">
                💡 {notification.reasoning}
              </p>
            )}
          </div>
        )}

        {/* Postponement Reason */}
        {notification.reason && (
          <div className="border-t pt-3">
            <p className="text-sm">
              <span className="font-semibold text-red-600">
                {t("Reason:", "السبب:")}
              </span>{" "}
              {notification.reason}
            </p>
          </div>
        )}

        {/* Action Button */}
        <div className="border-t pt-3">
          <Link href={`/tender/${notification.id}`}>
            <Button className="w-full gap-2" variant="default">
              {t("Open in Dashboard", "فتح في لوحة التحكم")}
              <ExternalLink className="h-4 w-4" />
            </Button>
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}
