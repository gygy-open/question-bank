import type { ClassValue } from "clsx"
import { clsx } from "clsx"
import { twMerge } from "tailwind-merge"
import { formatDistanceToNow } from "date-fns"
import { zhCN } from "date-fns/locale"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatRelativeTime(dateStr: string): string {
  if (!dateStr) return ""
  // 后端返回的是 UTC naive 时间, 补 Z 以正确解析
  const normalized = dateStr.endsWith("Z") ? dateStr : `${dateStr}Z`
  return formatDistanceToNow(new Date(normalized), { addSuffix: true, locale: zhCN })
}

