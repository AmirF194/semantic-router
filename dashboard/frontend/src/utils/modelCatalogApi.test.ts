import { afterEach, describe, expect, it, vi } from 'vitest'

import { getBuiltInModelCatalog, ModelCatalogApiError } from './modelCatalogApi'

afterEach(() => {
  vi.unstubAllGlobals()
})

const validCatalog = {
  catalogs: [
    {
      catalog_version: 'latest',
      channel: 'latest',
      default_model: 'vllm-sr/chorus-v1',
      enabled_models: ['vllm-sr/chorus-v1'],
    },
  ],
  models: [
    {
      id: 'vllm-sr/chorus-v1',
      display_name: 'Chorus V1',
      compatible: true,
      traits: ['balanced'],
      roles: [],
    },
  ],
}

describe('built-in model catalog API', () => {
  it('loads the authenticated read-only catalog endpoint with abort support', async () => {
    const controller = new AbortController()
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(validCatalog), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getBuiltInModelCatalog(controller.signal)).resolves.toEqual(validCatalog)
    expect(fetchMock).toHaveBeenCalledWith('/api/models/catalog', { signal: controller.signal })
  })

  it('fails closed when the server omits version or model inventory', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () => new Response(JSON.stringify({ catalogs: [], models: [] }), { status: 200 }),
      ),
    )

    await expect(getBuiltInModelCatalog()).rejects.toMatchObject({
      name: 'ModelCatalogApiError',
      status: 502,
    })
  })

  it('does not echo an arbitrary backend error body', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response('private backend command and credentials', {
            status: 503,
            statusText: 'Service Unavailable',
          }),
      ),
    )

    const request = getBuiltInModelCatalog()
    await expect(request).rejects.toBeInstanceOf(ModelCatalogApiError)
    await expect(request).rejects.not.toThrow(/private backend|credentials/)
  })
})
