import { AgencySwarmAdapter } from "@/agency-swarm/adapter"

type ConfigRecord = Record<string, unknown>

type ConfigUpdateClient = {
  global: {
    dispose?: () => Promise<unknown>
    config: {
      update: (
        input: { config: ConfigRecord },
        options?: { throwOnError?: boolean },
      ) => Promise<unknown>
    }
  }
  instance: {
    dispose: () => Promise<unknown>
  }
}

type SyncBootstrap = {
  bootstrap: (input?: { fatal?: boolean }) => Promise<unknown>
}

function isRecord(value: unknown): value is ConfigRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

function readEnvConfigContent() {
  const raw = process.env.OPENCODE_CONFIG_CONTENT
  if (!raw) return undefined

  try {
    const parsed = JSON.parse(raw)
    if (!isRecord(parsed)) return undefined
    return { raw, parsed }
  } catch {
    return undefined
  }
}

export function buildAgencyProviderConfig(nextOptions: ConfigRecord, baseConfig?: ConfigRecord): ConfigRecord {
  const provider = isRecord(baseConfig?.provider) ? baseConfig.provider : {}
  const currentProvider = isRecord(provider[AgencySwarmAdapter.PROVIDER_ID])
    ? provider[AgencySwarmAdapter.PROVIDER_ID]
    : {}

  return {
    ...(baseConfig ?? {}),
    model: `${AgencySwarmAdapter.PROVIDER_ID}/${AgencySwarmAdapter.DEFAULT_MODEL_ID}`,
    provider: {
      ...provider,
      [AgencySwarmAdapter.PROVIDER_ID]: {
        ...currentProvider,
        name: typeof currentProvider.name === "string" ? currentProvider.name : "agency-swarm",
        options: nextOptions,
      },
    },
  }
}

export async function updateAgencyProviderConfig(input: {
  client: ConfigUpdateClient
  sync: SyncBootstrap
  nextOptions: ConfigRecord
  fetch?: typeof fetch
  url?: string
}) {
  const envConfig = readEnvConfigContent()
  const nextConfig = buildAgencyProviderConfig(input.nextOptions, envConfig?.parsed)
  let didPatchEnv = false
  let didUpdateConfig = false

  if (envConfig) {
    process.env.OPENCODE_CONFIG_CONTENT = JSON.stringify(nextConfig)
    didPatchEnv = true
  }

  try {
    await input.client.global.config.update({ config: nextConfig }, { throwOnError: true })
    didUpdateConfig = true
    if (input.fetch && input.url) {
      await updateRuntimeConfigContent({
        fetch: input.fetch,
        url: input.url,
        config: nextConfig,
      })
    } else if (input.client.global.dispose) {
      await input.client.global.dispose()
    } else {
      await input.client.instance.dispose()
    }
    await input.sync.bootstrap()
  } catch (error) {
    if (didPatchEnv && !didUpdateConfig) {
      process.env.OPENCODE_CONFIG_CONTENT = envConfig?.raw
    }
    throw error
  }
}

async function updateRuntimeConfigContent(input: {
  fetch: typeof fetch
  url: string
  config: ConfigRecord
}) {
  const endpoint = new URL("/global/config/content", input.url)
  const response = await input.fetch(endpoint, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(input.config),
  })
  if (!response.ok) {
    throw new Error(`Failed to update runtime config content: ${response.status} ${response.statusText}`)
  }
}
