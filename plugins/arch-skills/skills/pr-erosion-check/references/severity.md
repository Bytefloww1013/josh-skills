# Shared severity and confidence scale

All skills in this set, and architecture-review-report, use this scale so their outputs can be merged.

## Severity

| Level | Meaning | Typical examples |
|---|---|---|
| Critical | Breaks a structural invariant, or locks in a costly Type 1 mistake, or risks data loss or security | Domain core imports infrastructure; Timing/Value/Identity connascence across services; destructive migration with no path back; tests deleted to make CI pass |
| High | Will cause erosion or a wide blast radius soon | New dependency cycle; Meaning/Position/Algorithm connascence across modules; boundary bypass; silent error swallowing on a write path; Accepted ADR violated |
| Medium | Raises cost of change or cognitive load | Drift from an established pattern; unmeasurable quality goal; Type 1 decision without ADR; speculative abstraction; hotspot grown |
| Low | Local or cosmetic | Naming inconsistency; small nesting increase in a new function |
| Positive | A strength worth keeping | New port isolates a vendor; contract test added |
| Gap | Input is silent on something needed; phrase as a question | "What happens to in-flight jobs during the switch?" |

Adjust by one level for: degree (many call sites up), static enforcement already present (down), Type 1 context (up).

## Confidence

| Level | Meaning |
|---|---|
| High | Seen directly in code, diff or text you quoted |
| Medium | Strongly implied; one inference step |
| Low | Inferred from patterns; needs a human or a tool to confirm |

## Filtering rule

Report a Low-confidence finding only if its severity would be Critical or High. Otherwise drop it or list it under "Not checked". A short list of true findings is worth more than a long list a reader learns to ignore.
