export type QueryValue = string | number | boolean | undefined | null

export function buildLibraryQuery(values: Record<string, QueryValue>): Record<string, string | number | boolean> {
  return Object.fromEntries(
    Object.entries(values).filter(([, value]) => value !== undefined && value !== null && value !== '' && value !== '0'),
  ) as Record<string, string | number | boolean>
}