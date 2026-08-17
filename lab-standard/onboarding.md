# lab-standard/onboarding.md — welcome a new lab member (run this LIGHTLY)

A human just said something like *"I'm new here / help me get set up / onboard me."* Your job is a
**short, friendly intake** — a colleague chatting for a few minutes — that quietly seeds the
substrate with who they are and what they work on. The single most important rule: **do not
overwhelm them.**

## Style rules — these override your defaults; follow them exactly

- **One question at a time.** Ask, then WAIT. Never send a list of questions or a multi-part prompt.
- **One short line per question.** No preamble, no explaining how the system works.
- **Five topics, max** — and the member can skip any. Offer it ("happy to skip this"). Stop early if
  they seem done or busy.
- **Seed silently.** When you record something, don't narrate the tool call or paste back results. A
  three-word "got it" is enough.
- **Never re-ask what's already set.** Call `onboarding_status` FIRST and skip every ✓ item.
- **No walls of text.** If you must show something, keep it to ≤ 3 lines.
- **It's resumable.** If they stop, thank them and leave it — they can say "onboard me" again later
  and you'll pick up the ○ items. Never pressure them to finish now.

If you catch yourself writing a paragraph, delete it and ask one short question instead.

## Step 0 — see what's already done

Call `onboarding_status`. Pursue only the ○ (missing) items below. If everything is ✓, just say
they're all set and run `warm_start`.

## The intake — one short question each, skipping ✓ items

1. **Who are you?** → get their name/handle; `add_member(<name>)` and use it as their contributor id.
2. **What do you work on?** → one line about their area. Quietly note it and pick ONE topic to
   pre-warm later. Don't interrogate for detail.
3. **Any current project or code to link?** → if they share a repo/path, offer to conform it
   (`scaffold.py conform`) and register its hypothesis + a one-line `worklog_note`. If not, skip —
   don't push.
4. **A few key papers?** → a `.bib` → `import_publications.py`; or 2–3 titles → `record_publication`.
   This is what makes the coverage map *theirs*. Take whatever they give; don't ask for "more."
5. **Anyone to follow?** → a colleague or a project → `follow`. One is plenty.

For the area from step 2 you MAY pre-warm **one** topic with `curate_literature` in the background —
only one, and don't make them wait on it or watch the output.

## Close — short

Two or three lines: what you set up (e.g. "roster ✓, 3 papers, following Priya") and the single most
useful next thing (usually `warm_start`, or `coverage_map` on their area). Then hand off. Do **not**
summarize the whole system.

## The spirit

They should leave feeling *known* and oriented in about 3–5 minutes — not audited. When in doubt,
ask less and seed less; they can always add more later. A member who enjoys the first session comes
back; one who gets a questionnaire does not.
