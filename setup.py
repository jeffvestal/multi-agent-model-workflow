"""
Setup script for the Multi-LLM Movie Search Workflow demo.

Provisions an Agent Builder tool, agent, and workflow on an Elastic Cloud /
Serverless cluster using the Kibana APIs.  Optionally runs the workflow with
a sample query.

Requirements:
    pip install requests python-dotenv pyyaml

Usage:
    # Set environment variables (or use a .env file)
    export ELASTICSEARCH_URL="https://my-deploy.es.us-east-1.aws.elastic.cloud:443"
    export ELASTIC_API_KEY="your-api-key"

    python setup.py              # provision everything
    python setup.py --run        # provision + run with a sample query
    python setup.py --teardown   # delete agent, tool, and workflow
"""

import argparse
import json
import sys
import time
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv
import os

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL", "")
ELASTIC_API_KEY = os.getenv("ELASTIC_API_KEY", "")

TOOL_ID = "movie-search-tool"
AGENT_ID = "movie-search-agent"
WORKFLOW_FILE = Path(__file__).parent / "workflow.yaml"

SAMPLE_QUERY = "something like Inception but funnier"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def derive_kibana_url(es_url: str) -> str:
    kb_url = es_url.replace(".es.", ".kb.")
    if kb_url == es_url:
        sys.exit(
            "ERROR: Could not derive Kibana URL from ELASTICSEARCH_URL.\n"
            "Set KIBANA_URL explicitly if this is not a standard Cloud deployment."
        )
    return kb_url.rstrip("/")


def kibana_headers() -> dict:
    return {
        "Authorization": f"ApiKey {ELASTIC_API_KEY}",
        "Content-Type": "application/json",
        "kbn-xsrf": "true",
        "x-elastic-internal-origin": "kibana",
    }


def check_response(resp: requests.Response, action: str):
    if resp.ok:
        print(f"  [OK]  {action}")
        return resp.json() if resp.text else {}
    print(f"  [ERR] {action} -- {resp.status_code}")
    try:
        print(f"        {json.dumps(resp.json(), indent=2)}")
    except Exception:
        print(f"        {resp.text[:500]}")
    return None


def resource_exists(url: str, headers: dict) -> bool:
    resp = requests.get(url, headers=headers)
    return resp.ok

# ---------------------------------------------------------------------------
# Provision
# ---------------------------------------------------------------------------

def create_tool(kibana_url: str, headers: dict):
    print("\n--- Creating search tool ---")
    url = f"{kibana_url}/api/agent_builder/tools"

    if resource_exists(f"{url}/{TOOL_ID}", headers):
        print(f"  [SKIP] Tool '{TOOL_ID}' already exists")
        return

    payload = {
        "id": TOOL_ID,
        "type": "index_search",
        "description": (
            "Search the movie database. Use this tool to find movies by plot, "
            "genre, theme, title, or any natural language description."
        ),
        "configuration": {
            "pattern": "movies-recall-demo",
        },
    }
    resp = requests.post(url, headers=headers, json=payload)
    check_response(resp, f"Create tool '{TOOL_ID}'")


def create_agent(kibana_url: str, headers: dict):
    print("\n--- Creating agent ---")
    url = f"{kibana_url}/api/agent_builder/agents"

    if resource_exists(f"{url}/{AGENT_ID}", headers):
        print(f"  [SKIP] Agent '{AGENT_ID}' already exists")
        return

    payload = {
        "id": AGENT_ID,
        "name": "Movie Search Agent",
        "description": "Versatile movie assistant that searches a 40k movie database and generates recommendations.",
        "configuration": {
            "instructions": (
                "You are a versatile movie assistant. Follow the instructions in "
                "each message precisely. When asked to search, use your search tool. "
                "When asked to generate text, write clearly and concisely.\n\n"
                "FORMATTING RULES:\n"
                "- Be concise. No filler.\n"
                "- When returning JSON, return ONLY valid JSON with no markdown fencing.\n"
                "- When returning lists, use numbered format.\n"
                "- When writing recommendations, be conversational and fun."
            ),
            "tools": [{"tool_ids": [TOOL_ID]}],
        },
    }
    resp = requests.post(url, headers=headers, json=payload)
    check_response(resp, f"Create agent '{AGENT_ID}'")


def create_workflow(kibana_url: str, headers: dict) -> str | None:
    print("\n--- Creating workflow ---")

    workflow_yaml = yaml.safe_load(WORKFLOW_FILE.read_text())
    workflow_name = workflow_yaml["name"]

    search_resp = requests.post(
        f"{kibana_url}/api/workflows/search",
        headers=headers,
        json={"limit": 100, "page": 1, "query": workflow_name},
    )
    if search_resp.ok:
        results = search_resp.json().get("results", [])
        existing = [w for w in results if w.get("name") == workflow_name]
        if existing:
            wf_id = existing[0]["id"]
            print(f"  [SKIP] Workflow '{workflow_name}' already exists (id: {wf_id})")
            return wf_id

    workflow_yaml_str = WORKFLOW_FILE.read_text()
    payload = {"yaml": workflow_yaml_str}
    resp = requests.post(
        f"{kibana_url}/api/workflows",
        headers=headers,
        json=payload,
    )
    result = check_response(resp, f"Create workflow '{workflow_name}'")
    if result:
        wf_id = result.get("id", result.get("workflowId"))
        print(f"  Workflow ID: {wf_id}")
        return wf_id
    return None


def run_workflow(kibana_url: str, headers: dict, workflow_id: str, query: str):
    print(f"\n--- Running workflow with query: \"{query}\" ---")
    resp = requests.post(
        f"{kibana_url}/api/workflows/{workflow_id}/run",
        headers=headers,
        json={"inputs": {"query": query}},
    )
    result = check_response(resp, "Run workflow")
    if result:
        exec_id = result.get("workflowExecutionId")
        print(f"  Execution ID: {exec_id}")
        print(f"  View in Kibana: {kibana_url}/app/management/kibana/workflows")
        return exec_id
    return None

# ---------------------------------------------------------------------------
# Teardown
# ---------------------------------------------------------------------------

def teardown(kibana_url: str, headers: dict):
    print("\n--- Teardown ---")

    search_resp = requests.post(
        f"{kibana_url}/api/workflows/search",
        headers=headers,
        json={"limit": 100, "page": 1, "query": "smart_movie_search"},
    )
    if search_resp.ok:
        results = search_resp.json().get("results", [])
        for wf in results:
            if wf.get("name") == "smart_movie_search":
                resp = requests.delete(
                    f"{kibana_url}/api/workflows/{wf['id']}",
                    headers=headers,
                )
                check_response(resp, f"Delete workflow '{wf['id']}'")

    resp = requests.delete(
        f"{kibana_url}/api/agent_builder/agents/{AGENT_ID}",
        headers=headers,
    )
    check_response(resp, f"Delete agent '{AGENT_ID}'")

    resp = requests.delete(
        f"{kibana_url}/api/agent_builder/tools/{TOOL_ID}",
        headers=headers,
    )
    check_response(resp, f"Delete tool '{TOOL_ID}'")

    print("\nTeardown complete.")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Multi-LLM Movie Search Workflow setup")
    parser.add_argument("--run", action="store_true", help="Run the workflow after provisioning")
    parser.add_argument("--query", type=str, default=SAMPLE_QUERY, help="Query to run (with --run)")
    parser.add_argument("--teardown", action="store_true", help="Delete all created resources")
    args = parser.parse_args()

    if not ELASTICSEARCH_URL or not ELASTIC_API_KEY:
        sys.exit(
            "ERROR: Set ELASTICSEARCH_URL and ELASTIC_API_KEY environment variables "
            "(or create a .env file)."
        )

    kibana_url = os.getenv("KIBANA_URL") or derive_kibana_url(ELASTICSEARCH_URL)
    headers = kibana_headers()

    print(f"Kibana URL: {kibana_url}")

    if args.teardown:
        teardown(kibana_url, headers)
        return

    create_tool(kibana_url, headers)
    create_agent(kibana_url, headers)
    workflow_id = create_workflow(kibana_url, headers)

    if args.run and workflow_id:
        time.sleep(1)
        run_workflow(kibana_url, headers, workflow_id, args.query)

    print("\nDone! Open Kibana > Workflows to see the workflow.")
    print(f"  URL: {kibana_url}/app/management/kibana/workflows")


if __name__ == "__main__":
    main()
