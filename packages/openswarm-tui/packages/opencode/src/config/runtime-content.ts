let runtimeConfigContent: string | undefined

export function getRuntimeConfigContent() {
  return runtimeConfigContent ?? process.env.OPENCODE_CONFIG_CONTENT
}

export function setRuntimeConfigContent(config: unknown) {
  runtimeConfigContent = JSON.stringify(config)
  process.env.OPENCODE_CONFIG_CONTENT = runtimeConfigContent
}
