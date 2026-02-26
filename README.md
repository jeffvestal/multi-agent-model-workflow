# Multi-LLM Movie Search Workflow

A demo showing a single Elastic Workflow that orchestrates three Agent Builder calls, each using a different LLM through Elastic Inference Service (EIS).

## What It Does

A "Smart Movie Search Pipeline" that takes a natural language query like *"something like Inception but funnier"* and runs it through three steps:

| Step | Model | Why |
|------|-------|-----|
| **Query Expansion** | OpenAI GPT-4.1 Mini | Cheap & fast -- good enough for simple text transforms |
| **Search & Rank** | Google Gemini 2.5 Flash | Fast with strong tool-use for semantic search |
| **Recommendation** | Anthropic Claude Sonnet 4.5 | Excellent creative writing for the final output |

Each step calls the **same** Agent Builder agent (`movie-search-agent`) but with a different `connector-id`, demonstrating how EIS lets you swap models per task without managing separate API keys or endpoints.

## Architecture

```
User: "something like Inception but funnier"
          │
          ▼
┌─────────────────────────────┐
│  Step 1: Query Expansion    │  ← OpenAI GPT-4.1 Mini
│  Generates 3 search         │
│  variations of the query    │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  Step 2: Search & Rank      │  ← Google Gemini 2.5 Flash
│  Runs index_search on       │
│  movies-recall-demo, dedupes│
│  and ranks top 5            │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  Step 3: Recommendation     │  ← Anthropic Claude Sonnet 4.5
│  Writes a fun movie night   │
│  recommendation             │
└─────────────────────────────┘
```

## Prerequisites

- Elastic Cloud Serverless (or Stack 9.3+) with Workflows enabled
- EIS preconfigured connectors available (GPT-4.1 Mini, Gemini 2.5 Flash, Claude Sonnet 4.5)
- An index called `movies-recall-demo` with a `semantic_text` field named `content`
- Python 3.10+

## Setup

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure credentials
cp .env.example .env
# Edit .env with your Elasticsearch URL and API key

# 4. Provision the agent, tool, and workflow
python setup.py

# 5. (Optional) Run the workflow with a sample query
python setup.py --run

# 6. (Optional) Run with a custom query
python setup.py --run --query "best sci-fi movies from the 90s"
```

## Cleanup

```bash
python setup.py --teardown
```

## Key Concept: `connector-id` on `ai.agent` Steps

The magic is in the workflow YAML. Each `ai.agent` step accepts a top-level `connector-id` field that overrides which LLM the agent uses:

```yaml
steps:
  - name: expand_query
    type: ai.agent
    connector-id: "OpenAI-GPT-4-1-Mini"      # cheap model
    with:
      agent_id: "movie-search-agent"
      message: "..."

  - name: search_movies
    type: ai.agent
    connector-id: "Google-Gemini-2-5-Flash"   # tool-use model
    with:
      agent_id: "movie-search-agent"
      message: "..."

  - name: recommend
    type: ai.agent
    connector-id: "Anthropic-Claude-Sonnet-4-5" # creative model
    with:
      agent_id: "movie-search-agent"
      message: "..."
```

No separate API keys. No provider-specific SDKs. Just swap the connector ID.

## Files

| File | Description |
|------|-------------|
| `workflow.yaml` | The workflow definition (also used by setup.py) |
| `setup.py` | Provisions tool, agent, and workflow via Kibana APIs |
| `.env.example` | Template for environment variables |
| `requirements.txt` | Python dependencies |
