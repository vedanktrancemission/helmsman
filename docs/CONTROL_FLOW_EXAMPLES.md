# Control-flow examples — build each one by hand

Four walkthroughs, one per control-flow node kind. Each builds a complete, runnable
workflow on the canvas from an empty state and ends with the exact input to type and the
exact trail you should see.

Everything here works with the offline `fake` model, so no API key is needed. Every
branch is driven from the run input, so you can steer each flow deterministically.

> **Shortcut:** the same four flows ship as templates. In **Builder → Templates**, click
> **+ Example: If / Else**, **+ Example: Switch**, **+ Example: For loop**, or
> **+ Example: While loop** to load a finished copy, then skip to the *Run it* step of
> any section below. Build by hand when you want to learn the canvas; load the template
> when you just want to test.

---

## Before you start

```bash
cd server && ./venv/bin/python -m uvicorn app.main:app --reload --port 8000
cd web && npm run dev            # separate shell → http://localhost:5173
```

### The canvas, in one minute

| Thing | Where |
|---|---|
| Create an empty workflow | **New Workflow** → type a name |
| Open the node palette | **+ Add Node** |
| Add an agent node | palette → pick an agent → **Add agent** |
| Add a control node | palette → **◇ If / Else**, **⑃ Switch**, **↻ While Loop**, **⟳ For Loop** |
| Edit a control node | click it → inspector opens on the right |
| Wire two nodes | drag from a node's right-hand dot onto the next node's left-hand dot |
| Set the start node | **ENTRY:** dropdown |
| Remove a node | select it → **Delete Node** |
| Persist the graph | **Save** (also runs automatically before **Run ▶**) |

Three rules that matter:

1. **Every branch is its own handle.** A control node has one labelled dot per branch on
   its right edge — `true`/`false`, each switch case plus `default`, or `body`/`exit`.
   Drag from the specific branch you mean.
2. **An unwired branch ends the run.** Unwired branches are marked `⊘` on the node. That
   is a legitimate design (`exit → END` is often what you want), not an error.
3. **A loop's `body` must come back.** Wire `body` out to the work, then wire the last
   node of that work back into the loop node. That back edge *is* the loop. **Save**
   refuses a loop whose `body` is unwired and shows the reason in the Output box.

### Node names are generated

Agent nodes take the agent's name; control nodes are named after their kind — `IfElse`,
`Switch`, `WhileLoop`, `ForLoop` (a second one becomes `IfElse_2`). Duplicates are
suffixed automatically. There is no rename field in the inspector yet, so if an
expression needs to reference a loop by name, use the generated name — e.g.
`loop['ForLoop']['results']`, not `loop['EachItem']['results']`. The shipped templates use
friendlier names because they are defined in code.

### Expressions

Every condition / expression / items field is a Python expression evaluated against the
run state. Click **Show available variables** in the inspector for the full list; the ones
used below are:

| Variable | Meaning |
|---|---|
| `input` | the run's original task text |
| `last_output` | output of the most recent agent |
| `outputs` | dict of every node's latest output — `outputs['Draft']` |
| `item`, `index`, `count`, `total`, `results` | state of the innermost loop |
| `loop` | any loop by name — `loop['ForLoop']['results']` |

An expression that raises is treated as falsy rather than failing the run, so a typo
sends an `if` down the `false` branch instead of blowing up the workflow.

---

## 1. If / Else — route on the input

Two outcomes from one boolean. An intake agent restates the request, then an if node
checks whether it is urgent.

```
Intake ──▶ IfElse ──true──▶ RushHandler
                 └─false──▶ NormalHandler
```

### Create the agents

**Agents** tab → **Create**, three times:

| Name | Role | System prompt |
|---|---|---|
| `Intake` | `intake` | Restate the incoming request in one sentence. |
| `RushHandler` | `on-call` | This is urgent. Give the immediate mitigation steps, shortest path first. |
| `NormalHandler` | `support` | This is not urgent. Queue it and give a normal, thorough answer. |

Leave Model as `fake` and every other field at its default.

### Build the flow

1. **Builder** tab → **New Workflow** → name it `If Else Demo`.
2. **+ Add Node** → select `Intake` → **Add agent**. It becomes the entry automatically
   (check the **ENTRY:** dropdown reads `Intake`).
3. **+ Add Node** → **◇ If / Else**. A node named `IfElse` appears with `true` and
   `false` handles, both marked `⊘`.
4. **+ Add Node** → `RushHandler` → **Add agent**. Repeat for `NormalHandler`.
5. Drag the nodes so `Intake` is left, `IfElse` is next, and the two handlers are stacked
   on the right. (Layout is cosmetic, but it makes the wiring obvious.)
6. Click `IfElse`. In the inspector, set **Condition** to:
   ```python
   'urgent' in input.lower()
   ```
7. Wire it up — four drags:
   - `Intake` right dot → `IfElse` left dot
   - `IfElse` **true** dot → `RushHandler`
   - `IfElse` **false** dot → `NormalHandler`
   - leave both handlers unwired — they end the run
8. **Save**. The `⊘` marks on `true`/`false` disappear.

### Run it

| Input | Expected trail |
|---|---|
| `urgent: login is broken` | `Intake` → `IfElse → branch:true` → `RushHandler` |
| `review this when free` | `Intake` → `IfElse → branch:false` → `NormalHandler` |

Open **Monitor**, click the run in **Run history**, and you will see the decision
persisted as a `control` message:

```
[control] IfElse -> branch:true   [if] 'urgent' in input.lower() == True → true
```

### Try changing it

- Point the condition at the agent instead of the raw input:
  `'urgent' in last_output.lower()` — now `Intake`'s wording decides the branch.
- Delete the `false` edge and Save. The flow still validates; non-urgent requests simply
  end after `IfElse`.

---

## 2. Switch — route to one of N lanes

Same idea, more than two destinations. The switch evaluates an expression and jumps to
the case that matches its value, or to `default` when nothing matches.

```
                  ┌─billing──▶ BillingLane
Switch (entry) ───┼─tech─────▶ TechLane
                  └─default──▶ GeneralLane
```

### Create the agents

| Name | Role | System prompt |
|---|---|---|
| `BillingLane` | `billing` | Resolve billing and payment questions clearly. |
| `TechLane` | `technical` | Resolve technical issues with concrete steps. |
| `GeneralLane` | `general` | Handle anything that did not match a case. |

### Build the flow

1. **New Workflow** → `Switch Demo`.
2. **+ Add Node** → **⑃ Switch**. The node `Switch` appears with handles `a`, `b`,
   `default` (the two placeholder cases). It is the entry — no agent needed in front of a
   switch.
3. Click `Switch` and set **Expression** to:
   ```python
   'billing' if 'billing' in input.lower() else ('tech' if 'tech' in input.lower() else 'other')
   ```
4. Set **Cases (comma separated)** to `billing, tech`. Watch the handles update live:
   `a`/`b` are replaced by `billing`/`tech`, and `default` stays. Removing a case also
   removes any edge that was attached to it.
5. Add the three agent nodes.
6. Wire `billing → BillingLane`, `tech → TechLane`, `default → GeneralLane`.
7. **Save**.

Note the expression can return `'other'`, which is not a case. That is the point —
anything unmatched lands on `default`.

### Run it

| Input | Expression value | Expected lane |
|---|---|---|
| `billing question about my invoice` | `billing` | `BillingLane` |
| `tech issue with the app` | `tech` | `TechLane` |
| `hello there` | `other` | `GeneralLane` via `default` |

```
[control] Switch -> branch:billing   [switch] value='billing' → billing
[control] Switch -> branch:default   [switch] value='other' (no case matched) → default
```

### Try changing it

Replace the expression with `input.strip().lower().split()[0]` and set cases to
`billing, tech, sales`. Now the first word of your input picks the lane directly — type
`sales renewal quote` and it routes to a `sales` handle. An empty input raises inside the
expression, which is treated as no match, so it falls to `default`.

---

## 3. For loop — run the same work once per item

A for node evaluates `items` once, then hands the body one item per pass. The body loops
back into the for node, which advances to the next item and finally takes `exit`.

```
ForLoop (entry) ──body──▶ Handler ──┐
   ▲                                │
   └────────────────────────────────┘
   └─exit──▶ Recap
```

### Create the agents

| Name | Role | System prompt |
|---|---|---|
| `Handler` | `worker` | Handle the single item named in the loop context. One short line. |
| `Recap` | `reporter` | Summarize what was done for every item across the loop. |

### Build the flow

1. **New Workflow** → `For Loop Demo`.
2. **+ Add Node** → **⟳ For Loop**. `ForLoop` appears with `body` and `exit`. It is the
   entry.
3. Click it and set **Items** to:
   ```python
   [p.strip() for p in input.split(',') if p.strip()]
   ```
   Set **Max iterations** to `5`.
4. Add `Handler` and `Recap`. Drag `Handler` *below* `ForLoop` and `Recap` to its right —
   this keeps the loop-back edge readable.
5. Wire three edges:
   - `ForLoop` **body** dot → `Handler`
   - `Handler` right dot → **back into `ForLoop`** ← this is the loop
   - `ForLoop` **exit** dot → `Recap`
6. **Save**.

The `body` edge draws as an animated orange line so the cycle is visible at a glance.

> If you skip step 5's back edge, **Save** fails with
> `for node 'ForLoop' must wire its 'body' branch to a node` in the Output box. Wire it
> and save again.

### Run it

| Input | Expected |
|---|---|
| `alpha, beta, gamma` | `Handler` runs **3×** — once per item — then `Recap` |
| `a,b,c,d,e,f,g` | `Handler` runs **5×**, capped by Max iterations, then `Recap` |
| `just one` | `Handler` runs **1×**, then `Recap` |

The persisted trail for `alpha, beta, gamma`:

```
[control] ForLoop -> branch:body   [for] item 1/3: 'alpha' → body
[agent  ] Handler -> workflow      … LOOP CONTEXT: loop=ForLoop, iteration=1 of 3, item='alpha'
[control] ForLoop -> branch:body   [for] item 2/3: 'beta' → body
[agent  ] Handler -> workflow      … item='beta'
[control] ForLoop -> branch:body   [for] item 3/3: 'gamma' → body
[agent  ] Handler -> workflow      … item='gamma'
[control] ForLoop -> branch:exit   [for] exhausted after 3 item(s) → exit
[agent  ] Recap   -> workflow      …
```

Note the `LOOP CONTEXT` line: the current `item` is injected into the body agent's prompt
automatically, which is what lets one agent handle a different item each pass.

### Try changing it

- Iterate over another node's output instead of the input. Put an agent in front of the
  loop, make it the entry, and set **Items** to `outputs['Planner'].splitlines()` — a
  string is split on newlines for you.
- Iterate a fixed count: **Items** = `5`. An integer becomes a range, so you get items
  `0`–`4`.
- Add an if node after the loop to act on everything it collected. Wire `exit` into a new
  **◇ If / Else** and set its condition to:
  ```python
  any('RISK' in str(r).upper() for r in loop['ForLoop']['results'])
  ```
  `results` is the list of body outputs, in order — the loop takes `exit` only after the
  last body output has been collected.

---

## 4. While loop — repeat until a condition goes false

A while node re-evaluates its condition before every body pass. This is the classic
draft → review → revise cycle, and it exits the moment the reviewer approves.

```
Draft ──▶ Review ──▶ WhileLoop ──body──▶ Writer ──┐
                        ▲                          │
                        └──────────────────────────┘  (Writer → Review)
                        └─exit──▶ Ship
```

### Create the agents

| Name | Role | System prompt |
|---|---|---|
| `Draft` | `writer` | Write a first draft of whatever the task asks for. |
| `Review` | `reviewer` | Critique the draft against a quality bar. Reply starting with APPROVE if it is good enough, otherwise start with REVISE and give one concrete fix. |
| `Writer` | `writer` | Improve the draft using the latest feedback. Return the full revised draft. |
| `Ship` | `publisher` | Emit the approved final version, cleaned up and ready to ship. |

The `APPROVE` / `REVISE` convention is what the loop condition reads. Keep it.

### Build the flow

1. **New Workflow** → `While Loop Demo`.
2. Add `Draft` (entry), then `Review`.
3. **+ Add Node** → **↻ While Loop**. Click `WhileLoop` and set **Condition** to:
   ```python
   'APPROVE' not in last_output.upper()
   ```
   Set **Max iterations** to `4`.
4. Add `Writer` (place it below `WhileLoop`) and `Ship` (to its right).
5. Wire five edges:
   - `Draft` → `Review`
   - `Review` → `WhileLoop`
   - `WhileLoop` **body** → `Writer`
   - `Writer` → **`Review`** ← back into the *reviewer*, not into the loop node, so each
     revision gets re-reviewed and the condition sees a fresh verdict
   - `WhileLoop` **exit** → `Ship`
6. **Save**.

The back edge closes the cycle `WhileLoop → Writer → Review → WhileLoop`. Any path that
returns to the loop node works; it does not have to be a direct edge from the body.

### Run it

Any input works — try `write a launch tweet`:

```
[agent  ] Draft       …
[agent  ] Review       REVISE — tighten the hook and trim adjectives.
[control] WhileLoop    [while] iteration 1/4 → body
[agent  ] Writer      …
[agent  ] Review       REVISE — tighten the hook and trim adjectives.
[control] WhileLoop    [while] iteration 2/4 → body
[agent  ] Writer      …
[agent  ] Review       APPROVE — the draft meets the bar.
[control] WhileLoop    [while] condition false after 2 iteration(s) → exit
[agent  ] Ship        …
```

Two revisions, then the condition goes false and the loop exits to `Ship`. (Offline, the
fake reviewer is scripted to approve on the second revision; with a real model it exits
whenever the reviewer is satisfied.)

### Prove the guard works

Change the condition to a literal `True` and Save, then run again. The condition never
goes false, so `Max iterations` stops it:

```
[control] WhileLoop -> branch:exit   [while] iteration guard reached (4)
```

The run still completes and still reaches `Ship`. This is why a while loop can never hang
the workflow — set the cap to what you can afford and the loop is bounded by construction.

---

## Where to look when something is off

| Symptom | Cause |
|---|---|
| `Save` shows `must wire its 'body' branch` | loop body isn't connected — see rule 3 |
| `Save` shows `needs a 'condition' expression` | control node's expression field is empty |
| `Save` shows `no branch 'x'` | an edge references a case you have since removed |
| `if` always takes `false` | the expression raised — check names against the variables list |
| Loop runs once and exits | `items` produced an empty list; check it in the inspector |
| Run ends right after a control node | that branch is unwired (`⊘`), which ends the run |
| Loop hits the guard unexpectedly | condition never goes false; log `last_output` in Monitor |

`recursion_limit` is derived from your loops' `max_iterations`, so nested and long loops
get enough supersteps automatically. Set `recursion_limit` explicitly in the saved
`graph_spec` if you need to override it.

The same eight runs documented above are asserted in
`server/tests/test_control_flow.py`, so `cd server && pytest -q` verifies every branch
without opening the UI.
