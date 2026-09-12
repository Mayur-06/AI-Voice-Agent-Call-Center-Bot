import { cn } from "@/lib/utils";

function Toast({ className, ...props }) {
  return (
    <div
      data-slot="toast"
      role="status"
      aria-live="polite"
      className={cn(
        "fixed bottom-4 left-4 z-50 w-full max-w-sm",
        "animate-in fade-in-0 slide-in-from-bottom-2",
        className
      )}
      {...props}
    />
  );
}

function ToastTitle({ className, ...props }) {
  return (
    <div
      data-slot="toast-title"
      className={cn("text-sm font-medium text-white", className)}
      {...props}
    />
  );
}

function ToastDescription({ className, ...props }) {
  return (
    <div
      data-slot="toast-description"
      className={cn("text-xs text-white/80", className)}
      {...props}
    />
  );
}

function ToastClose({ className, onClick, ...props }) {
  return (
    <button
      data-slot="toast-close"
      type="button"
      onClick={onClick}
      aria-label="Dismiss"
      className={cn(
        "absolute top-2 right-2 rounded-md p-1 text-white/70 transition-colors hover:bg-white/10 hover:text-white",
        className
      )}
      {...props}
    >
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <line x1="18" y1="6" x2="6" y2="18" />
        <line x1="6" y1="6" x2="18" y2="18" />
      </svg>
    </button>
  );
}

export { Toast, ToastTitle, ToastDescription, ToastClose };
