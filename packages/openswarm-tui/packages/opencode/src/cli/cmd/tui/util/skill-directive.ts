export function skillPromptText(skill: string, frameworkMode: boolean) {
  if (!frameworkMode) return `/${skill} `
  return `Use OpenSwarm skill "${skill}" for this request:\n`
}
