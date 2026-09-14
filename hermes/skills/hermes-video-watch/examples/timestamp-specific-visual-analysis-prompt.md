# Example: Timestamp-Specific Visual Analysis Prompt

Use when the user asks what appears at a precise timestamp or short range.

```text
Inspect the video visually from <start timestamp> to <end timestamp>.

Video: <URL or local file>

Run focused extraction with high enough resolution to read on-screen text. Inspect the contact sheet, then the clearest individual frames.

Answer with:
- what is shown on screen
- any readable text, labels, code, UI controls, charts, or diagram elements
- what is spoken in captions during the same range, if captions are available
- whether the spoken explanation matches the visual content
- frame paths and timestamps used as evidence
```
