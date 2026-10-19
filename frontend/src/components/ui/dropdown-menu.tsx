import * as DropdownPrimitive from '@radix-ui/react-dropdown-menu'
import * as React from 'react'
import { cn } from '@/lib/utils'

export const DropdownMenu = DropdownPrimitive.Root
export const DropdownMenuTrigger = DropdownPrimitive.Trigger

export const DropdownMenuContent = ({
  className,
  sideOffset = 6,
  ...props
}: React.ComponentPropsWithoutRef<typeof DropdownPrimitive.Content>) => (
  <DropdownPrimitive.Portal>
    <DropdownPrimitive.Content
      sideOffset={sideOffset}
      className={cn('surface z-50 min-w-48 animate-fade-in p-1.5 shadow-lg', className)}
      {...props}
    />
  </DropdownPrimitive.Portal>
)
export const DropdownMenuItem = ({ className, ...props }: React.ComponentPropsWithoutRef<typeof DropdownPrimitive.Item>) => (
  <DropdownPrimitive.Item
    className={cn(
      'flex cursor-pointer select-none items-center gap-2 rounded-md px-2.5 py-2 text-sm outline-none transition-colors focus:bg-muted data-[disabled]:pointer-events-none data-[disabled]:opacity-50',
      className,
    )}
    {...props}
  />
)
export const DropdownMenuLabel = ({ className, ...props }: React.ComponentPropsWithoutRef<typeof DropdownPrimitive.Label>) => (
  <DropdownPrimitive.Label className={cn('px-2.5 py-1.5 text-xs text-muted-foreground', className)} {...props} />
)
export const DropdownMenuSeparator = ({ className, ...props }: React.ComponentPropsWithoutRef<typeof DropdownPrimitive.Separator>) => (
  <DropdownPrimitive.Separator className={cn('-mx-1.5 my-1.5 h-px bg-border', className)} {...props} />
)
