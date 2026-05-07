import { AgencySwarmAdapter } from "@/agency-swarm/adapter"
import { createMemo, createResource, createSignal } from "solid-js"
import { createSimpleContext } from "./helper"
import { useLocal } from "./local"
import { useSync } from "./sync"
import { isAgencySwarmFrameworkMode } from "../session-error"
import { readAgencyProviderOptions } from "../util/agency-target"

type ModelResource = {
  routeAgency: string
  state?: AgencySwarmAdapter.OpenSwarmModelState
}

export const { use: useOpenSwarmModels, provider: OpenSwarmModelsProvider } = createSimpleContext({
  name: "OpenSwarmModels",
  init: () => {
    const local = useLocal()
    const sync = useSync()

    const frameworkMode = createMemo(() =>
      isAgencySwarmFrameworkMode({
        currentProviderID: local.model.current()?.providerID,
        configuredModel: sync.data.config.model,
        agentModel: local.agent.current()?.model,
      }),
    )

    const providerOptions = createMemo(() =>
      readAgencyProviderOptions({
        configuredProvider: sync.data.config.provider?.[AgencySwarmAdapter.PROVIDER_ID],
        connectedProvider: sync.data.provider.find((item) => item.id === AgencySwarmAdapter.PROVIDER_ID),
      }),
    )
    const [lastError, setLastError] = createSignal<unknown>()

    const request = createMemo(() => {
      if (!frameworkMode()) return undefined
      const options = providerOptions()
      return {
        baseURL: options.baseURL,
        token: options.token,
        timeoutMs: options.discoveryTimeoutMs,
        agency: options.agency,
      }
    })

    const [resource, { refetch, mutate }] = createResource(request, async (input): Promise<ModelResource> => {
      let routeAgency = input.agency
      if (!routeAgency) {
        const discovered = await AgencySwarmAdapter.discover({
          baseURL: input.baseURL,
          token: input.token,
          timeoutMs: input.timeoutMs,
        })
        routeAgency = discovered.agencies[0]?.id
      }
      if (!routeAgency) {
        setLastError(new Error("No agency-swarm agency is available"))
        return {
          routeAgency: "",
        }
      }

      try {
        const state = await AgencySwarmAdapter.getOpenSwarmModels({
          baseURL: input.baseURL,
          agency: routeAgency,
          token: input.token,
          timeoutMs: input.timeoutMs,
        })
        setLastError(undefined)
        return {
          routeAgency,
          state,
        }
      } catch (error) {
        setLastError(error)
        return {
          routeAgency,
        }
      }
    })

    const state = createMemo(() => resource()?.state)

    function agentModel(agentIDOrName?: string | null) {
      const modelState = state()
      if (!modelState) return undefined
      if (agentIDOrName) {
        const folded = agentIDOrName.toLowerCase()
        const direct = modelState.agents.find(
          (item) => item.id === agentIDOrName || item.name === agentIDOrName || item.name.toLowerCase() === folded,
        )
        if (direct) return direct
      }
      return modelState.agents.find((item) => item.isEntryPoint) ?? modelState.agents[0]
    }

    const currentAgentModel = createMemo(() => agentModel(providerOptions().recipientAgent))

    async function setAgentModel(agent: string, model: string) {
      const input = request()
      if (!input) throw new Error("OpenSwarm model switching is only available in agency-swarm mode")
      const routeAgency = resource()?.routeAgency ?? input.agency
      if (!routeAgency) throw new Error("Select a swarm before changing agent models")

      const next = await AgencySwarmAdapter.setOpenSwarmAgentModel({
        baseURL: input.baseURL,
        agency: routeAgency,
        agent,
        model,
        token: input.token,
        timeoutMs: input.timeoutMs,
      })
      mutate({
        routeAgency,
        state: next,
      })
    }

    return {
      frameworkMode,
      loading: createMemo(() => resource.loading),
      error: createMemo(() => lastError()),
      state,
      agentModel,
      currentAgentModel,
      refresh: refetch,
      setAgentModel,
    }
  },
})
