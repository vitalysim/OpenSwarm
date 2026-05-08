# OpenSwarm Skills

Project-local OpenSwarm skills live here. Each skill is one direct child folder
with a `SKILL.md` file:

```text
openswarm_skills/
  example-skill/
    SKILL.md
    references/
    assets/
```

`SKILL.md` must start with frontmatter:

```markdown
---
name: example-skill
description: When to use this skill.
---

# Example Skill

Instructions for agents.
```

OpenSwarm skills are provider-neutral. V1 loads instructions and read-only
resources only; bundled scripts are not executed. Nested skill folders are not
discovered, so keep each reusable workflow at `openswarm_skills/<skill>/`.
