import { NodeKind, NodeSpec } from "./api";

export interface KindInfo {
  kind: NodeKind;
  label: string;
  icon: string;
  /** Branch handles this kind exposes, in display order. */
  branches: (spec: NodeSpec) => string[];
  /** Fresh config when a node of this kind is dropped on the canvas. */
  defaults: () => NodeSpec["config"];
  hint: string;
}

/** Mirrors CONTROL_TYPES / branch_keys in server/app/runtime/control.py. */
export const KINDS: Record<NodeKind, KindInfo> = {
  agent: {
    kind: "agent",
    label: "Agent",
    icon: "◆",
    branches: () => [],
    defaults: () => undefined,
    hint: "Runs an LLM agent and appends its output to the run.",
  },
  if: {
    kind: "if",
    label: "If / Else",
    icon: "◇",
    branches: () => ["true", "false"],
    defaults: () => ({ condition: "'urgent' in input.lower()" }),
    hint: "Evaluates a boolean expression and takes the true or false branch.",
  },
  switch: {
    kind: "switch",
    label: "Switch",
    icon: "⑃",
    branches: (spec) => {
      const cases = (spec.config?.cases || []).map(String).filter((c) => c && c !== "default");
      return [...cases, "default"];
    },
    defaults: () => ({ expression: "last_output.strip().lower()", cases: ["a", "b"] }),
    hint: "Evaluates an expression and jumps to the matching case, else default.",
  },
  while: {
    kind: "while",
    label: "While Loop",
    icon: "↻",
    branches: () => ["body", "exit"],
    defaults: () => ({ condition: "'APPROVE' not in last_output.upper()", max_iterations: 5 }),
    hint: "Repeats the body while the condition holds, up to max iterations.",
  },
  for: {
    kind: "for",
    label: "For Loop",
    icon: "⟳",
    branches: () => ["body", "exit"],
    defaults: () => ({ items: "last_output.splitlines()", max_iterations: 10 }),
    hint: "Runs the body once per item; the body exposes item, index and results.",
  },
};

export const CONTROL_KINDS: NodeKind[] = ["if", "switch", "while", "for"];
export const LOOP_KINDS: NodeKind[] = ["while", "for"];

export function kindOf(spec: NodeSpec | undefined): NodeKind {
  const kind = (spec?.type || "agent") as NodeKind;
  return KINDS[kind] ? kind : "agent";
}

export function isControl(spec: NodeSpec | undefined): boolean {
  return CONTROL_KINDS.includes(kindOf(spec));
}

export function branchesOf(spec: NodeSpec | undefined): string[] {
  if (!spec) return [];
  return KINDS[kindOf(spec)].branches(spec);
}

/** The config field a control kind cannot run without. */
export const REQUIRED_FIELD: Record<string, keyof NonNullable<NodeSpec["config"]>> = {
  if: "condition",
  switch: "expression",
  while: "condition",
  for: "items",
};

/** Variables every condition / expression / items field may read. */
export const EXPRESSION_VARS: [string, string][] = [
  ["input", "the run's original task text"],
  ["last_output", "output of the most recent agent"],
  ["outputs", "dict of every node's latest output, e.g. outputs['Writer']"],
  ["history", "list of {name, role, content} turns so far"],
  ["steps", "number of agent steps taken"],
  ["item", "current item of the innermost loop"],
  ["index", "items dispatched by the innermost loop"],
  ["count", "completed iterations of the innermost loop"],
  ["total", "item count of the innermost for loop"],
  ["results", "outputs collected by the innermost loop"],
  ["loop", "every loop's state, e.g. loop['Each']['results']"],
];
