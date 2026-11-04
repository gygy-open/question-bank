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
- **Outdated**: when a question is edited after decomposition, its accepted decomposition is marked "Outdated" and can be decomposed again with one click. Reviewed results are never overwritten automatically.

## Material questions

A material (shared stem) is decomposed once. When a sub-question is decomposed and its material has not been decomposed yet, the material is decomposed first; sub-questions then reference its conditions (shown as "From material") instead of repeating them.

## Managing structure types

Sidebar "Structure Types" maintains the type tree of the current subject:

- For math, the first level of condition types is **Algebra** (structure of expressions), **Geometry** (structure of shapes) and **Statistics** (structure of statistics), plus an **Ask** root. Other subjects have one "Condition" root and one "Ask" root. Teachers add or import the types below the roots.
- You can add, rename, move, merge (references and children move along), deactivate and delete types (only unused types without children), and import / export them as JSON.
- Only **active** types are offered to the AI and shown in filters.

Maintaining structure types requires the subject's "edit knowledge points / tags" permission.

## Where it is used

- **Question bank filters**: by structure type (including child types) and structure state (not decomposed / awaiting review / accepted / outdated); the list shows a state badge.
- **Similar structure**: in the stem structure panel, see accepted questions whose ask and condition types are close.
- **Compositions**: filter by structure type when adding questions; the composition sidebar shows the structure distribution of the whole paper.
- **Dashboard**: decomposition progress, items awaiting review, common structure types.
- **In-app AI and MCP**: read decompositions, find questions by structure type, and request decompositions. Changes submitted by external AI clients can only be saved as drafts; accepting them must be done by a teacher in the app.

## Switches

| Switch | Where | Default |
| --- | --- | --- |
| Question structure | System settings (super administrator) | On. When off, no new decompositions are accepted and structure features are hidden; existing data is kept |
| Decompose automatically after saving | Subject settings on the Structure Types page (subject manager) | Off. When on, newly created, imported and approved questions are queued automatically; this uses AI quota |

The Structure Types page also offers "Queue existing questions": it queues at the lowest priority, so imports and manual decompositions started by teachers are not delayed.

The prompt used for decomposition can be overridden per subject in the subject's prompt settings ("Stem decomposition assistant").
