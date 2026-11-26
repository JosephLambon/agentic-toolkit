---
name: jira-user-story
description: Use when asked to write a Jira story, create a user story, turn a bug into a story, or add acceptance criteria to a story. Draft or publish one developer-ready story, not an implementation or backlog plan.
---

# Jira user story

Write for a developer opening the ticket cold. Explain why the work matters, where to make the change, and what observable result is required.

1. Read the supplied context and inspect relevant code and sources with the available tools. Verify exact app, service, integration, endpoint, repository, path, and symbol names wherever relevant. Link to the most specific verified location (file or symbol permalink, API operation, or document section). If a link is unavailable, retain the exact name and location. Never guess a name or URL; flag unknowns and ask for details that are essential to implement or test the story.
2. Select the evidence a developer needs to understand the problem or decision: relevant screenshots, sanitized excerpts, repro artifacts, and reference documents. Name each item and say what it shows. Omit restricted material and redact secrets and personal or customer data. Upload only files authorized for that issue and audience; confirm uncertain sharing before uploading. Explain the essential rationale in the story itself.
3. Use the template and trim to the hard limits below before delivering or publishing. If the scope cannot fit without losing a requirement, propose a split; do not silently drop acceptance criteria.
4. Draft without making Jira changes unless the user asks to create or update a ticket. Resolve the Jira site and project or issue key. Use the client's authenticated Jira integration; create as a Story, not a substitute issue type. If updating, read first; replace only the requested story block and preserve other description content, fields, links, and attachments. If the block cannot be identified safely or Jira access, Story type, or required inputs are missing, return the draft and name the blocker.
5. Link hosted sources in **Evidence and references**. For a requested write, attach each authorized evidence or reference file to the same issue. If available, discover `uploadAttachmentToJiraIssue` in the Atlassian connector and follow its prepare, local upload, and finalize instructions. Otherwise use an approved, already configured Jira attachment client. Initially mark local files as pending; after uploading, re-read the issue, remove pending markers only for verified attachments, and verify the resulting description, links, and attachment list. Report the ticket URL and any files still needing manual upload. Do not recreate the issue to retry an upload.

## Template

**Title:** Name the affected component and desired outcome.

```markdown
# User Story

**When** [trigger or current situation]

**I want** [desired capability or change]

**So that** [impact, risk addressed, or reason the change is needed]

## Where

- [Exact app](app-url) → [owner/repo](repo-url) → [`path` / `Function`](code-permalink), [environment if relevant]

# 🎯 Acceptance Criteria

**Scenario 1: [Observable behavior]**

**Given** [actor, state, and environment when relevant]

**When** [specific action, request, or event]

**Then** [testable result with expected value or behavior]

## Evidence and references

- [Attachment filename or descriptive source link] — [what it shows or why it matters]
```

Use one Where line per affected component and one numbered scenario per distinct outcome, including relevant failure or compatibility cases. If no evidence was supplied or found, say so. If a necessary claim cannot be verified or an essential implementation detail is missing, return a draft instead of publishing.

**Hard limits:** Title 12 words; User Story 60; Where 50; each scenario 45 including its title; Evidence and references 50; entire new story block 250. Count visible whitespace-separated words containing letters or digits, including scenario labels and inline Markdown link text, not Markdown syntax, link destinations, or section headings. Save only the story block as Markdown (exclude unrelated content retained on updates) and run `python <skill-dir>/scripts/check_words.py "<title>" <story.md>` before delivery or publishing. If Python is unavailable, count with the same rules using a local tool. Trim and recheck any overage.
