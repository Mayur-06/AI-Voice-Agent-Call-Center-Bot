import * as React from "react"
import { Progress as ProgressPrimitive } from "@base-ui/react/progress"
import { cn } from "cn"

function Progress({
  className,
  value,
  max = 100,
  ...props
}) {
  const boundedValue = Math.min(Math.max(value ?? 0, 0), max)

  return (
    <ProgressPrimitive.Root
      data-slot="progress"
      value={boundedValue}
      max={max}
      className={cn(
        "relative h-2 w-full overflow-hidden rounded-full bg-[rgba(3,25,30,0.08)]",
        className
      )}
      {...props}
    >
      <ProgressPrimitive.Indicator
        data-slot="progress-indicator"
        className="h-full w-full flex-1 rounded-full bg-[var(--ink-black)] transition-all duration-300"
        style={{
          transform: `translateX(-${100 - (boundedValue / max) * 100}%)`,
        }}
      />
    </ProgressPrimitive.Root>
  )
}

export { Progress }
