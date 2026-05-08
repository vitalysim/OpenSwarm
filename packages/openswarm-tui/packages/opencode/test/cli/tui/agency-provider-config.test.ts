import { afterEach, describe, expect, mock, test } from "bun:test"
import { AgencySwarmAdapter } from "../../../src/agency-swarm/adapter"
import {
  buildAgencyProviderConfig,
  updateAgencyProviderConfig,
} from "../../../src/cli/cmd/tui/util/agency-provider-config"

const originalConfigContent = process.env.OPENCODE_CONFIG_CONTENT

function restoreEnvConfigContent() {
  if (originalConfigContent === undefined) {
    delete process.env.OPENCODE_CONFIG_CONTENT
    return
  }
  process.env.OPENCODE_CONFIG_CONTENT = originalConfigContent
}

describe("agency provider config updates", () => {
  afterEach(() => {
    mock.restore()
    restoreEnvConfigContent()
  })

  test("preserves non-agency config keys while replacing provider options", () => {
    const config = buildAgencyProviderConfig(
      {
        baseURL: "http://127.0.0.1:8000",
        agency: "security-research",
      },
      {
        $schema: "https://opencode.ai/config.json",
        theme: "system",
        provider: {
          other: {
            name: "Other Provider",
          },
          [AgencySwarmAdapter.PROVIDER_ID]: {
            name: "Agency Swarm",
            options: {
              baseURL: "http://127.0.0.1:7000",
              agency: "open-swarm",
            },
          },
        },
      },
    )

    expect(config.theme).toBe("system")
    expect((config.provider as any).other.name).toBe("Other Provider")
    expect((config.provider as any)[AgencySwarmAdapter.PROVIDER_ID].name).toBe("Agency Swarm")
    expect((config.provider as any)[AgencySwarmAdapter.PROVIDER_ID].options).toEqual({
      baseURL: "http://127.0.0.1:8000",
      agency: "security-research",
    })
  })

  test("updates env-backed launcher config before reloading sync state", async () => {
    process.env.OPENCODE_CONFIG_CONTENT = JSON.stringify({
      $schema: "https://opencode.ai/config.json",
      theme: "system",
      model: `${AgencySwarmAdapter.PROVIDER_ID}/${AgencySwarmAdapter.DEFAULT_MODEL_ID}`,
      provider: {
        [AgencySwarmAdapter.PROVIDER_ID]: {
          name: "Agency Swarm",
          options: {
            baseURL: "http://127.0.0.1:7000",
            agency: "open-swarm",
            workingDirectory: "/tmp/project",
          },
        },
      },
    })

    const update = mock(async (_input: unknown, _options?: unknown) => ({ data: undefined }))
    const dispose = mock(async () => undefined)
    const bootstrap = mock(async () => undefined)

    await updateAgencyProviderConfig({
      client: {
        global: {
          config: {
            update,
          },
        },
        instance: {
          dispose,
        },
      },
      sync: {
        bootstrap,
      },
      nextOptions: {
        baseURL: "http://127.0.0.1:8000",
        agency: "security-research",
        workingDirectory: "/tmp/project",
      },
    })

    const envConfig = JSON.parse(process.env.OPENCODE_CONFIG_CONTENT)
    expect(envConfig.theme).toBe("system")
    expect(envConfig.provider[AgencySwarmAdapter.PROVIDER_ID].name).toBe("Agency Swarm")
    expect(envConfig.provider[AgencySwarmAdapter.PROVIDER_ID].options.agency).toBe("security-research")
    expect(update).toHaveBeenCalledTimes(1)
    expect(dispose).toHaveBeenCalledTimes(1)
    expect(bootstrap).toHaveBeenCalledTimes(1)
  })

  test("updates worker runtime config content when a TUI transport is available", async () => {
    process.env.OPENCODE_CONFIG_CONTENT = JSON.stringify({
      model: `${AgencySwarmAdapter.PROVIDER_ID}/${AgencySwarmAdapter.DEFAULT_MODEL_ID}`,
      provider: {
        [AgencySwarmAdapter.PROVIDER_ID]: {
          name: "Agency Swarm",
          options: {
            baseURL: "http://127.0.0.1:7000",
            agency: "open-swarm",
          },
        },
      },
    })

    const update = mock(async (_input: unknown, _options?: unknown) => ({ data: undefined }))
    const dispose = mock(async () => undefined)
    const bootstrap = mock(async () => undefined)
    const runtimeFetch = mock(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response("true"))

    await updateAgencyProviderConfig({
      client: {
        global: {
          config: {
            update,
          },
        },
        instance: {
          dispose,
        },
      },
      sync: {
        bootstrap,
      },
      fetch: runtimeFetch as unknown as typeof fetch,
      url: "http://opencode.internal",
      nextOptions: {
        baseURL: "http://127.0.0.1:8000",
        agency: "security-research",
      },
    })

    expect(runtimeFetch).toHaveBeenCalledTimes(1)
    expect(String(runtimeFetch.mock.calls[0]?.[0])).toBe("http://opencode.internal/global/config/content")
    expect(dispose).not.toHaveBeenCalled()
    expect(bootstrap).toHaveBeenCalledTimes(1)
  })

  test("rolls back env-backed launcher config when persistent update fails", async () => {
    const previousConfig = JSON.stringify({
      model: `${AgencySwarmAdapter.PROVIDER_ID}/${AgencySwarmAdapter.DEFAULT_MODEL_ID}`,
      provider: {
        [AgencySwarmAdapter.PROVIDER_ID]: {
          name: "Agency Swarm",
          options: {
            baseURL: "http://127.0.0.1:7000",
            agency: "open-swarm",
          },
        },
      },
    })
    process.env.OPENCODE_CONFIG_CONTENT = previousConfig

    const update = mock(async () => {
      throw new Error("config update failed")
    })
    const dispose = mock(async () => undefined)
    const bootstrap = mock(async () => undefined)

    let error: unknown
    try {
      await updateAgencyProviderConfig({
        client: {
          global: {
            config: {
              update,
            },
          },
          instance: {
            dispose,
          },
        },
        sync: {
          bootstrap,
        },
        nextOptions: {
          baseURL: "http://127.0.0.1:8000",
          agency: "security-research",
        },
      })
    } catch (caught) {
      error = caught
    }

    expect(error).toBeInstanceOf(Error)
    expect(process.env.OPENCODE_CONFIG_CONTENT).toBe(previousConfig)
    expect(dispose).not.toHaveBeenCalled()
    expect(bootstrap).not.toHaveBeenCalled()
  })
})
