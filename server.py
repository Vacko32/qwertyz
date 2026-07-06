from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
DEFAULT_DATA_CSV = APP_DIR / "final.csv"
DEFAULT_PART2_DATA_CSV = APP_DIR / "final_second.csv"
DEFAULT_RESULTS_DIR = APP_DIR / "results"
DEFAULT_PART2_RESULTS_DIR = APP_DIR / "results_part2"

SCALE = {
    1: "strong preference for Response A",
    2: "slight preference for Response A",
    3: "neutral / tie",
    4: "slight preference for Response B",
    5: "strong preference for Response B",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required CSV: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


@dataclass(frozen=True)
class AssignmentRow:
    original_index: int
    assignment_index: int
    row: dict[str, str]

    @property
    def sample_id(self) -> str:
        return self.row["sample_id"]


class AnnotationState:
    def __init__(self, annotator_id: int, data_csv: Path, results_dir: Path) -> None:
        self.annotator_id = annotator_id
        self.data_csv = data_csv.resolve()
        self.results_dir = results_dir.resolve()
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.output_file = self.results_dir / f"annotator_{annotator_id}_preferences.json"

        self.rows = read_csv(self.data_csv)
        self._validate_input()
        assigned = [
            AssignmentRow(original_index=i, assignment_index=0, row=row)
            for i, row in enumerate(self.rows)
            if (i % 3) + 1 == annotator_id
        ]
        self.assigned_rows = [
            AssignmentRow(original_index=item.original_index, assignment_index=i + 1, row=item.row)
            for i, item in enumerate(assigned)
        ]
        self.rows_by_sample_id = {item.sample_id: item for item in self.assigned_rows}

        self.created_at = utc_now()
        self.responses: dict[str, dict[str, Any]] = {}
        self._load_existing()

    def _validate_input(self) -> None:
        required = {
            "sample_id",
            "source_type",
            "source_language",
            "target_language",
            "source_text",
            "model_pair",
            "model_a_model_id",
            "model_a_translation",
            "model_b_model_id",
            "model_b_translation",
        }
        if not self.rows:
            raise ValueError(f"{self.data_csv} has no data rows")
        missing = required - set(self.rows[0])
        if missing:
            raise ValueError(f"{self.data_csv} is missing columns: {', '.join(sorted(missing))}")

        sample_ids = [row["sample_id"] for row in self.rows]
        if len(sample_ids) != len(set(sample_ids)):
            raise ValueError("sample_id values must be unique")

        referenced_slots = {
            row["model_a_model_id"] for row in self.rows
        } | {
            row["model_b_model_id"] for row in self.rows
        }
        invalid_slots = {
            slot for slot in referenced_slots if not re.fullmatch(r"model_[1-9][0-9]*", slot)
        }
        if invalid_slots:
            raise ValueError(
                f"{self.data_csv} references non-anonymous model slots: "
                f"{', '.join(sorted(invalid_slots))}"
            )

    def _load_existing(self) -> None:
        if not self.output_file.exists():
            return
        with self.output_file.open("r", encoding="utf-8") as handle:
            existing = json.load(handle)
        self.created_at = existing.get("created_at") or self.created_at
        for response in existing.get("responses", []):
            sample_id = response.get("sample_id")
            if sample_id in self.rows_by_sample_id:
                self.responses[sample_id] = response

    @property
    def split_counts(self) -> dict[str, int]:
        counts = {str(i): 0 for i in range(1, 4)}
        for i, _row in enumerate(self.rows):
            counts[str((i % 3) + 1)] += 1
        return counts

    def public_state(self) -> dict[str, Any]:
        return {
            "annotator_id": self.annotator_id,
            "assignment": {
                "method": "round_robin_original_row_index_mod_3",
                "total_rows": len(self.rows),
                "assigned_rows": len(self.assigned_rows),
                "split_counts": self.split_counts,
            },
            "output_file": str(self.output_file),
            "dataset": {
                "name": self.data_csv.stem,
                "total_rows": len(self.rows),
            },
            "scale": SCALE,
            "rows": [self._public_row(item) for item in self.assigned_rows],
            "responses": {
                sample_id: {
                    "sample_id": sample_id,
                    "preference_score_1_to_5": response["preference_score_1_to_5"],
                    "notes": response.get("notes", ""),
                    "annotated_at": response.get("annotated_at"),
                }
                for sample_id, response in self.responses.items()
            },
        }

    def _public_row(self, item: AssignmentRow) -> dict[str, Any]:
        row = item.row
        return {
            "sample_id": row["sample_id"],
            "row_number": item.original_index + 1,
            "assignment_index": item.assignment_index,
            "source_type": row["source_type"],
            "source_language": row["source_language"],
            "target_language": row["target_language"],
            "source_text": row["source_text"],
            "response_a": row["model_a_translation"],
            "response_b": row["model_b_translation"],
        }

    def save_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        sample_id = str(payload.get("sample_id", ""))
        if sample_id not in self.rows_by_sample_id:
            raise ValueError("sample_id is not assigned to this annotator")

        try:
            score = int(payload.get("preference_score_1_to_5"))
        except (TypeError, ValueError) as exc:
            raise ValueError("preference_score_1_to_5 must be an integer from 1 to 5") from exc
        if score not in SCALE:
            raise ValueError("preference_score_1_to_5 must be an integer from 1 to 5")

        notes = str(payload.get("notes", ""))[:5000]
        item = self.rows_by_sample_id[sample_id]
        row = item.row
        self.responses[sample_id] = {
            "sample_id": sample_id,
            "row_number": item.original_index + 1,
            "assignment_index": item.assignment_index,
            "annotator_id": self.annotator_id,
            "preference_score_1_to_5": score,
            "preference_label": SCALE[score],
            "notes": notes,
            "annotated_at": utc_now(),
            "source_type": row["source_type"],
            "source_language": row["source_language"],
            "target_language": row["target_language"],
        }
        self._write_results()
        return {
            "ok": True,
            "saved": len(self.responses),
            "assigned": len(self.assigned_rows),
            "output_file": str(self.output_file),
        }

    def result_document(self) -> dict[str, Any]:
        ordered_responses = [
            self.responses[item.sample_id]
            for item in self.assigned_rows
            if item.sample_id in self.responses
        ]
        return {
            "schema_version": 1,
            "annotator_id": self.annotator_id,
            "created_at": self.created_at,
            "updated_at": utc_now(),
            "dataset": {
                "data_csv": self.data_csv.name,
                "data_csv_sha256": sha256_file(self.data_csv),
                "total_rows": len(self.rows),
            },
            "assignment": {
                "method": "round_robin_original_row_index_mod_3",
                "assigned_rows": len(self.assigned_rows),
                "split_counts": self.split_counts,
                "assigned_sample_ids": [item.sample_id for item in self.assigned_rows],
            },
            "scale": SCALE,
            "responses": ordered_responses,
        }

    def _write_results(self) -> None:
        document = self.result_document()
        tmp_path = self.output_file.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp_path, self.output_file)


def make_handler(state: AnnotationState) -> type[SimpleHTTPRequestHandler]:
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

        def log_message(self, fmt: str, *args: Any) -> None:
            print(f"{self.address_string()} - {fmt % args}")

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/state":
                self._send_json(state.public_state())
                return
            if parsed.path == "/api/export":
                document = state.result_document()
                body = json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header(
                    "Content-Disposition",
                    f'attachment; filename="{state.output_file.name}"',
                )
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if parsed.path.startswith("/api/"):
                self._send_json({"error": "unknown API endpoint"}, HTTPStatus.NOT_FOUND)
                return
            if parsed.path == "/":
                self.path = "/index.html"
            super().do_GET()

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != "/api/save":
                self._send_json({"error": "unknown API endpoint"}, HTTPStatus.NOT_FOUND)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length).decode("utf-8")
                payload = json.loads(body)
                result = state.save_response(payload)
            except json.JSONDecodeError:
                self._send_json({"error": "request body must be valid JSON"}, HTTPStatus.BAD_REQUEST)
                return
            except ValueError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            self._send_json(result)

        def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local preference annotation website.")
    parser.add_argument(
        "annotator_id",
        type=int,
        choices=(1, 2, 3),
        help="Annotator split to serve: 1, 2, or 3.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind. Default: 127.0.0.1")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind. Default: 8000")
    parser.add_argument(
        "--part",
        type=int,
        choices=(1, 2),
        default=1,
        help="Dataset part to annotate. Part 1 uses final.csv; part 2 uses final_second.csv.",
    )
    parser.add_argument("--data-csv", type=Path, default=None, help="Override preference CSV path.")
    parser.add_argument(
        "--outdir",
        type=Path,
        default=None,
        help="Directory for annotator JSON files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_csv = args.data_csv or (DEFAULT_PART2_DATA_CSV if args.part == 2 else DEFAULT_DATA_CSV)
    outdir = args.outdir or (DEFAULT_PART2_RESULTS_DIR if args.part == 2 else DEFAULT_RESULTS_DIR)
    state = AnnotationState(args.annotator_id, data_csv, outdir)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(state))
    url = f"http://{args.host}:{args.port}"
    print(f"Dataset part {args.part}: {state.data_csv.name}")
    print(f"Annotator {args.annotator_id}: {len(state.assigned_rows)} of {len(state.rows)} rows")
    print(f"Results file: {state.output_file}")
    print(f"Open: {url}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
