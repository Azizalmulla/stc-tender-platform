"use client";

import { useQuery } from "@tanstack/react-query";
import { 
  getAnalyticsSummary, 
  getAnalyticsTrends, 
  getTopMinistries, 
  getUpcomingDeadlines,
  getUrgencyDistribution,
  getCategoryStats
} from "@/lib/api";
import { 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  LineChart,
  Line,
  Legend,
  AreaChart,
  Area
} from "recharts";
import { 
  FileText, 
  Clock, 
  CheckCircle, 
  AlertTriangle,
  TrendingUp,
  Building2,
  Calendar,
  ArrowLeft,
  Loader2,
  RefreshCw
} from "lucide-react";
import Link from "next/link";

// Apple-style colors
const COLORS = ['#007AFF', '#34C759', '#FF9500', '#FF3B30', '#5856D6', '#AF52DE'];

export default function AnalyticsPage() {
  const { data: summary, isLoading: loadingSummary, refetch: refetchSummary } = useQuery({
    queryKey: ['analytics-summary'],
    queryFn: getAnalyticsSummary,
  });

  const { data: trends, isLoading: loadingTrends } = useQuery({
    queryKey: ['analytics-trends'],
    queryFn: () => getAnalyticsTrends(30),
  });

  const { data: ministries, isLoading: loadingMinistries } = useQuery({
    queryKey: ['analytics-ministries'],
    queryFn: () => getTopMinistries(8),
  });

  const { data: deadlines, isLoading: loadingDeadlines } = useQuery({
    queryKey: ['analytics-deadlines'],
    queryFn: () => getUpcomingDeadlines(14),
  });

  const { data: urgency, isLoading: loadingUrgency } = useQuery({
    queryKey: ['analytics-urgency'],
    queryFn: getUrgencyDistribution,
  });

  const { data: categories, isLoading: loadingCategories } = useQuery({
    queryKey: ['analytics-categories'],
    queryFn: getCategoryStats,
  });

  const isLoading = loadingSummary || loadingTrends || loadingMinistries || 
                    loadingDeadlines || loadingUrgency || loadingCategories;

  // Prepare urgency chart data - Apple colors
  const urgencyData = urgency ? [
    { name: 'عاجل (3 أيام)', value: urgency.urgent_3_days, color: '#FF3B30' },
    { name: 'هذا الأسبوع', value: urgency.this_week, color: '#FF9500' },
    { name: 'هذا الشهر', value: urgency.this_month, color: '#34C759' },
    { name: 'لاحقاً', value: urgency.later, color: '#007AFF' },
    { name: 'منتهي', value: urgency.expired, color: '#8E8E93' },
  ] : [];

  // Prepare category chart data
  const categoryData = categories?.map(cat => ({
    name: cat.category === 'tenders' ? 'مناقصات' : 
          cat.category === 'auctions' ? 'مزايدات' : 
          cat.category === 'practices' ? 'ممارسات' : cat.category,
    active: cat.active,
    expired: cat.expired,
    total: cat.total
  })) || [];

  const refreshAll = () => {
    refetchSummary();
  };

  return (
    <div className="min-h-screen bg-[#F2F2F7] dark:bg-black">
      {/* Header - Apple style */}
      <header className="sticky top-0 z-50 bg-[#F2F2F7]/80 dark:bg-black/80 backdrop-blur-xl border-b border-[#C6C6C8] dark:border-[#38383A]">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/" className="p-2 hover:bg-[#E5E5EA] dark:hover:bg-[#1C1C1E] rounded-xl transition-colors">
              <ArrowLeft className="w-5 h-5 text-[#007AFF]" />
            </Link>
            <div>
              <h1 className="text-2xl font-semibold text-[#1C1C1E] dark:text-white">
                لوحة التحليلات
              </h1>
              <p className="text-sm text-[#8E8E93]">
                إحصائيات وتحليلات المناقصات
              </p>
            </div>
          </div>
          <button 
            onClick={refreshAll}
            className="flex items-center gap-2 px-4 py-2 bg-[#007AFF] text-white rounded-xl hover:bg-[#0056B3] transition-colors font-medium"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
            تحديث
          </button>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-8">
        {/* Summary Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <StatCard
            icon={<FileText className="w-6 h-6" />}
            label="إجمالي المناقصات"
            value={summary?.total_tenders || 0}
            color="violet"
            loading={loadingSummary}
          />
          <StatCard
            icon={<CheckCircle className="w-6 h-6" />}
            label="مناقصات نشطة"
            value={summary?.active_tenders || 0}
            color="emerald"
            loading={loadingSummary}
          />
          <StatCard
            icon={<TrendingUp className="w-6 h-6" />}
            label="جديد هذا الأسبوع"
            value={summary?.new_this_week || 0}
            color="cyan"
            loading={loadingSummary}
          />
          <StatCard
            icon={<AlertTriangle className="w-6 h-6" />}
            label="مواعيد هذا الأسبوع"
            value={summary?.deadlines_this_week || 0}
            color="amber"
            loading={loadingSummary}
          />
        </div>

        {/* Charts Grid */}
        <div className="grid md:grid-cols-2 gap-4 mb-8">
          {/* Tender Trends Chart */}
          <div className="bg-white dark:bg-[#1C1C1E] rounded-2xl p-6 shadow-sm">
            <h2 className="text-lg font-semibold mb-4 flex items-center gap-2 text-[#1C1C1E] dark:text-white">
              <TrendingUp className="w-5 h-5 text-[#007AFF]" />
              اتجاه المناقصات (30 يوم)
            </h2>
            {loadingTrends ? (
              <div className="h-64 flex items-center justify-center">
                <Loader2 className="w-8 h-8 animate-spin text-[#007AFF]" />
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={250}>
                <AreaChart data={trends?.daily || []}>
                  <defs>
                    <linearGradient id="colorCount" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#007AFF" stopOpacity={0.2}/>
                      <stop offset="95%" stopColor="#007AFF" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E5E5EA" />
                  <XAxis 
                    dataKey="date" 
                    tick={{ fontSize: 10, fill: '#8E8E93' }}
                    tickFormatter={(val) => new Date(val).toLocaleDateString('ar-KW', { day: 'numeric', month: 'short' })}
                  />
                  <YAxis tick={{ fontSize: 12, fill: '#8E8E93' }} />
                  <Tooltip 
                    labelFormatter={(val) => new Date(val).toLocaleDateString('ar-KW', { weekday: 'long', day: 'numeric', month: 'long' })}
                    formatter={(val: number) => [val, 'مناقصات']}
                  />
                  <Area 
                    type="monotone" 
                    dataKey="count" 
                    stroke="#007AFF" 
                    fillOpacity={1} 
                    fill="url(#colorCount)" 
                    strokeWidth={2}
                  />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>

          {/* Urgency Distribution */}
          <div className="bg-white dark:bg-[#1C1C1E] rounded-2xl p-6 shadow-sm">
            <h2 className="text-lg font-semibold mb-4 flex items-center gap-2 text-[#1C1C1E] dark:text-white">
              <Clock className="w-5 h-5 text-[#FF9500]" />
              توزيع الاستعجال
            </h2>
            {loadingUrgency ? (
              <div className="h-64 flex items-center justify-center">
                <Loader2 className="w-8 h-8 animate-spin text-[#FF9500]" />
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={250}>
                <PieChart>
                  <Pie
                    data={urgencyData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={90}
                    paddingAngle={3}
                    dataKey="value"
                    label={({ name, percent }) => (percent ?? 0) > 0.05 ? `${((percent ?? 0) * 100).toFixed(0)}%` : ''}
                  >
                    {urgencyData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(val: number, name: string) => [val, name]} />
                  <Legend 
                    layout="vertical" 
                    align="right" 
                    verticalAlign="middle"
                    formatter={(value) => <span className="text-sm">{value}</span>}
                  />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Second Row Charts */}
        <div className="grid md:grid-cols-2 gap-4 mb-8">
          {/* Top Ministries */}
          <div className="bg-white dark:bg-[#1C1C1E] rounded-2xl p-6 shadow-sm">
            <h2 className="text-lg font-semibold mb-4 flex items-center gap-2 text-[#1C1C1E] dark:text-white">
              <Building2 className="w-5 h-5 text-[#5856D6]" />
              أكثر الجهات نشاطاً
            </h2>
            {loadingMinistries ? (
              <div className="h-64 flex items-center justify-center">
                <Loader2 className="w-8 h-8 animate-spin text-[#5856D6]" />
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart 
                  data={ministries || []} 
                  layout="vertical"
                  margin={{ left: 20, right: 20 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#E5E5EA" />
                  <XAxis type="number" tick={{ fontSize: 12, fill: '#8E8E93' }} />
                  <YAxis 
                    dataKey="ministry" 
                    type="category" 
                    width={150}
                    tick={{ fontSize: 11, fill: '#8E8E93' }}
                    tickFormatter={(val) => val.length > 25 ? val.substring(0, 25) + '...' : val}
                  />
                  <Tooltip formatter={(val: number) => [val, 'مناقصات']} />
                  <Bar dataKey="count" fill="#5856D6" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>

          {/* Category Breakdown */}
          <div className="bg-white dark:bg-[#1C1C1E] rounded-2xl p-6 shadow-sm">
            <h2 className="text-lg font-semibold mb-4 flex items-center gap-2 text-[#1C1C1E] dark:text-white">
              <FileText className="w-5 h-5 text-[#34C759]" />
              توزيع الفئات
            </h2>
            {loadingCategories ? (
              <div className="h-64 flex items-center justify-center">
                <Loader2 className="w-8 h-8 animate-spin text-[#34C759]" />
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={categoryData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E5E5EA" />
                  <XAxis dataKey="name" tick={{ fontSize: 12, fill: '#8E8E93' }} />
                  <YAxis tick={{ fontSize: 12, fill: '#8E8E93' }} />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="active" name="نشط" fill="#34C759" stackId="a" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="expired" name="منتهي" fill="#8E8E93" stackId="a" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Upcoming Deadlines */}
        <div className="bg-white dark:bg-[#1C1C1E] rounded-2xl p-6 shadow-sm">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2 text-[#1C1C1E] dark:text-white">
            <Calendar className="w-5 h-5 text-[#FF3B30]" />
            المواعيد القادمة (14 يوم)
          </h2>
          {loadingDeadlines ? (
            <div className="h-48 flex items-center justify-center">
              <Loader2 className="w-8 h-8 animate-spin text-[#FF3B30]" />
            </div>
          ) : deadlines && deadlines.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={deadlines}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E5E5EA" />
                <XAxis 
                  dataKey="date" 
                  tick={{ fontSize: 10, fill: '#8E8E93' }}
                  tickFormatter={(val) => new Date(val).toLocaleDateString('ar-KW', { day: 'numeric', month: 'short' })}
                />
                <YAxis tick={{ fontSize: 12, fill: '#8E8E93' }} />
                <Tooltip 
                  labelFormatter={(val) => new Date(val).toLocaleDateString('ar-KW', { weekday: 'long', day: 'numeric', month: 'long' })}
                  formatter={(val: number) => [val, 'مناقصات']}
                />
                <Bar dataKey="count" fill="#FF3B30" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-48 flex items-center justify-center text-[#8E8E93]">
              لا توجد مواعيد نهائية في الأسبوعين القادمين
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

// Stat Card Component - Apple style
function StatCard({ 
  icon, 
  label, 
  value, 
  color, 
  loading 
}: { 
  icon: React.ReactNode; 
  label: string; 
  value: number; 
  color: 'violet' | 'emerald' | 'cyan' | 'amber';
  loading?: boolean;
}) {
  // Apple color mapping
  const iconColors = {
    violet: 'text-[#5856D6]',
    emerald: 'text-[#34C759]',
    cyan: 'text-[#007AFF]',
    amber: 'text-[#FF9500]',
  };

  return (
    <div className="bg-white dark:bg-[#1C1C1E] rounded-2xl p-5 shadow-sm transition-all hover:shadow-md">
      <div className="flex items-center gap-3 mb-2">
        <span className={iconColors[color]}>{icon}</span>
        <span className="text-sm font-medium text-[#8E8E93]">{label}</span>
      </div>
      {loading ? (
        <Loader2 className={`w-6 h-6 animate-spin ${iconColors[color]}`} />
      ) : (
        <div className="text-3xl font-semibold text-[#1C1C1E] dark:text-white">{value.toLocaleString('ar-KW')}</div>
      )}
    </div>
  );
}
