# Preference Annotation App

Local web app for blinded preference annotation.

The public data only uses anonymous slots `Model 1` through `Model 5`. It does not include model provider names, API keys, generation logs, dropped-row traces, or annotation results.

## Run

```bash
cd preference-annotation-public
uv run python server.py 1
```

Use `1`, `2`, or `3` for the annotator split:

```bash
uv run python server.py 2
uv run python server.py 3
```

Use these assignments:

- David: `uv run python server.py 1`
- Martin F: `uv run python server.py 2`
- Vacko / project owner: `uv run python server.py 3`

Open the printed local URL, usually:

```text
http://127.0.0.1:8000
```

## Output

Ratings are saved locally and are intentionally ignored by Git:

```text
results/annotator_1_preferences.json
results/annotator_2_preferences.json
results/annotator_3_preferences.json
```

Each annotator sends only their own JSON result file to the project owner.

## Split

The current blinded corpus has 138 rows:

- Annotator 1 / David: 46 rows
- Annotator 2 / Martin F: 46 rows
- Annotator 3 / Vacko: 46 rows

The browser only shows `Response A` and `Response B`. The CSV uses anonymous slots only (`model_1` through `model_5`), and this repository does not include the private mapping from slots to real model names.
