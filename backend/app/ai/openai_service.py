from openai import OpenAI
from typing import List, Dict, Optional
import json
from app.core.config import settings


class OpenAIService:
    """Service for OpenAI API interactions"""
    
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.OPENAI_MODEL
        self.embedding_model = settings.OPENAI_EMBEDDING_MODEL
    
    def summarize_tender(self, title: str, body: str, lang: str = "ar") -> Dict:
        """
        Generate bilingual summary and key facts for a tender
        
        Args:
            title: Tender title
            body: Tender body text
            lang: Primary language ('ar' or 'en')
            
        Returns:
            Dict with summary_ar, summary_en, facts_ar, facts_en
        """
        prompt = f"""You are an Arabic tender extraction assistant.
Extract structured information from this Kuwait Alyoum tender text.

Title: {title}
Body: {body[:3000]}

Return JSON with:
{{
 "summary_ar": "موجز بالعربية في سطرين فقط",
 "summary_en": "English summary in 2 lines only",
 "facts_ar": ["حقيقة 1", "حقيقة 2", "حقيقة 3"],
 "facts_en": ["Fact 1", "Fact 2", "Fact 3"]
}}

Rules:
- Keep summaries under 2 lines each
- Extract 3-5 key facts
- Arabic first, then English
- Never fabricate missing data
- Focus on: ministry, deadline, tender number, requirements, budget
"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=settings.TEMPERATURE,
                max_tokens=settings.MAX_TOKENS_SUMMARY,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            
            return {
                "summary_ar": result.get("summary_ar", ""),
                "summary_en": result.get("summary_en", ""),
                "facts_ar": result.get("facts_ar", []),
                "facts_en": result.get("facts_en", [])
            }
            
        except Exception as e:
            print(f"Summarization error: {e}")
            return {
                "summary_ar": title[:200] if lang == "ar" else "",
                "summary_en": title[:200] if lang == "en" else "",
                "facts_ar": [],
                "facts_en": []
            }
    
    def extract_structured_data(self, text: str) -> Dict:
        """
        Extract structured fields from tender text
        
        Args:
            text: Full tender text
            
        Returns:
            Dict with ministry, tender_number, deadline, document_price_kd, category
        """
        prompt = f"""Extract these fields from this Kuwait tender text:

{text[:2000]}

Return JSON:
{{
 "ministry": "Ministry name or issuing entity",
 "tender_number": "Tender/RFP number if found",
 "deadline": "YYYY-MM-DD format if date found",
 "document_price_kd": numeric value in KD,
 "category": "IT" or "Construction" or "Services" or "Healthcare" or "Infrastructure" or "Other"
}}

Rules:
- Return null for missing fields
- Guess category based on keywords
- Parse dates from Arabic or English text
- Extract numbers carefully
"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=200,
                response_format={"type": "json_object"}
            )
            
            return json.loads(response.choices[0].message.content)
            
        except Exception as e:
            print(f"Structured extraction error: {e}")
            return {
                "ministry": None,
                "tender_number": None,
                "deadline": None,
                "document_price_kd": None,
                "category": None
            }
    
    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector for text
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector (3072 dimensions for text-embedding-3-large)
        """
        try:
            # Truncate if too long (max ~8000 tokens)
            text = text[:30000]
            
            response = self.client.embeddings.create(
                model=self.embedding_model,
                input=text
            )
            
            return response.data[0].embedding
            
        except Exception as e:
            print(f"Embedding generation error: {e}")
            return [0.0] * settings.EMBEDDING_DIMENSION
    
    def answer_question(self, question: str, context_docs: List[Dict], conversation_history: List[Dict] = None) -> Dict:
        """
        Answer a question about tenders using RAG with conversation context
        
        Args:
            question: User question in Arabic or English
            context_docs: List of relevant tender documents
            conversation_history: Previous conversation messages for context (optional)
            
        Returns:
            Dict with answer_ar, answer_en, citations, confidence
        """
        # Build context from documents
        context = "\n\n---\n\n".join([
            f"Title: {doc['title']}\n"
            f"Body: {doc['body'][:3000]}\n"
            f"URL: {doc['url']}\n"
            f"Published: {doc.get('published_at', 'N/A')}\n"
            f"Deadline: {doc.get('deadline', 'N/A')}\n"
            f"Ministry: {doc.get('ministry', 'N/A')}"
            for doc in context_docs[:10]  # Use top 10 documents for better coverage
        ])
        
        # Build conversation context
        conversation_context = ""
        if conversation_history:
            conversation_context = "\n\nPrevious Conversation:\n" + "\n".join([
                f"{msg['role'].capitalize()}: {msg['content']}"
                for msg in conversation_history[-6:]  # Last 3 exchanges (6 messages)
            ])
        
        system_prompt = f"""You are an expert assistant for Kuwait government tenders from Kuwait Al-Yawm (Official Gazette).

INSTRUCTIONS:
1. Answer ONLY using the provided context documents - never invent information
2. Use conversation history for follow-up questions context
3. For deadline queries: Use the Deadline field and compare to today's date
4. For ministry queries: Clearly state the ministry name from context
5. Always cite sources with [Source] links in your answer
6. If multiple tenders match, list them clearly with numbers
7. Include key details: Tender number, Ministry, Deadline when available
8. Be concise but comprehensive

MULTILINGUAL:
- Detect question language and respond in BOTH Arabic and English
- If Arabic question → detailed Arabic answer + brief English summary
- If English question → detailed English answer + brief Arabic summary

Context Documents:
{context}
{conversation_context}

QUALITY RULES:
- If context insufficient or irrelevant: say "لم أجد تفاصيل كافية" / "I need more details."
- If no tenders match query: explain why and suggest alternatives
- Confidence score: 0.9+ for exact matches, 0.7-0.9 for good semantic matches, 0.5-0.7 for weak matches

Return JSON:
{{
 "answer_ar": "إجابة مفصلة بالعربية مع ذكر التفاصيل المهمة",
 "answer_en": "Detailed English answer with important details",
 "citations": [{{"url": "...", "title": "...", "published_at": "..."}}],
 "confidence": 0.85
}}
"""
        
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ]
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=settings.TEMPERATURE,
                max_tokens=settings.MAX_TOKENS_QA,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            
            return {
                "answer_ar": result.get("answer_ar", "لم أجد إجابة"),
                "answer_en": result.get("answer_en", "No answer found"),
                "citations": result.get("citations", []),
                "confidence": result.get("confidence", 0.5)
            }
            
        except Exception as e:
            print(f"Q&A error: {e}")
            return {
                "answer_ar": "حدث خطأ في المعالجة",
                "answer_en": "Processing error occurred",
                "citations": [],
                "confidence": 0.0
            }
    
    def detect_keywords_semantic(self, text: str, keywords: List[str]) -> List[Dict]:
        """
        Use embeddings to detect semantic keyword matches
        
        Args:
            text: Text to search in
            keywords: List of keywords to match
            
        Returns:
            List of matches with scores
        """
        # Generate embeddings
        text_embedding = self.generate_embedding(text)
        
        matches = []
        for keyword in keywords:
            keyword_embedding = self.generate_embedding(keyword)
            
            # Calculate cosine similarity
            similarity = self._cosine_similarity(text_embedding, keyword_embedding)
            
            if similarity > settings.SIMILARITY_THRESHOLD:
                matches.append({
                    "keyword": keyword,
                    "match_type": "semantic",
                    "score": similarity
                })
        
        return matches
    
    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = sum(a * a for a in vec1) ** 0.5
        magnitude2 = sum(b * b for b in vec2) ** 0.5
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        return dot_product / (magnitude1 * magnitude2)
