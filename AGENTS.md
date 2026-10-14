# BJJ Vault

When answering instructional questions, use the `bjj-vault` MCP tools. Search across several results,
then use `get_transcript` to verify the actual passage. Attribute answers to the instructor.
Call `make_clip` for the best 1–3 ranges (usually 15–120 seconds; maximum 300 seconds).
Return the clickable `play_url` and explain that it expires, plus a note link when useful.
The `play_url` uses the current HTTPS mobile tunnel when it is enabled. Return this URL
for phone users; the `in_context_url` and ordinary watch URLs remain local to the PC.
If mobile access has stopped, run `Start-Mobile.ps1` on the PC before creating the link.
The link streams from this PC; do not attach or export a video file unless asked.
If the vault does not cover the question, say so instead of inventing an instructional answer.

The installation and all generated data live on X: (clonkker). Keep videos, model caches,
temporary audio, and environments on that drive. Note generation uses the local Codex CLI's
ChatGPT sign-in. Never introduce API-key authentication or switch to an API provider.

Run `python -m unittest discover -s tests -v` for streaming changes. The production server
uses one serial worker. Keep it running for playback and ingestion; do not start competing workers.
