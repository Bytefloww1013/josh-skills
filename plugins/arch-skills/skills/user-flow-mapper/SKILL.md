---
name: "user-flow-mapper"
description: "Map an app user's journey for a task as Mermaid diagrams, get approval, then build mockups/prototype and a formal UX report. Use when asked for a user flow, journey map or flow blueprint."
---

# User Flow Mapper

A user flow is the blueprint of a UX strategy: the steps a user takes to finish one task in a product, from "Oh, I need this" to "Perfect, I'm done!". Before drawing, put yourself in the user's shoes: who they are, what triggers the need, what they see, what can go wrong, what "done" looks like.

## Inputs
- The application (name, purpose, users) and the task/journey to map.
- If either is missing, ask one short question, or state your assumption and proceed.

## Step 1: Diagram the flow
1. Write a one-paragraph framing: persona, trigger, goal, success state, assumptions.
2. Pick the **3 most relevant** of these 5 diagram types (unless the user specifies), and say in one line why each was chosen:
   - **Event Modeling** (UI -> Command -> Event -> Read model, left to right in time slices). Mermaid has no native eventmodeling type in most renderers, so render it as a `flowchart LR` with subgraph swimlanes: UI, Commands, Events, Read Models. Keep the `tf NN` slice numbering in node labels. Example source notation:
     ```
     tf 01 ui ShopUI
     tf 02 cmd AddItemToCart
     tf 03 evt ItemAdded
     tf 04 rmo CartView ->> 03
     ```
   - **State diagram** (`stateDiagram-v2`): lifecycle of the core object.
   - **Sequence diagram** (`sequenceDiagram`): actors and systems exchanging messages.
   - **Use case diagram** (`flowchart` with actors and use-case ovals): who can do what.
   - **User journey** (`journey`): stages, tasks, satisfaction scores, pain points.
   Selection heuristics: object with a lifecycle -> state; multiple systems/integrations -> sequence; event-driven or CQRS-ish backend -> event model; many roles/permissions -> use case; emotional/experience focus or onboarding -> journey.
3. Render the diagrams so the user sees them (inline widget or page loading mermaid@11 from a CDN), and also give the raw Mermaid source.
4. Validate syntax before showing (e.g. run the source through `@mermaid-js/mermaid-cli` or the mermaid parse API if available).

## Step 2: Ask for approval
Ask plainly: "Does this flow match what you have in mind?"
- **Not approved:** refine using their direction. If they give none or are unsure, ask narrowing questions (one at a time) to find the smallest acceptable flow, then iterate from that.
- **Approved:** build low-fi mockups and a self-contained clickable HTML prototype of the flow (one screen per UI slice / journey stage, with working navigation between steps and mocked data). The goal is a rough visual of what they asked for, not production code.

## Step 3: Formal report
After the prototype is approved, produce one report (a doc or page) containing:
- Summary: persona, task, goal, success criteria.
- Decisions log: every choice made and every change requested across iterations.
- Analysis: pain points, edge cases, error/empty states, risks, open questions.
- All final diagrams (rendered + Mermaid source).
- Mockups/prototype link and screen-by-screen notes.
- Recommended next steps: build order, data/entities needed, acceptance criteria per step.
If the user criticizes or asks to try again at any stage, pivot to a different path rather than tweaking the same one, and ask questions as needed.

## Rules
- Don't invent facts about the user's app as fact: label assumptions.
- Keep each diagram readable: about 15 nodes max; split if larger.
- Each step ends with a clear question or a clear deliverable.