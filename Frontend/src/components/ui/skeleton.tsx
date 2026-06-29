import { cn } from '@/lib/utils';

/**
 * A neutral, pulsing placeholder shown while real content is loading. Compose
 * several together to mirror the shape of the content being fetched (rows,
 * cards, chart blocks) so the layout doesn't jump when data arrives.
 */
function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('animate-pulse rounded-md bg-muted', className)}
      aria-hidden="true"
      {...props}
    />
  );
}

export { Skeleton };
