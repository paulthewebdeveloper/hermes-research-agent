# Example: YouTube Study Guide Prompt

Use when a user wants a study guide from a lecture, tutorial, or long educational video.

```text
Analyze this YouTube video and produce a study guide that uses both transcript evidence and visual evidence.

Video: <URL>

Requirements:
- Extract captions/transcript if available.
- Identify timestamp ranges where slides, diagrams, demos, code, terminal output, or UI screens appear.
- Use focused frame extraction for the most important visual sections.
- Inspect the contact sheet first, then selected frames.
- Create a structured study guide with:
  - concise concept explanations
  - timestamps for key claims
  - visual evidence summaries for important screenshots
  - a section for limitations, including missing captions or inaccessible frames
- Do not rely on transcript-only analysis if the presenter teaches visually.
```
