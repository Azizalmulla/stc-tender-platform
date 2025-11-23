/**
 * Simple toast utility for notifications
 * Can be replaced with a full toast library like sonner or react-hot-toast later
 */

type ToastProps = {
  title: string;
  description?: string;
  variant?: "default" | "destructive";
};

export function useToast() {
  const toast = ({ title, description, variant = "default" }: ToastProps) => {
    // Simple alert for now - can be replaced with a proper toast library
    const message = description ? `${title}\n${description}` : title;
    
    if (variant === "destructive") {
      alert(`❌ ${message}`);
    } else {
      alert(`✅ ${message}`);
    }
  };

  return { toast };
}
