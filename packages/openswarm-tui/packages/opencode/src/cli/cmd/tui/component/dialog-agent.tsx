import { AgencySwarmAdapter } from "@/agency-swarm/adapter"
import { displayAgentName } from "@/agent/display"
import { useLocal } from "@tui/context/local"
import { useOpenSwarmModels } from "@tui/context/openswarm-models"
import { useSDK } from "@tui/context/sdk"
import { useSync } from "@tui/context/sync"
import { useDialog } from "@tui/ui/dialog"
import { DialogPrompt } from "@tui/ui/dialog-prompt"
import { DialogSelect, type DialogSelectOption } from "@tui/ui/dialog-select"
import { useToast } from "@tui/ui/toast"
import { createMemo, createResource, createSignal } from "solid-js"
import { DialogAgencySwarmConnect } from "./dialog-provider"
import { isAgencySwarmFrameworkMode } from "../session-error"
import {
  buildAgencyTargetOptions,
  readAgencyProviderOptions,
  resolveAgencyTargetFromPicker,
  resolveAgencyTargetSelection,
} from "../util/agency-target"

type AgentOptionValue =
  | {
      kind: "local"
      agent: string
    }
  | {
      kind: "agency"
      agency: string
    }
  | {
      kind: "recipient"
      agency: string
      recipientAgent: string
    }
  | {
      kind: "connect"
    }
  | {
      kind: "manage_models"
    }

export function DialogAgent() {
  const local = useLocal()
  const sync = useSync()
  const sdk = useSDK()
  const dialog = useDialog()
  const toast = useToast()
  const openSwarmModels = useOpenSwarmModels()

  const currentModel = createMemo(() => local.model.current())
  const agencySwarmEnabled = createMemo(() =>
    isAgencySwarmFrameworkMode({
      currentProviderID: currentModel()?.providerID,
      configuredModel: sync.data.config.model,
      agentModel: local.agent.current()?.model,
    }),
  )

  const providerOptions = createMemo(() => {
    return readAgencyProviderOptions({
      configuredProvider: sync.data.config.provider?.[AgencySwarmAdapter.PROVIDER_ID],
      connectedProvider: sync.data.provider.find((item) => item.id === AgencySwarmAdapter.PROVIDER_ID),
    })
  })

  const discoveryInput = createMemo(() => {
    if (!agencySwarmEnabled()) return undefined
    return {
      baseURL: providerOptions().baseURL,
      token: providerOptions().token,
      timeoutMs: providerOptions().discoveryTimeoutMs,
    }
  })

  const [discovery] = createResource(
    discoveryInput,
    async (input): Promise<{ agencies: AgencySwarmAdapter.AgencyDescriptor[]; error?: string }> => {
      try {
        const result = await AgencySwarmAdapter.discover({
          baseURL: input.baseURL,
          token: input.token,
          timeoutMs: input.timeoutMs,
        })
        return { agencies: result.agencies }
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") throw error
        return {
          agencies: [],
          error: error instanceof Error ? error.message : String(error),
        }
      }
    },
    {
      initialValue: { agencies: [] },
    },
  )

  const options = createMemo<DialogSelectOption<AgentOptionValue>[]>(() => {
    if (!agencySwarmEnabled()) {
      return local.agent.list().map((item) => {
        return {
          value: {
            kind: "local",
            agent: item.name,
          } as AgentOptionValue,
          title: displayAgentName(item.name),
          description: item.native ? "native" : item.description,
        }
      })
    }

    const result: DialogSelectOption<AgentOptionValue>[] = []
    const discovered = discovery()
    const error = discovered?.error

    if (discovery.loading && !error) {
      result.push({
        value: {
          kind: "agency",
          agency: "__loading__",
        },
        title: "Discovering agency-swarm agents...",
        disabled: true,
        category: "agency-swarm",
      })
      return result
    }

    if (error) {
      result.push({
        value: {
          kind: "agency",
          agency: "__error__",
        },
        title: "Agency discovery failed",
        description: error,
        disabled: true,
        category: "agency-swarm",
      })
      result.push({
        value: {
          kind: "connect",
        },
        title: "Open /connect",
        description: "Select a local server or update token",
        category: "agency-swarm",
      })
      return result
    }

    const agencies = discovered?.agencies ?? []
    if (agencies.length > 1 && !providerOptions().agency) {
      result.push({
        value: {
          kind: "agency",
          agency: "__choose__",
        },
        title: "Choose a swarm",
        description: "Multiple swarms were discovered. Select one before managing agent models.",
        disabled: true,
        category: "agency-swarm",
      })
    }
    for (const agency of agencies) {
      const category = `Swarm: ${agency.name}`
      const entry = agency.agents.find((agent) => agent.isEntryPoint) ?? agency.agents[0]
      const description =
        agency.description && agency.description !== entry?.description ? agency.description : undefined
      result.push({
        value: {
          kind: "agency",
          agency: agency.id,
        },
        title: agency.name,
        description,
        category,
      })
      for (const agent of agency.agents) {
        const model =
          openSwarmModels.routeAgency?.() === agency.id
            ? (openSwarmModels.agentModel(agent.id) ?? openSwarmModels.agentModel(agent.name))
            : undefined
        result.push({
          value: {
            kind: "recipient",
            agency: agency.id,
            recipientAgent: agent.id,
          },
          title: `- ${agent.name}`,
          description: agentDescription(agent, model),
          category,
        })
      }
    }

    const modelState = openSwarmModels.state()
    if (agencies.length > 0 && providerOptions().agency && (modelState || openSwarmModels.loading())) {
      const currentModel = openSwarmModels.currentAgentModel()
      result.push({
        value: {
          kind: "manage_models",
        },
        title: "Manage agent models",
        description: currentModel
          ? `Current: ${currentModel.name} uses ${currentModel.modelLabel}`
          : "Loading models...",
        category: "Actions",
      })
    }

    if (result.length === 0) {
      result.push({
        value: {
          kind: "agency",
          agency: "__empty__",
        },
        title: "No agencies discovered",
        description: `Check ${providerOptions().baseURL} and run \`agentswarm agency agencies\``,
        disabled: true,
        category: "agency-swarm",
      })
    }

    return result
  })

  const current = createMemo<AgentOptionValue | undefined>(() => {
    if (!agencySwarmEnabled()) {
      return {
        kind: "local",
        agent: local.agent.current()?.name ?? "build",
      }
    }

    const selected = resolveAgencyTargetSelection({
      agencies: discovery()?.agencies ?? [],
      configuredAgency: providerOptions().agency,
      configuredRecipient: providerOptions().recipientAgent,
    })
    if (selected) {
      if (!selected.recipientAgent) {
        return {
          kind: "agency",
          agency: selected.agency,
        }
      }
      return {
        kind: "recipient",
        agency: selected.agency,
        recipientAgent: selected.recipientAgent,
      }
    }

    if (providerOptions().agency) {
      return {
        kind: "agency",
        agency: providerOptions().agency!,
      }
    }

    return undefined
  })

  return (
    <DialogSelect
      title={agencySwarmEnabled() ? "Select swarm" : "Select agent"}
      current={current()}
      options={options()}
      onSelect={(option) => {
        if (option.value.kind === "local") {
          local.agent.set(option.value.agent)
          dialog.clear()
          return
        }

        if (option.value.kind === "connect") {
          dialog.replace(() => <DialogAgencySwarmConnect />)
          return
        }

        if (option.value.kind === "manage_models") {
          dialog.replace(() => <DialogOpenSwarmAgentModels />)
          return
        }

        void setAgencySwarmTarget(option.value).catch((error) => {
          toast.show({
            variant: "error",
            message: error instanceof Error ? error.message : String(error),
            duration: 6000,
          })
        })
      }}
    />
  )

  async function setAgencySwarmTarget(value: Extract<AgentOptionValue, { kind: "agency" | "recipient" }>) {
    const options = providerOptions()
    const selected = resolveAgencyTargetFromPicker({
      agencies: discovery()?.agencies ?? [],
      selectedAgency: value.agency,
      selectedRecipient: value.kind === "recipient" ? value.recipientAgent : undefined,
    })
    const nextOptions = buildAgencyTargetOptions({
      providerOptions: options,
      agency: value.agency,
      recipientAgent: selected?.recipientAgent ?? null,
    })

    await sdk.client.global.config.update(
      {
        config: {
          model: `${AgencySwarmAdapter.PROVIDER_ID}/${AgencySwarmAdapter.DEFAULT_MODEL_ID}`,
          provider: {
            [AgencySwarmAdapter.PROVIDER_ID]: {
              name: "agency-swarm",
              options: nextOptions,
            },
          },
        },
      },
      {
        throwOnError: true,
      },
    )

    await sdk.client.instance.dispose()
    await sync.bootstrap()
    dialog.clear()

    const selectedMessage =
      value.kind === "agency"
        ? `Selected swarm ${selected?.agencyLabel ?? value.agency}`
        : `Selected ${selected?.label ?? value.recipientAgent} in swarm ${selected?.agencyLabel ?? value.agency}`
    toast.show({
      variant: "success",
      message: selectedMessage,
      duration: 3000,
    })
  }
}

function agentDescription(
  agent: AgencySwarmAdapter.AgencyAgentDescriptor,
  model: AgencySwarmAdapter.OpenSwarmAgentModelState | undefined,
) {
  const parts: string[] = []
  if (agent.description) parts.push(agent.description)
  else if (agent.isEntryPoint) parts.push("Entry point")
  if (model) {
    const suffix = model.resolvedFrom === "default" ? " via DEFAULT_MODEL" : ""
    parts.push(`Model: ${model.modelLabel}${suffix}`)
    if (!model.available) parts.push(`Status: ${model.status}`)
  }
  return parts.join(" | ") || undefined
}

type ModelAgentOption = {
  kind: "agent"
  agent: AgencySwarmAdapter.OpenSwarmAgentModelState
}

function DialogOpenSwarmAgentModels() {
  const dialog = useDialog()
  const models = useOpenSwarmModels()

  const options = createMemo<DialogSelectOption<ModelAgentOption>[]>(() => {
    const state = models.state()
    if (!state && models.loading()) {
      return [
        {
          value: { kind: "agent", agent: emptyAgent("Loading") },
          title: "Loading OpenSwarm model status...",
          disabled: true,
        },
      ]
    }
    if (!state) {
      const error = models.error()
      return [
        {
          value: { kind: "agent", agent: emptyAgent("Unavailable") },
          title: "OpenSwarm model status unavailable",
          description:
            error instanceof Error ? error.message : error ? String(error) : "Check the local bridge and try again.",
          disabled: true,
        },
      ]
    }
    return state.agents.map((agent) => ({
      value: {
        kind: "agent",
        agent,
      },
      title: agent.name,
      description: modelStatusDescription(agent),
      category: "OpenSwarm agents",
    }))
  })

  return (
    <DialogSelect
      title={models.state()?.agency ? `Agent models - ${models.state()?.agency}` : "Agent models"}
      options={options()}
      onSelect={(option) => {
        dialog.replace(() => <DialogOpenSwarmModelPicker agent={option.value.agent} />)
      }}
    />
  )
}

type ModelCatalogOption =
  | {
      kind: "catalog"
      model: AgencySwarmAdapter.OpenSwarmModelCatalogItem
    }
  | {
      kind: "custom"
    }

function DialogOpenSwarmModelPicker(props: { agent: AgencySwarmAdapter.OpenSwarmAgentModelState }) {
  const dialog = useDialog()
  const toast = useToast()
  const models = useOpenSwarmModels()
  const [busy, setBusy] = createSignal(false)

  const options = createMemo<DialogSelectOption<ModelCatalogOption>[]>(() => {
    const state = models.state()
    const catalog = state?.catalog ?? []
    const result: DialogSelectOption<ModelCatalogOption>[] = catalog.map((item) => ({
      value: {
        kind: "catalog",
        model: item,
      },
      title: item.label,
      description: `${item.id}${item.available ? "" : ` | ${item.status}`}`,
      category: item.source === "subscription" ? "Subscriptions" : "API providers",
      disabled: busy(),
    }))
    if (state?.allowCustom !== false) {
      result.push({
        value: {
          kind: "custom",
        },
        title: "Custom model ID",
        description: "Use any OpenAI, subscription, or LiteLLM model string",
        category: "Advanced",
        disabled: busy(),
      })
    }
    return result
  })

  return (
    <DialogSelect
      title={`Model for ${props.agent.name}`}
      current={
        options().find((option) => option.value.kind === "catalog" && option.value.model.id === props.agent.model)
          ?.value
      }
      options={options()}
      onSelect={(option) => {
        if (option.value.kind === "custom") {
          dialog.replace(() => <DialogOpenSwarmCustomModelPrompt agent={props.agent} />)
          return
        }
        void updateModel(option.value.model.id)
      }}
    />
  )

  async function updateModel(modelID: string) {
    setBusy(true)
    try {
      await models.setAgentModel(props.agent.name, modelID)
      toast.show({
        variant: "success",
        message: `${props.agent.name} now uses ${modelID}`,
        duration: 3000,
      })
      dialog.replace(() => <DialogOpenSwarmAgentModels />)
    } catch (error) {
      toast.show({
        variant: "error",
        message: error instanceof Error ? error.message : String(error),
        duration: 6000,
      })
    } finally {
      setBusy(false)
    }
  }
}

function DialogOpenSwarmCustomModelPrompt(props: { agent: AgencySwarmAdapter.OpenSwarmAgentModelState }) {
  const dialog = useDialog()
  const toast = useToast()
  const models = useOpenSwarmModels()
  const [busy, setBusy] = createSignal(false)

  return (
    <DialogPrompt
      title={`Custom model for ${props.agent.name}`}
      value={props.agent.model}
      placeholder="subscription/codex, gpt-5.2, litellm/anthropic/..."
      busy={busy()}
      busyText="Updating model..."
      onConfirm={(value) => {
        void updateModel(value)
      }}
    />
  )

  async function updateModel(value: string) {
    const modelID = value.trim()
    if (!modelID) return
    setBusy(true)
    try {
      await models.setAgentModel(props.agent.name, modelID)
      toast.show({
        variant: "success",
        message: `${props.agent.name} now uses ${modelID}`,
        duration: 3000,
      })
      dialog.replace(() => <DialogOpenSwarmAgentModels />)
    } catch (error) {
      toast.show({
        variant: "error",
        message: error instanceof Error ? error.message : String(error),
        duration: 6000,
      })
    } finally {
      setBusy(false)
    }
  }
}

function modelStatusDescription(agent: AgencySwarmAdapter.OpenSwarmAgentModelState) {
  const source = agent.resolvedFrom === "default" ? "DEFAULT_MODEL" : agent.envKey
  const status = agent.available ? agent.status : `${agent.status}: ${agent.statusDetail ?? "not available"}`
  return `${agent.modelLabel} | ${source} | ${status}`
}

function emptyAgent(name: string): AgencySwarmAdapter.OpenSwarmAgentModelState {
  return {
    id: name,
    name,
    envKey: "",
    model: "",
    modelLabel: "",
    resolvedFrom: "agent",
    isEntryPoint: false,
    loaded: false,
    available: false,
    status: "unknown",
  }
}
