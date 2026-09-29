---
name: project-context
description: Restore repository context, save a bounded cross-host handoff, validate agent instructions, or initialize the shared Codex and Claude workflow for a new product.
---

# Project context

For an existing repository, read root `AGENTS.md` and `.agents/workflow.md`.
Run `python3 .agents/context.py resume`; load the task checkpoint only when
continuing that task. Reconcile stale branch/SHA/diff before using old evidence.
Keep repository-specific decisions in the sources named by `.agents/project.json`.
Use `checkpoint --task <slug> --from-file <reviewed.json>` before a substantial
handoff; see the workflow for its six required fields. Run `check` after editing
agent infrastructure. This tool does not run product tests, models or network calls.

For a new product lacking this workflow, use the user-level `project-bootstrap`
skill when installed. It creates a reviewable starting point without replacing
existing instructions. Infer the stack from the actual project or user's request;
do not impose a Flutter template on Swift/web products. No automatic provider,
MCP, RAG, Beads, model training or LangChain installation.
