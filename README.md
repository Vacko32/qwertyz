# Preference Annotation App

Local web app for blinded preference annotation.

The public data only uses anonymous model slots such as `Model 1` and `Model 2`. It does not include model provider names, API keys, generation logs, dropped-row traces, GEMBA scores, or annotation results.

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

## Run Part 2

Part 2 uses only the new preference rows from `final_part2.csv`. It keeps the
same blinded UI and writes results to `results_part2/`, separate from the
original annotation results.

```bash
uv run python server.py 1 --part 2
uv run python server.py 2 --part 2
uv run python server.py 3 --part 2
```

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
results_part2/annotator_1_preferences.json
results_part2/annotator_2_preferences.json
results_part2/annotator_3_preferences.json
```

Each annotator sends only their own JSON result file to the project owner.

## Split

The current blinded corpus has 138 rows:

- Annotator 1 / David: 46 rows
- Annotator 2 / Martin F: 46 rows
- Annotator 3 / Vacko: 46 rows

Part 2 has 270 rows:

- Annotator 1 / David: 90 rows
- Annotator 2 / Martin F: 90 rows
- Annotator 3 / Vacko: 90 rows

`final_part2_with_thinking.csv` contains the same part 2 rows plus 14 repaired
part 1 thinking-token rows for relabeling:

```bash
uv run python server.py 1 --part 2 --data-csv final_part2_with_thinking.csv
uv run python server.py 2 --part 2 --data-csv final_part2_with_thinking.csv
uv run python server.py 3 --part 2 --data-csv final_part2_with_thinking.csv
```

- Annotator 1 / David: 95 rows
- Annotator 2 / Martin F: 95 rows
- Annotator 3 / Vacko: 94 rows

The browser only shows `Response A` and `Response B`. The CSVs use anonymous slots only (`model_1`, `model_2`, etc.), and this repository does not include the private mapping from slots to real model names.
