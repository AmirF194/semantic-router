import type { BuiltInModelCatalog } from '../types/modelCatalog'

export class ModelCatalogApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ModelCatalogApiError'
    this.status = status
  }
}

function isBuiltInModelCatalog(value: unknown): value is BuiltInModelCatalog {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<BuiltInModelCatalog>
  if (!Array.isArray(candidate.catalogs) || !Array.isArray(candidate.models)) return false
  if (candidate.catalogs.length === 0 || candidate.models.length === 0) return false
  return (
    candidate.catalogs.every(
      (catalog) =>
        catalog &&
        typeof catalog.catalog_version === 'string' &&
        (catalog.channel === 'latest' || catalog.channel === 'release') &&
        typeof catalog.default_model === 'string' &&
        Array.isArray(catalog.enabled_models),
    ) &&
    candidate.models.every(
      (model) =>
        model &&
        typeof model.id === 'string' &&
        typeof model.display_name === 'string' &&
        typeof model.compatible === 'boolean' &&
        Array.isArray(model.traits) &&
        Array.isArray(model.roles),
    )
  )
}

export async function getBuiltInModelCatalog(signal?: AbortSignal): Promise<BuiltInModelCatalog> {
  const response = await fetch('/api/models/catalog', { signal })
  if (!response.ok) {
    throw new ModelCatalogApiError(
      `Built-in model catalog is unavailable (HTTP ${response.status}).`,
      response.status,
    )
  }
  const payload: unknown = await response.json()
  if (!isBuiltInModelCatalog(payload)) {
    throw new ModelCatalogApiError('Built-in model catalog returned an invalid contract.', 502)
  }
  return payload
}
