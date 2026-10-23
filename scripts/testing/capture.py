"""Decode PCAP with Wireshark's CLI and match every curl request and response."""

import argparse
import json
import subprocess
from pathlib import Path


def verify(root: Path):
    events = [
        json.loads(line) for line in (root / "replay.jsonl").read_text().splitlines()
    ]
    if not events:
        raise ValueError("Replay contains no requests")
    fields = (
        "frame.number",
        "http.request.method",
        "http.request.uri",
        "http.response.code",
        "http.request_in",
    )
    command = [
        "tshark",
        "-n",
        "-2",
        "-r",
        str(root / "demo.pcap"),
        "-d",
        "tcp.port==8000,http",
        "-Y",
        "http.request or http.response",
        "-T",
        "fields",
        "-E",
        "separator=/t",
        "-E",
        "occurrence=f",
    ]
    for field in fields:
        command.extend(["-e", field])
    decoded = subprocess.run(
        command, check=True, capture_output=True, text=True, timeout=60
    )
    (root / "http-packets.tsv").write_text("\t".join(fields) + "\n" + decoded.stdout)
    requests = []
    responses = {}
    for line in decoded.stdout.splitlines():
        frame, method, uri, status, request_frame = line.split("\t")
        if method:
            requests.append((frame, method, uri))
        if status:
            if request_frame in responses:
                raise ValueError(f"Duplicate response for frame {request_frame}")
            responses[request_frame] = (frame, int(status))
    if len(requests) != len(events) or len(responses) != len(events):
        raise ValueError(
            f"Incomplete capture: {len(requests)} requests, "
            f"{len(responses)} responses; expected {len(events)} pairs"
        )
    matched = []
    for (frame, method, uri), event in zip(requests, events, strict=True):
        response_frame, status = responses.get(frame, (None, None))
        if (method, uri, status) != (event["method"], event["path"], event["status"]):
            raise ValueError(f"Capture differs from replay at request frame {frame}")
        matched.append(
            {
                "request_frame": frame,
                "response_frame": response_frame,
                "method": method,
                "path": uri,
                "status": status,
            }
        )
    (root / "capture-verification.json").write_text(json.dumps(matched, indent=2))
    print(f"CAPTURE VERIFIED: {len(matched)} HTTP request/response pairs")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", type=Path, default=Path("/artifacts"))
    verify(parser.parse_args().directory)
