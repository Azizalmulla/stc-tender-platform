import axios from "axios";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    "Content-Type": "application/json",
  },
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
}): Promise<Tender[]> => {
  const { data } = await api.get("/api/tenders/", { params });
  return data;
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
