import axios from "axios";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Debug: Log what we got from environment
if (typeof window !== 'undefined') {
  console.log('🔧 Raw API_URL from env:', API_URL);
}

// Force HTTPS in production
const SAFE_API_URL = API_URL.replace(/^http:\/\/(?!localhost)/, "https://");

if (typeof window !== 'undefined') {
  console.log('🔒 Safe API_URL:', SAFE_API_URL);
}

export const api = axios.create({
  baseURL: SAFE_API_URL,
  headers: {
    "Content-Type": "application/json",
  },
  maxRedirects: 5,
  validateStatus: (status) => status < 500, // Accept redirects
});

// Force HTTPS on every request (belt and suspenders approach)
api.interceptors.request.use((config) => {
  if (config.baseURL && config.baseURL.startsWith('http://') && !config.baseURL.includes('localhost')) {
    config.baseURL = config.baseURL.replace('http://', 'https://');
  }
  console.log('📤 Request URL:', (config.baseURL || '') + (config.url || ''));
  return config;
}, (error) => {
  return Promise.reject(error);
});

// Types
export interface Tender {
  id: number;
  url: string;
  title: string | null;
  summary_ar: string | null;
  summary_en: string | null;
  ministry: string | null;
  category: string | null;
  tender_number: string | null;
  deadline: string | null;
  document_price_kd: number | null;
  published_at: string | null;
  lang: string | null;
  score?: number;
  // Pre-tender meeting fields
  meeting_date: string | null;
  meeting_location: string | null;
  // Postponement fields
  is_postponed: boolean;
  original_deadline: string | null;
  postponement_reason: string | null;
}

export interface TenderDetail extends Tender {
  body: string | null;
  facts_ar: string[] | null;
  facts_en: string[] | null;
  attachments: any | null;
  created_at: string | null;
}

export interface SearchResult extends Tender {
  score?: number;
}

export interface NotificationItem {
  id: number;
  title: string;
  ministry: string | null;
  url: string;
  deadline: string | null;
  published_at: string | null;
  reason: string | null;
  type: 'postponed' | 'new' | 'deadline';
  // AI-powered fields
  relevance_score?: 'very_high' | 'high' | 'medium' | 'low';
  confidence?: number;
  keywords?: string[];
  sectors?: string[];
  recommended_team?: string;
  reasoning?: string;
  urgency?: 'critical' | 'high' | 'medium' | 'low' | 'expired';
  days_left?: number;
  urgency_label?: string;
}

export interface NotificationsSummary {
  postponed: number;
  new: number;
  deadlines: number;
  items: NotificationItem[];
}

export interface ChatResponse {
  answer_ar: string;
  answer_en: string;
  citations: Array<{
    url: string;
    title: string;
    published_at: string | null;
  }>;
  confidence: number;
  context_count: number;
}

export interface TenderStats {
  total_tenders: number;
  categories: Array<{ name: string; count: number }>;
  top_ministries: Array<{ name: string; count: number }>;
  recent_7_days: number;
  upcoming_deadlines: Array<{
    id: number;
    title: string;
    deadline: string;
    ministry: string | null;
  }>;
}

// API Functions
export const getTenders = async (params?: {
  skip?: number;
  limit?: number;
  ministry?: string;
  category?: string;
  lang?: string;
  from_date?: string;
  to_date?: string;
  sector?: string;
  status?: string;
  value_min?: number;
  value_max?: number;
  urgency?: string;
}): Promise<Tender[]> => {
  console.log('🔍 getTenders called with params:', params);
  console.log('🌐 API baseURL:', api.defaults.baseURL);
  try {
    const { data } = await api.get("/api/tenders", { params });
    console.log('✅ getTenders response:', data?.length, 'tenders');
    return data;
  } catch (error: any) {
    console.error('❌ getTenders error:', error.message);
    console.error('Error details:', error.response?.status, error.response?.data);
    throw error;
  }
};

export const getTenderDetail = async (id: number): Promise<TenderDetail> => {
  const { data } = await api.get(`/api/tenders/${id}`);
  return data;
};

export const getTenderStats = async (): Promise<TenderStats> => {
  const { data } = await api.get("/api/tenders/stats/summary");
  return data;
};

export const searchKeyword = async (
  query: string,
  lang?: string,
  limit?: number
): Promise<SearchResult[]> => {
  const { data } = await api.get("/api/search/keyword", {
    params: { q: query, lang, limit },
  });
  return data;
};

export const searchSemantic = async (
  query: string,
  limit?: number,
  threshold?: number
): Promise<SearchResult[]> => {
  const { data } = await api.get("/api/search/semantic", {
    params: { q: query, limit, threshold },
  });
  return data;
};

export const searchHybrid = async (
  query: string,
  limit?: number
): Promise<SearchResult[]> => {
  const { data } = await api.get("/api/search/hybrid", {
    params: { q: query, limit },
  });
  return data;
};

export const askQuestion = async (
  question: string,
  lang?: string,
  limit?: number
): Promise<ChatResponse> => {
  const { data } = await api.post("/api/chat/ask", {
    question,
    lang,
    limit: limit || 5,
  });
  return data;
};

export const getNotifications = async (params?: {
  limit?: number;
  enrich_with_ai?: boolean;
}): Promise<NotificationsSummary> => {
  const { data} = await api.get("/api/notifications", { params });
  return data;
};
