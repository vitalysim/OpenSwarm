import { describe, expect, test } from "bun:test"
import { skillPromptText } from "../../../src/cli/cmd/tui/util/skill-directive"

describe("skill prompt directive", () => {
  test("uses native slash command outside agency-swarm mode", () => {
    expect(skillPromptText("pptx", false)).toBe("/pptx ")
  })

  test("uses OpenSwarm directive in agency-swarm mode", () => {
    expect(skillPromptText("security-deck", true)).toBe('Use OpenSwarm skill "security-deck" for this request:\n')
  })
})
