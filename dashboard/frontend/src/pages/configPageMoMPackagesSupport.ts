import type {
  RecipeActivationState,
  RecipeDescriptor,
  RecipePackageErrorCode,
  RecipePackageImportRequest,
  RecipePackageWarning,
} from '../types/recipe'
import { RecipeApiError } from '../utils/recipeApi'

export const RECIPE_PACKAGE_PAGE_SIZE = 25

export type ManagedRecipeProtectionState = Extract<
  RecipeActivationState,
  'active' | 'recovering' | 'inconsistent'
>

export function resolveManagedRecipeProtection(
  descriptor: RecipeDescriptor | null,
): ManagedRecipeProtectionState | null {
  if (!descriptor?.managed) return null
  const state = descriptor.activation_state
  if (state === 'active') return descriptor.active_recipe_digest ? state : null
  return state === 'recovering' || state === 'inconsistent' ? state : null
}

export type RecipePackageCapabilityBlocker =
  | 'server_readonly'
  | 'recipe_store_readonly'
  | 'runtime_config_readonly'
  | 'permission_required'
  | null

export interface RecipePackageCapabilities {
  canImport: boolean
  canActivate: boolean
  importBlocker: RecipePackageCapabilityBlocker
  activationBlocker: RecipePackageCapabilityBlocker
}

export function resolveRecipePackageCapabilities(
  serverReadonly: boolean,
  runtimeConfigWritable: boolean,
  recipeStoreWritable: boolean,
  hasWritePermission: boolean,
  hasDeployPermission: boolean,
): RecipePackageCapabilities {
  const importBlocker: RecipePackageCapabilityBlocker = serverReadonly
    ? 'server_readonly'
    : !recipeStoreWritable
      ? 'recipe_store_readonly'
      : !hasWritePermission
        ? 'permission_required'
        : null
  const activationBlocker: RecipePackageCapabilityBlocker = serverReadonly
    ? 'server_readonly'
    : !runtimeConfigWritable
      ? 'runtime_config_readonly'
      : !hasDeployPermission
        ? 'permission_required'
        : null
  return {
    canImport: importBlocker === null,
    canActivate: activationBlocker === null,
    importBlocker,
    activationBlocker,
  }
}

export type RecipePackageOperation =
  | 'load'
  | 'import'
  | 'activate'
  | 'deactivate'
  | 'activate-preview'
  | 'deactivate-preview'

export interface RecipePackageErrorPresentation {
  title: string
  message: string
  code?: RecipePackageErrorCode
}

export interface RecipePackageWarningPresentation {
  code: string
  path: string
  message: string
}

export function presentRecipePackageWarning(
  warning: RecipePackageWarning,
): RecipePackageWarningPresentation {
  if (warning.code === 'environment_binding_required') {
    const environmentName = warning.message.match(
      /environment variable\s+([A-Za-z_][A-Za-z0-9_]*)/i,
    )?.[1]
    return {
      code: warning.code,
      path: warning.path,
      message: environmentName
        ? `Requires environment variable ${environmentName} to be authorized before activation.`
        : 'Requires an authorized environment variable before activation.',
    }
  }
  return {
    code: warning.code,
    path: warning.path,
    message: 'Review this package warning before activation.',
  }
}

const RUNTIME_CONFIG_MUTATION_ERRORS: Record<string, string> = {
  managed_recipe_active:
    'This runtime configuration is controlled by a managed Recipe. Use package activation, repair, or Restore source instead.',
  deploy_in_progress: 'Another runtime configuration operation is in progress. Try again shortly.',
  config_coordination_failed:
    'Runtime configuration coordination is unavailable. Refresh managed Recipe state before retrying.',
  runtime_config_readonly:
    'The runtime configuration mount is read-only. Package import may remain available, but runtime changes are disabled.',
  readonly_mode: 'This Dashboard is read-only. Configuration editing is disabled.',
}

export function presentRuntimeConfigMutationError(code: string | undefined): string | undefined {
  return code ? RUNTIME_CONFIG_MUTATION_ERRORS[code] : undefined
}

export type RecipePackageImportValidation =
  | { ok: true; request: RecipePackageImportRequest }
  | { ok: false; field: 'url' | 'sha256'; message: string }

export function validateRecipePackageImport(
  rawURL: string,
  rawExpectedSHA256: string,
): RecipePackageImportValidation {
  const value = rawURL.trim()
  if (!value) {
    return { ok: false, field: 'url', message: 'Enter a public HTTPS Recipe ZIP URL.' }
  }

  let url: URL
  try {
    url = new URL(value)
  } catch {
    return { ok: false, field: 'url', message: 'Enter a valid HTTPS URL.' }
  }
  if (url.protocol !== 'https:' || !url.hostname) {
    return { ok: false, field: 'url', message: 'Recipe packages must use a public HTTPS URL.' }
  }
  if (url.username || url.password) {
    return {
      ok: false,
      field: 'url',
      message: 'Use a public URL without embedded credentials.',
    }
  }
  url.hash = ''

  const checksum = rawExpectedSHA256.trim().replace(/^sha256:/i, '')
  if (checksum && !/^[a-f0-9]{64}$/i.test(checksum)) {
    return {
      ok: false,
      field: 'sha256',
      message: 'SHA-256 must contain exactly 64 hexadecimal characters.',
    }
  }

  return {
    ok: true,
    request: {
      url: url.toString(),
      ...(checksum ? { expected_archive_sha256: `sha256:${checksum.toLowerCase()}` } : {}),
    },
  }
}

export function formatPackageInstalledAt(value: string): string {
  const timestamp = Date.parse(value)
  if (!Number.isFinite(timestamp)) return 'Install time unavailable'
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(timestamp)
}

const PACKAGE_ERRORS: Partial<Record<RecipePackageErrorCode, RecipePackageErrorPresentation>> = {
  invalid_request: {
    title: 'Package request is invalid',
    message: 'Review the package URL and optional SHA-256 value, then try again.',
  },
  invalid_url: {
    title: 'Package URL is invalid',
    message: 'Use a public HTTPS URL that points to a Recipe ZIP archive.',
  },
  insecure_url: {
    title: 'Secure package URL required',
    message: 'Recipe packages can only be downloaded over HTTPS.',
  },
  source_forbidden: {
    title: 'Package source was blocked',
    message: 'The URL does not resolve to a public package source allowed by the server.',
  },
  download_failed: {
    title: 'Package download failed',
    message: 'Check that the HTTPS archive is public, available, and then try again.',
  },
  download_too_large: {
    title: 'Package download was rejected',
    message: 'The archive exceeds the server package-size limit.',
  },
  archive_digest_mismatch: {
    title: 'Archive integrity check failed',
    message: 'The downloaded archive does not match the pinned SHA-256 digest.',
  },
  invalid_archive: {
    title: 'Archive security check failed',
    message: 'The ZIP archive is malformed or violates package extraction safety rules.',
  },
  invalid_recipe: {
    title: 'Recipe schema validation failed',
    message: 'The archive does not contain a conformant managed Recipe package.',
  },
  package_version_conflict: {
    title: 'Package version conflict',
    message: 'This Recipe ID and version are already installed with different content.',
  },
  package_not_found: {
    title: 'Installed package was not found',
    message: 'Refresh installed packages and choose another Recipe to activate.',
  },
  deploy_in_progress: {
    title: 'Another configuration operation is in progress',
    message: 'Wait for the current Router configuration operation to finish, then retry.',
  },
  activation_failed: {
    title: 'Recipe activation failed',
    message: 'The new Router configuration was rejected and the previous Recipe was restored.',
  },
  activation_rollback_failed: {
    title: 'Activation and rollback failed',
    message:
      'The Router could not activate this Recipe or restore the previous configuration. Check Router health before retrying.',
  },
  activation_inconsistent: {
    title: 'Router repair could not start',
    message: 'Refresh activation state, then retry repair with an installed Recipe package.',
  },
  activation_confirmation_required: {
    title: 'Activation plan changed',
    message:
      'Review the current listener, storage, and authentication restart plan before confirming again.',
  },
  environment_binding_required: {
    title: 'Recipe environment binding unavailable',
    message:
      'Authorize and provide the required environment variables when starting the managed stack, then retry activation. The runtime configuration was not changed.',
  },
  activation_incompatible: {
    title: 'Recipe is incompatible with this running stack',
    message:
      'This package requires a different listener or managed-service topology. Start a compatible stack before activating it. The runtime configuration was not changed.',
  },
  managed_storage_isolation_required: {
    title: 'Managed storage needs loopback isolation',
    message:
      'Preserve the existing storage data, recreate the affected managed storage container with loopback-only host port bindings, and retry. No Recipe activation or source restore was started.',
  },
  managed_recipe_active: {
    title: 'Managed Recipe controls this configuration',
    message:
      'Use Recipe package activation, repair, or Restore source instead of an ordinary runtime configuration update.',
  },
  config_coordination_failed: {
    title: 'Runtime configuration coordination failed',
    message: 'Refresh the managed Recipe state before retrying this operation.',
  },
  warnings_not_acknowledged: {
    title: 'Package warnings need acknowledgment',
    message: 'Review the package warnings and confirm activation again.',
  },
  recipe_store_readonly: {
    title: 'Recipe package store is read-only',
    message:
      'Installed packages remain available to inspect, but this server cannot persist a new package import.',
  },
  runtime_config_readonly: {
    title: 'Runtime configuration is read-only',
    message:
      'Package import remains independent, but activation, repair, and source restore require a writable runtime configuration mount.',
  },
  readonly_mode: {
    title: 'Server is read-only',
    message: 'The explicit server-wide read-only policy disables every Recipe package change.',
  },
}

const DEACTIVATION_ERRORS: Partial<Record<RecipePackageErrorCode, RecipePackageErrorPresentation>> =
  {
    activation_incompatible: {
      title: 'Source runtime is incompatible with this running stack',
      message:
        'The preserved source configuration requires a different stack topology. The managed Recipe remains active.',
    },
    activation_failed: {
      title: 'Source runtime restore failed',
      message: 'The source configuration could not be restored. The managed Recipe remains active.',
    },
    activation_rollback_failed: {
      title: 'Source restore and rollback failed',
      message:
        'The Router could not restore the source configuration or return to a consistent managed state. Check Router health before retrying.',
    },
  }

const ACTIVATION_PREVIEW_ERRORS: Partial<
  Record<RecipePackageErrorCode, RecipePackageErrorPresentation>
> = {
  activation_failed: {
    title: 'Activation plan could not be prepared',
    message:
      'The Dashboard could not inspect or prepare the activation plan. Recipe activation was not started.',
  },
}

const DEACTIVATION_PREVIEW_ERRORS: Partial<
  Record<RecipePackageErrorCode, RecipePackageErrorPresentation>
> = {
  activation_failed: {
    title: 'Source restore plan could not be prepared',
    message:
      'The Dashboard could not inspect or prepare the source restore plan. Source restore was not started.',
  },
}

export function presentRecipePackageError(
  reason: unknown,
  operation: RecipePackageOperation,
): RecipePackageErrorPresentation {
  const code = reason instanceof RecipeApiError ? reason.code : undefined
  const known = code
    ? operation === 'deactivate'
      ? DEACTIVATION_ERRORS[code] || PACKAGE_ERRORS[code]
      : operation === 'activate-preview'
        ? ACTIVATION_PREVIEW_ERRORS[code] || PACKAGE_ERRORS[code]
        : operation === 'deactivate-preview'
          ? DEACTIVATION_PREVIEW_ERRORS[code] || DEACTIVATION_ERRORS[code] || PACKAGE_ERRORS[code]
          : PACKAGE_ERRORS[code]
    : undefined
  if (known) return { ...known, code }

  if (operation === 'load') {
    return {
      title: 'Installed packages are unavailable',
      message: 'The Dashboard could not load the installed Recipe package inventory.',
    }
  }
  if (operation === 'activate') {
    return {
      title: 'Recipe activation failed',
      message: 'The Dashboard could not complete the activation request. Refresh before retrying.',
    }
  }
  if (operation === 'activate-preview') {
    return {
      title: 'Activation plan could not be prepared',
      message:
        'The Dashboard could not inspect or prepare the activation plan. Recipe activation was not started.',
    }
  }
  if (operation === 'deactivate-preview') {
    return {
      title: 'Source restore plan could not be prepared',
      message:
        'The Dashboard could not inspect or prepare the source restore plan. Source restore was not started.',
    }
  }
  if (operation === 'deactivate') {
    return {
      title: 'Source runtime restore failed',
      message:
        'The Dashboard could not complete the source restore request. Refresh managed Recipe state before retrying.',
    }
  }
  return {
    title: 'Recipe package import failed',
    message: 'The Dashboard could not complete the package download and installation request.',
  }
}
