/** GET /setup/status — the two independent first-run stages. */
export interface SetupStatus {
  /** A database is configured (env DB_URL or wizard-written config.json). */
  db_configured: boolean
  /** At least one active superuser exists. */
  admin_initialized: boolean
}
