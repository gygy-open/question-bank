# Question Structure

Question structure splits the **stem** of a question into **conditions** and **asks**, and classifies each one by the subject's **structure types**. After a teacher reviews a decomposition, it can be used to find questions by structure, see the structure distribution of a paper, and analyze how questions are built.

::: tip Stem only
Decomposition uses only the stem (including options), never the answer or explanation. Answers add a lot of noise.
:::

## Concepts

| Concept | Meaning | Example |
| --- | --- | --- |
| Condition | One thing the stem gives: an object under study, a known value, a relation, a constraint, or something that varies. Each condition states exactly one thing | "$f(x)=x^3+ax+2$", "$f(x)$ has 3 zeros" |
| Ask | One thing to answer; with sub-questions (1)(2), one per sub-question | "Find the range of $a$" |
| Structure type | A category of conditions / asks, organized as a tree per subject | Algebra › Function › Parametric cubic function |
| Source span | Which part of the stem each condition / ask comes from | Highlighted in the panel |

Structure types, **knowledge points** and **tags** are three independent classifications:

- **Knowledge points** come from textbooks and curriculum standards and have a stable hierarchy;
- **Tags** cover everything else;
- **Structure types** describe how stem conditions are built and are maintained by teachers. The AI can only choose from active types; when none fits, it adds a description (shown as "Unclassified") for teachers to sort out.

## Decomposing questions

1. In the question bank, open "Stem Structure" from a question's action menu, or click "Stem Structure" while editing a question, then choose "Decompose". You can also select several questions and use the batch action "Decompose stems".
2. Decomposition runs in the background and shares one queue with Smart Import. When the AI service has a problem, imports and decompositions pause together and resume together once it recovers.
3. A finished decomposition is **awaiting review**. It is used for search and statistics only after it is accepted.

Each decomposition is checked automatically, and problems are shown next to the affected item:

| Problem | Meaning |
| --- | --- |
| Source text not found | The quoted text does not exist in the stem (the AI rewrote it) |
| Duplicate | Two conditions say the same thing |
| Ask symbol not introduced | A letter used in the ask (such as $a$) appears in no condition, which usually means a condition is missing |
| May contain several assertions | A condition contains "and" or similar; consider splitting it (warning only) |
| Uncovered text | Stem text not covered by any item (hint only; descriptive words such as "Given" or "the function" do not need to be decomposed) |

When the check finds errors, the AI automatically decomposes once more with the list of problems.

## Review and editing

- The **review page** (sidebar "Structure Review") lists all decompositions awaiting review in the current subject, with errors first. Shortcuts: `J` / `K` next / previous, `A` accept, `X` reject, `E` edit, `R` decompose again. Decompositions without errors can be accepted in bulk.
- **Editing**: select text in the source to add it as a condition or an ask; rewrite, classify, reorder, merge or split items; tick the conditions an ask depends on. Saving creates a new "edited manually" version, and the AI result is kept for comparison.
- **Source**: a decomposition comes from "AI", "Manual" or "External agent" (submitted through MCP). The review page can filter by source.
- **Outdated**: when a question is edited after decomposition, its accepted decomposition is marked "Outdated" and can be decomposed again with one click. Reviewed results are never overwritten automatically.

## Material questions

A material (shared stem) is decomposed once. When a sub-question is decomposed and its material has not been decomposed yet, the material is decomposed first; sub-questions then reference its conditions (shown as "From material") instead of repeating them.

## Parameters and variants

During decomposition the AI marks **parameters** under conditions and asks: values a teacher could change to make a variant, such as coefficients, constants, lengths or point coordinates. Parameters are underlined with a dotted line in the source, and each item shows "name = value".

- **Editing parameters**: in edit mode, select text in the source and click "Set as parameter"; for a number inside a formula, click "Add parameter" under the item and type the value. Each parameter has a name, a kind, a domain (min, max, integer, allowed values, note) and a "replaceable" flag.
- **Domain**: the AI suggests a domain, but it takes effect only after a teacher ticks "Domain confirmed". Changing the domain clears the confirmation.
- **Generate variant**: on an accepted, up-to-date decomposition, click "Generate variant". Enter new values, or tick "AI picks" (only for parameters with a confirmed domain); the dialog previews the changed stem. After you submit:
  1. Values are replaced at their exact positions in the source, never by find-and-replace, so the 2 in `x^2` is never changed by mistake;
  2. AI re-solves the question and checks that the conditions are consistent, the answer is unique and the numbers are reasonable. For choice questions it also checks the options; if they no longer fit, AI rewrites them and you are asked to review them. Options written inline in the stem cannot be rewritten, so such a variant is rejected;
  3. If the variant works, a **draft question** is created (duplicate checks still apply) and linked to the original as a variant; otherwise the reason is shown and no question is created.

## Element groups and the composition basket

- **Element groups**: in edit mode, several conditions can be grouped, for example "function and zeros". When every condition in a group is classified, use "Replace group" to swap in a group with the same condition types from another question; AI rewrites the question, checks it and creates a draft variant.
- **Composition basket**: in an accepted decomposition, use the button next to a condition, ask or group to add it to the composition basket (items may come from several questions of one subject). Choose a question type, add a note, and AI writes a new question. The system then:
  1. decomposes the new question and checks that every chosen item is used and no other condition is added; if not, AI rewrites it once;
  2. re-solves it;
  3. if both checks pass, creates a draft question linked to every source question as composed, and saves its decomposition for review.

## Solution structure and thinking difficulty

After the stem decomposition is accepted, open the "Solution structure" tab in the structure panel to decompose the solution:

- Each step has a goal, a method and a result, the conditions (C1…), asks (Q1…) and earlier steps (S1…) it uses, and the ask it answers. Key steps can be marked, and typical mistakes can be recorded for a step (for example the mistake that leads to a wrong option).
- The check verifies that every step has a goal, references existing conditions and asks, uses only earlier steps, and that every ask is answered by some step.
- A question can have several solutions; each is reviewed separately.
- **Thinking difficulty**: the thinking load of a solution is the sum of its step weights, where a normal step counts as 1. Method weights are set in the "Method" tree on the Structure Types page. A question's thinking difficulty is the smallest load among its accepted solutions. It is shown next to the existing 1–5 star difficulty, and the question bank can filter and sort by it.
- When the stem decomposition is replaced or the question is edited, the solution is marked "Needs review".

## Managing structure types

Sidebar "Structure Types" maintains the type tree of the current subject:

- For math, the first level of condition types is **Algebra** (structure of expressions), **Geometry** (structure of shapes) and **Statistics** (structure of statistics), plus an **Ask** root. Other subjects have one "Condition" root and one "Ask" root. A **Method** root classifies solution steps, and method types can have a thinking-load weight. Teachers add or import the types below the roots.
- When editing a type you can choose its **knowledge points**. When a stem item or solution step belongs to the type, the stem structure panel suggests these knowledge points for the question, and you can add them with one click.
- You can add, rename, move, merge (references and children move along), deactivate and delete types (only unused types without children), and import / export them as JSON.
- Only **active** types are offered to the AI and shown in filters.

- **Pending grouping**: for unclassified items, the AI writes a short category description. Once there are enough of them (at least 10 conditions or 10 asks), a subject manager can click "Start grouping" on the "Pending grouping" tab. AI groups items with similar meaning into candidate types, with a suggested parent and similar existing types. For each candidate, choose "Create as type", "Merge into existing type" or "Ignore"; once confirmed, the items in the group are classified automatically. Ignored items are not grouped again.

Maintaining structure types requires the subject's "edit knowledge points / tags" permission; starting grouping requires subject management permission.

## Where it is used

- **Question bank filters**: by structure type (including child types) and structure state (not decomposed / awaiting review / accepted / outdated); the list shows a state badge.
- **Related questions**: in the stem structure panel, find accepted related questions in three ways: "Similar types" (similar ask and condition types), "Shared conditions" (identical conditions, ignoring formatting) and "Changed numbers" (same parameter pattern, different values).
- **Compositions**: filter by structure type when adding questions; the composition sidebar shows the structure distribution of the whole paper.
- **Dashboard**: decomposition progress, items awaiting review, common structure types, decomposition sources, knowledge point mapping coverage of types, and the number of questions with a thinking difficulty.
- **In-app AI and MCP**: read stem and solution structures and find questions by structure type. Through MCP, external agents can also request decompositions, generate variants, replace groups, compose questions, decompose solutions, maintain the structure type tree and start type grouping (with the user's own permissions), then check results with `get_structure_job`. This suits agents that process data or run validation in bulk. Everything an agent produces is a draft question or a decomposition awaiting review; **accepting it must be done by a teacher in the app**.
- **Telling agent-generated questions apart**: questions created through MCP, including those generated by agent-started variant or composition jobs, show an "Agent" badge in the question list; the "Created via" filter shows only these questions, which makes reviewing or cleaning up test data easy.

## Switches

| Switch | Where | Default |
| --- | --- | --- |
| Question structure | System settings (super administrator) | On. When off, no new decompositions are accepted and structure features are hidden; existing data is kept |
| Decompose automatically after saving | Subject settings on the Structure Types page (subject manager) | Off. When on, newly created, imported and approved questions are queued automatically; this uses AI quota |

The Structure Types page also offers "Queue existing questions": it queues at the lowest priority, so imports and manual decompositions started by teachers are not delayed.

All related prompts can be overridden per subject in the subject's prompt settings: "Stem decomposition assistant", "Type grouping assistant", "Variant check assistant", "Composition assistant" and "Solution decomposition assistant".
