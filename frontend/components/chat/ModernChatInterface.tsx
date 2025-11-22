"use client";

import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { ArrowUp, User, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useLanguage } from "@/contexts/LanguageContext";
import Image from "next/image";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

export function ModernChatInterface() {
  const { t, language } = useLanguage();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "1",
      role: "assistant",
      content: t(
        "Hello! I'm your AI agent for government tenders. How can I help you today?",
        "مرحباً! أنا الوكيل الذكي للمناقصات الحكومية. كيف يمكنني مساعدتك اليوم؟"
      ),
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Load session ID and conversation history from localStorage on mount
  useEffect(() => {
    const loadConversation = async () => {
      const storedSessionId = localStorage.getItem('chat_session_id');
      if (storedSessionId) {
        setSessionId(storedSessionId);
        
        // Load conversation history from backend
        try {
          const response = await fetch(
            `${process.env.NEXT_PUBLIC_API_URL}/api/chat/conversations/${storedSessionId}`
          );
          
          if (response.ok) {
            const data = await response.json();
            
            // Map backend messages to frontend Message format
            const loadedMessages: Message[] = data.messages.map((msg: any) => ({
              id: msg.timestamp, // Use timestamp as unique ID
              role: msg.role,
              content: msg.content,
              timestamp: new Date(msg.timestamp),
            }));
            
            // Set messages if we have history
            if (loadedMessages.length > 0) {
              setMessages(loadedMessages);
            }
          }
        } catch (error) {
          console.error('Failed to load conversation history:', error);
          // Keep default welcome message if loading fails
        }
      }
    };
    
    loadConversation();
  }, []);

  // Auto-scroll to bottom when new message
  useEffect(() => {
    if (scrollAreaRef.current) {
      const scrollContainer = scrollAreaRef.current.querySelector('[data-radix-scroll-area-viewport]');
      if (scrollContainer) {
        scrollContainer.scrollTop = scrollContainer.scrollHeight;
      }
    }
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: input.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    const questionText = input.trim();
    setInput("");
    setIsLoading(true);

    try {
      // Call chat API with session ID (backend handles history)
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/chat/ask`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          question: questionText,
          session_id: sessionId,  // Send current session ID (or null for new)
          lang: language,
          limit: 5,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to get response');
      }

      const data = await response.json();
      
      // Save session ID from response
      if (data.session_id) {
        setSessionId(data.session_id);
        localStorage.setItem('chat_session_id', data.session_id);
      }
      
      // Use response based on current language
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: language === 'ar' ? data.answer_ar : data.answer_en,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      console.error("Error:", error);
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: t(
          "Sorry, I encountered an error. Please try again.",
          "عذراً، حدث خطأ. يرجى المحاولة مرة أخرى."
        ),
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-5rem)] w-full max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-4 p-6 border-b">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-white shadow-sm">
          <Image
            src="/stc-logo.png"
            alt="STC Logo"
            width={32}
            height={32}
            className="object-contain"
          />
        </div>
        <div className="flex-1">
          <h2 className="text-2xl font-bold">{t("Agent", "الوكيل")}</h2>
          <p className="text-sm text-muted-foreground">
            {t(
              "Ask me anything about government tenders",
              "اسأل عن أي مناقصة وسأساعدك في العثور على المعلومات"
            )}
          </p>
        </div>
        <Badge variant="secondary" className="gap-1">
          <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
          {t("Online", "متصل")}
        </Badge>
      </div>

      {/* Messages */}
      <ScrollArea className="flex-1 p-6" ref={scrollAreaRef}>
        <div className="space-y-6">
          {messages.map((message) => (
            <div
              key={message.id}
              className={cn(
                "flex gap-3 items-start",
                message.role === "user" && "flex-row-reverse"
              )}
            >
              {/* Avatar */}
              <Avatar className={cn(
                "h-10 w-10",
                message.role === "assistant" && "bg-white shadow-sm"
              )}>
                <AvatarFallback>
                  {message.role === "assistant" ? (
                    <Image
                      src="/stc-logo.png"
                      alt="STC"
                      width={24}
                      height={24}
                      className="object-contain"
                    />
                  ) : (
                    <User className="h-5 w-5" />
                  )}
                </AvatarFallback>
              </Avatar>

              {/* Message bubble */}
              <div
                className={cn(
                  "flex flex-col gap-1 max-w-[80%]",
                  message.role === "user" && "items-end"
                )}
              >
                <Card
                  className={cn(
                    "px-4 py-3",
                    message.role === "assistant"
                      ? "bg-muted border-border"
                      : "bg-primary text-primary-foreground border-primary"
                  )}
                >
                  <p className="text-sm leading-relaxed whitespace-pre-wrap">
                    {message.content}
                  </p>
                </Card>
                <span className="text-xs text-muted-foreground px-2">
                  {message.timestamp.toLocaleTimeString(language === "ar" ? "ar-KW" : "en-US", {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              </div>
            </div>
          ))}

          {/* Loading indicator */}
          {isLoading && (
            <div className="flex gap-3 items-start">
              <Avatar className="h-10 w-10 bg-white shadow-sm">
                <AvatarFallback>
                  <Image
                    src="/stc-logo.png"
                    alt="STC"
                    width={24}
                    height={24}
                    className="object-contain"
                  />
                </AvatarFallback>
              </Avatar>
              <Card className="px-4 py-3 bg-muted">
                <div className="flex gap-1">
                  <div className="h-2 w-2 rounded-full bg-primary/60 animate-bounce" />
                  <div className="h-2 w-2 rounded-full bg-primary/60 animate-bounce [animation-delay:0.2s]" />
                  <div className="h-2 w-2 rounded-full bg-primary/60 animate-bounce [animation-delay:0.4s]" />
                </div>
              </Card>
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Input Area */}
      <div className="border-t bg-background p-4">
        <div className="flex items-center gap-3 max-w-4xl mx-auto">
          <Input
            ref={inputRef}
            placeholder={t(
              "Ask me anything about tenders...",
              "اسأل عن أي مناقصة..."
            )}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            disabled={isLoading}
            className="h-14 px-6 rounded-full text-base shadow-sm"
          />
          
          <Button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            size="icon"
            className="h-14 w-14 rounded-full shadow-lg"
          >
            {isLoading ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : (
              <ArrowUp className="h-5 w-5" />
            )}
          </Button>
        </div>

        {/* Quick suggestions */}
        <div className="flex flex-wrap gap-2 mt-3 max-w-4xl mx-auto justify-center">
          <Badge variant="outline" className="cursor-pointer hover:bg-primary/5 rounded-full">
            {t("Latest Tenders", "أحدث المناقصات")}
          </Badge>
          <Badge variant="outline" className="cursor-pointer hover:bg-primary/5 rounded-full">
            {t("Electricity Tenders", "مناقصات الكهرباء")}
          </Badge>
          <Badge variant="outline" className="cursor-pointer hover:bg-primary/5 rounded-full">
            {t("Application Requirements", "شروط التقديم")}
          </Badge>
        </div>
      </div>
    </div>
  );
}
