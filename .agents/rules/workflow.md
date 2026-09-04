# Development Workflow Rules

## Mandatory Planning & Review Mode

1. **Always Plan First**:
   - For any new feature, code modification, refactor, bugfix, or architectural change, always create or update an implementation plan first (`implementationPlan.md` or implementation plan artifact).
   - The plan must clearly define:
     - Architecture & execution flow
     - File-by-file breakdown of proposed changes
     - Edge cases, risk controls, and mitigations
     - Step-by-step verification plan

2. **Strict Approval Gate**:
   - **DO NOT** write, modify, or delete any source code files, and **DO NOT** execute mutating implementation commands until the user has explicitly reviewed and approved the implementation plan.
   - Clarifying questions and design choices must be resolved or explicitly approved before code is written.

3. **Stop After Planning**:
   - Immediately after creating or updating an implementation plan, stop calling execution tools.
   - Present the key decisions to the user and wait for explicit confirmation/approval before proceeding with implementation.

