import asyncio
import os
import json
import time
import httpx
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from google import genai

load_dotenv(dotenv_path="../.env")

MCP_URL = "http://localhost:8000/mcp"
SIGNOZ_API_KEY = os.environ.get("SIGNOZ_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

gemini_client = genai.Client(api_key=GEMINI_API_KEY)


async def call_tool(session, tool_name, arguments):
    result = await session.call_tool(tool_name, arguments)
    text_parts = [block.text for block in result.content if hasattr(block, "text")]
    return "\n".join(text_parts)


def parse_json_prefix(text):
    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(text)
    return obj


def remediate(root_cause_service):
    print(f"\n=== Step 5: Remediating — disabling chaos on {root_cause_service} ===")
    port_map = {"payment-service": 8011}
    port = port_map.get(root_cause_service)
    if not port:
        print(f"No known admin endpoint for {root_cause_service}, skipping remediation.")
        return
    resp = httpx.post(f"http://localhost:{port}/admin/disable-chaos")
    print(f"Remediation response: {resp.json()}")


def extract_trace_id(search_result_json):
    data = parse_json_prefix(search_result_json)
    rows = data["data"]["data"]["results"][0]["rows"]
    if not rows:
        return None
    return rows[0]["data"]["trace_id"]


def extract_span_summary(trace_details_json):
    data = parse_json_prefix(trace_details_json)
    rows = data["data"]["data"]["results"][0]["rows"]

    spans = {}
    children_by_parent = {}
    for row in rows:
        span = row["data"]
        span_id = span.get("span_id")
        parent_id = span.get("parent_span_id")
        duration_ms = round(span.get("duration_nano", 0) / 1_000_000, 2)
        spans[span_id] = {
            "service": span.get("service.name"),
            "operation": span.get("name"),
            "duration_ms": duration_ms,
            "span_id": span_id,
            "parent_span_id": parent_id,
        }
        children_by_parent.setdefault(parent_id, []).append(span_id)

    summary = []
    for span_id, span in spans.items():
        children_ids = children_by_parent.get(span_id, [])
        children_total_ms = sum(spans[c]["duration_ms"] for c in children_ids if c in spans)
        self_time_ms = round(span["duration_ms"] - children_total_ms, 2)
        summary.append({**span, "self_time_ms": self_time_ms})

    # sort by self_time descending so the most likely root cause is listed first
    summary.sort(key=lambda s: s["self_time_ms"], reverse=True)
    return summary


async def diagnose_with_gemini(span_summary):
    prompt = f"""You are an SRE diagnosing a distributed system cascade failure.
Below is a list of spans from a single distributed trace. Each span shows:
- duration_ms: total time including any nested/downstream calls
- self_time_ms: time spent doing actual work in THAT span alone, excluding
  time spent waiting on nested child calls

self_time_ms is the reliable signal for root cause — a span with high
duration_ms but low self_time_ms was just waiting on something downstream.
The span with the highest self_time_ms is doing the real slow work.

Span data (sorted by self_time_ms, highest first):
{json.dumps(span_summary, indent=2)}

Identify the ONE service responsible for the highest self_time_ms among
meaningful application-level spans (ignore near-zero internal send/receive
housekeeping spans). Respond in this exact format:

ROOT_CAUSE_SERVICE: <service name>
REASONING: <one or two sentence explanation>
"""
    response = gemini_client.models.generate_content(
        model="gemini-flash-lite-latest",
        contents=prompt
    )
    return response.text


def measure_fresh_latency(n=10):
    print(f"\n=== Step 6: Sending {n} fresh requests to directly measure recovery ===")
    durations = []
    for i in range(n):
        start = time.time()
        try:
            httpx.post("http://localhost:8010/order", json={"item": "verify-test", "qty": 1}, timeout=10)
            durations.append(time.time() - start)
        except Exception as e:
            print(f"Request {i} failed: {e}")
    avg_ms = round((sum(durations) / len(durations)) * 1000, 2) if durations else None
    max_ms = round(max(durations) * 1000, 2) if durations else None
    print(f"Fresh request latencies — avg: {avg_ms}ms, max: {max_ms}ms (baseline is ~100ms, pre-fix was 2000-5000ms)")
    return avg_ms, max_ms


async def verify_via_signoz(session, service_name):
    print(f"\n=== Supplementary: querying SigNoz P95 for {service_name} (may include older data) ===")
    result = await call_tool(session, "signoz_aggregate_traces", {
        "filter": f"service.name = '{service_name}'",
        "aggregation": "p95",
        "aggregateOn": "duration_nano"
    })
    print(result[:500])


async def main():
    headers = {"SIGNOZ-API-KEY": SIGNOZ_API_KEY}
    async with streamablehttp_client(MCP_URL, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            print("=== Step 1: Finding a recent slow trace on order-service ===")
            traces_result = await call_tool(session, "signoz_search_traces", {
                "service": "order-service",
                "filter": "duration_nano > 2000000000"
            })
            trace_id = extract_trace_id(traces_result)
            if not trace_id:
                print("No slow traces found. Run ./load_test.sh and try again.")
                return
            print(f"Found slow trace: {trace_id}")

            print("\n=== Step 2: Fetching full trace details ===")
            trace_details = await call_tool(session, "signoz_get_trace_details", {
                "traceId": trace_id
            })

            print("\n=== Step 3: Extracting span summary ===")
            span_summary = extract_span_summary(trace_details)
            print(json.dumps(span_summary, indent=2))

            if not span_summary:
                print("Could not extract spans — raw shape may differ from expected.")
                return

            print("\n=== Step 4: Asking Gemini for root cause diagnosis ===")
            diagnosis = await diagnose_with_gemini(span_summary)
            print(diagnosis)

            for line in diagnosis.splitlines():
                if line.startswith("ROOT_CAUSE_SERVICE:"):
                    root_cause = line.split(":", 1)[1].strip()
                    remediate(root_cause)
                    measure_fresh_latency(10)
                    await verify_via_signoz(session, root_cause)
                    break


if __name__ == "__main__":
    asyncio.run(main())