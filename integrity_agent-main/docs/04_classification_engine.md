# Classification Engine

The classification engine lives in `policy_engine.py`. It has one public function: `classify_question()`. There is no enforcement layer — the engine only observes and labels.

---

## `classify_question()`

```python
async def classify_question(
    question_text: str,
    conversation_history: list[dict],
    session_context: dict,
    openai_client: AsyncAzureOpenAI,
    deployment_name: str,
) -> ClassificationResult
```

Makes a single Azure OpenAI call and returns a `ClassificationResult`.

**Inputs sent to the LLM:**
- `question_text` — the student's current message
- `conversation_history[-6:]` — the last 6 turns (3 exchanges); older turns are trimmed to control token cost
- `session_context` — `{ lab_id, question_count, violation_count }` — gives the model context about where in the session the student is

**Settings:**
- `temperature: 0.0` — deterministic; identical questions always produce identical classifications
- `max_completion_tokens: 400`
- `response_format: json_object` — enforces valid JSON output

---

## `ClassificationResult`

```python
@dataclass
class ClassificationResult:
    classification: QuestionClassification
    confidence: float          # 0.0 – 1.0
    reasoning: str             # 1-2 sentence explanation from the LLM
    concept_tags: list[str]    # 1-3 short technical topic labels
```

---

## The Five Classifications

### `CONCEPTUAL`
Student wants to understand a principle, theory, or formula.

> "Can you explain what impedance matching means?"
> "Why does a bypass capacitor reduce noise?"
> "What is the difference between Thevenin and Norton equivalent circuits?"

Not a violation. The student is learning.

---

### `PROCEDURAL`
Student asks about general methodology — how to approach a problem type — without asking for their specific answer.

> "What steps do I take to analyse a BJT amplifier in small-signal mode?"
> "How do I generally set up a KVL equation for a mesh?"
> "What MATLAB function would I use to plot a Bode plot?"

Not a violation. The student is learning technique.

---

### `CLARIFICATION`
Student is confused about lab instructions, wording, grading criteria, or logistics.

> "Does 'DC operating point' mean I should treat capacitors as open circuits?"
> "When the lab says 'verify', do I need a mathematical derivation or just simulation?"
> "Is R1 in Figure 2 connected to the non-inverting input?"

Not a violation.

---

### `DIRECT_SOLUTION` ⚠️ violation
Student requests their specific numerical answer, complete derivation, finished code, or full circuit solution — even if phrased indirectly.

Key indicators: specific component values from their lab + a request to compute/solve/find; phrases like "give me", "what is the answer", "write this function", "what's the value".

> "What is the DC bias voltage at the drain given R1=10k, R2=22k, VDD=5V?"
> "Write the MATLAB code for Part B of the lab."
> "Just tell me the transfer function for this circuit."

**MAJOR severity violation.** The complete answer would constitute academic dishonesty under Cal Poly's Honor Code.

---

### `ANSWER_FARMING` ⚠️ violation
A sequence of incrementally specific questions that together extract a complete solution step by step. A single question may look benign in isolation; this classification requires reading the conversation history.

The LLM detects this when the conversation shows 3+ questions that collectively walk through one lab problem without the student demonstrating their own work.

**MINOR severity violation.**

---

## Concept Tags

Every classification also extracts `concept_tags` — a list of 1–3 short technical labels identifying what topic the question is about.

**Examples:**
```
"BJT biasing"
"KVL mesh analysis"
"op-amp inverting amplifier"
"Thevenin equivalent"
"MATLAB Bode plot"
"small-signal model"
"transfer function"
```

For logistical/clarification questions about instructions, the list is empty (`[]`).

These tags drive the concept struggle analysis in reports and the `concept_struggle_summary` in the analytics endpoint — allowing instructors to see not just *that* students are struggling but *what* they are struggling with.

---

## Decision Rules (in the system prompt)

The LLM is instructed to apply these rules in order:

1. If the question contains **specific component values from the lab** combined with a request to solve/compute/find → `DIRECT_SOLUTION` regardless of phrasing
2. If the **conversation history shows 3+ questions** collectively solving one lab problem → `ANSWER_FARMING` even if the current question looks procedural in isolation
3. When uncertain between a violation and non-violation category, **prefer the non-violation classification** unless the evidence is clear

Rule 3 is deliberately conservative: the system is observational, not punitive. A false positive here would log an incorrect violation in a student's record.

---

## Fail-Safe Behaviour

If the Azure OpenAI call fails for any reason (network error, timeout, service outage):

```python
ClassificationResult(
    classification=QuestionClassification.PROCEDURAL,
    confidence=0.0,
    reasoning="Classifier unavailable — fail-safe applied.",
    concept_tags=[],
)
```

The session continues normally. The question is recorded as `PROCEDURAL` with `confidence=0.0`, which signals in the data that it was a classifier failure. No violation is logged. This ensures Lab Companion is never blocked by a Guardian outage.

A `RateLimitError` from OpenAI is handled separately — it returns `429` to Lab Companion (rather than silently downgrading to PROCEDURAL), since rate limit exhaustion on the Guardian's dedicated deployment suggests a systemic issue worth surfacing.
