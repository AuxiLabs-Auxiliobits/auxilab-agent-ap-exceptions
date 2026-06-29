import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

// Severity badges read as ledger stamps: a tinted wash + a hairline border in
// the semantic ink, rather than flat pastel pills. `danger/warning/success`
// map to the overdue / pending / settled exception scale.
const badgeVariants = cva(
  "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-semibold tracking-wide transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-primary text-primary-foreground hover:bg-primary/90",
        secondary:
          "border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80",
        destructive:
          "border-transparent bg-destructive text-destructive-foreground hover:bg-destructive/90",
        outline: "text-foreground",
        success:
          "border-settled/30 bg-settled/12 text-settled",
        warning:
          "border-pending/30 bg-pending/12 text-pending",
        danger:
          "border-overdue/30 bg-overdue/12 text-overdue",
        info:
          "border-ink/20 bg-ink/10 text-ink dark:border-primary/30 dark:bg-primary/10 dark:text-primary",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

export { Badge, badgeVariants }
