"use client";

import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Send, Bot, User, Loader2, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

export function ModernChatInterface() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "1",
      role: "assistant",
      content: "مرحباً! أنا مساعدك الذكي للمناقصات الحكومية. كيف يمكنني مساعدتك اليوم؟",
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

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
    setInput("");
    setIsLoading(true);

    try {
      // TODO: Replace with actual API call
      await new Promise((resolve) => setTimeout(resolve, 1500));
      
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: "هذا مثال على الرد. سيتم ربطه بالـ API قريباً!",
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      console.error("Error:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-5rem)] w-full max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3 p-6 border-b bg-gradient-to-r from-primary/5 to-primary/10">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
          <Sparkles className="h-6 w-6 text-primary" />
        </div>
        <div className="flex-1">
          <h2 className="text-2xl font-bold">المساعد الذكي</h2>
          <p className="text-sm text-muted-foreground">
            اسأل عن أي مناقصة وسأساعدك في العثور على المعلومات
          </p>
        </div>
        <Badge variant="secondary" className="gap-1">
          <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
          متصل
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
                message.role === "assistant" && "bg-primary/10"
              )}>
                <AvatarFallback>
                  {message.role === "assistant" ? (
                    <Bot className="h-5 w-5 text-primary" />
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
                  {message.timestamp.toLocaleTimeString("ar-KW", {
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
              <Avatar className="h-10 w-10 bg-primary/10">
                <AvatarFallback>
                  <Bot className="h-5 w-5 text-primary" />
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
        <div className="flex items-end gap-2 max-w-4xl mx-auto">
          <div className="relative flex-1">
            <Textarea
              ref={textareaRef}
              placeholder="اكتب سؤالك هنا... (اضغط Enter للإرسال)"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={handleKeyPress}
              disabled={isLoading}
              className="min-h-[60px] max-h-32 resize-none pr-4 pl-12 py-4 text-base"
              dir="rtl"
            />
            <div className="absolute left-3 bottom-4 text-xs text-muted-foreground">
              Shift + Enter للسطر الجديد
            </div>
          </div>
          
          <Button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            size="lg"
            className="h-[60px] px-6 gap-2"
          >
            {isLoading ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : (
              <>
                <Send className="h-5 w-5" />
                <span>إرسال</span>
              </>
            )}
          </Button>
        </div>

        {/* Quick suggestions */}
        <div className="flex flex-wrap gap-2 mt-3 max-w-4xl mx-auto">
          <Badge variant="outline" className="cursor-pointer hover:bg-primary/5">
            أحدث المناقصات
          </Badge>
          <Badge variant="outline" className="cursor-pointer hover:bg-primary/5">
            مناقصات الكهرباء
          </Badge>
          <Badge variant="outline" className="cursor-pointer hover:bg-primary/5">
            شروط التقديم
          </Badge>
        </div>
      </div>
    </div>
  );
}
