# Blog Outline: Multi-Model Workflows with Elastic Inference Service

> Handoff document for the blog writer. Each section has talking points, real execution data, and code snippets ready to use.

---

## 1. Hook / Intro

**Key message:** EIS now ships preconfigured connectors for models from OpenAI, Anthropic, and Google -- ready to use out of the box, no API keys or provider SDKs required.

Talking points:
- Elastic Inference Service (EIS) provides preconfigured LLM connectors on every Elastic Cloud deployment
- Models from three major providers are available immediately: OpenAI (GPT-4.1, GPT-5.2), Anthropic (Claude Sonnet 4.5, Opus 4.5/4.6), Google (Gemini 2.5 Flash/Pro)
- You can now build workflows that use different models for different tasks -- matching the right model to the right job
- To demonstrate this, we built a single Elastic Workflow that chains 3 agent calls, each powered by a different LLM

---

## 2. The Demo: Smart Movie Search Pipeline

**What it does:** Takes a natural language query like "best sci-fi movies from the 90s" and runs it through a 3-step pipeline -- query expansion, semantic search over a 40k movie index, and a polished recommendation.

**Architecture:**

```
User: "best sci-fi movies from the 90s"
          |
          v
+-----------------------------+
|  Step 1: Query Expansion    |  <-- OpenAI GPT-4.1 Mini
|  Generates 3 search         |
|  variations of the query    |
+-------------+---------------+
              |
              v
+-----------------------------+
|  Step 2: Search & Rank      |  <-- Google Gemini 2.5 Flash
|  Runs semantic search on    |
|  movies-recall-demo index,  |
|  deduplicates & ranks top 5 |
+-------------+---------------+
              |
              v
+-----------------------------+
|  Step 3: Recommendation     |  <-- Anthropic Claude Sonnet 4.5
|  Writes a fun, opinionated  |
|  movie recommendation       |
+-----------------------------+
```

**Key design point:** All three steps call the *same* Agent Builder agent (`movie-search-agent`). The model is swapped per step using the `connector-id` field -- no need for separate agents per model.

---

## 3. Step-by-Step Breakdown

### Step 1: Query Expansion -- OpenAI GPT-4.1 Mini

**Task:** Take the user's raw query and generate 3 semantically different search variations.

**Why GPT-4.1 Mini:**
- Cheapest and fastest model available via EIS
- Query expansion is a simple text transformation -- no tool use, no complex reasoning needed
- The task has a well-defined output format (JSON array), which even small models handle reliably

**YAML:**

```yaml
- name: expand_query
  type: ai.agent
  connector-id: "OpenAI-GPT-4-1-Mini"
  with:
    agent_id: "movie-search-agent"
    message: |
      You are a query expansion engine. Take the user's movie search query and
      generate exactly 3 semantically different search variations...
      User query: {{ inputs.query }}
      Return ONLY a JSON array of 3 strings, nothing else.
```

**Real execution output** (10s):

```json
[
  "top science fiction films released in the 1990s",
  "classic 90s sci-fi movies with futuristic themes",
  "popular science fiction movies from the 1990s era"
]
```

**Writer note:** Each variation approaches the query from a different angle -- formal ("science fiction films"), thematic ("futuristic themes"), and temporal ("1990s era"). This gives the search step more surface area to find relevant movies.

---

### Step 2: Search & Rank -- Google Gemini 2.5 Flash

**Task:** Use the `index_search` tool to run semantic search against a 40k movie index, then deduplicate and rank the results.

**Why Gemini 2.5 Flash:**
- Strong tool-use capability -- reliably invokes the search tool with well-formed queries
- Fast execution, important since this step runs multiple searches
- Works well with Elastic's `semantic_text` field type and `index_search` tool

**YAML:**

```yaml
- name: search_movies
  type: ai.agent
  connector-id: "Google-Gemini-2-5-Flash"
  with:
    agent_id: "movie-search-agent"
    message: |
      You have access to a movie search tool. Use it to find movies matching these
      search queries. Run a search for each query, then deduplicate and rank the
      combined results.
      Search queries:
      {{ steps.expand_query.output.message }}
      Return the top 5 unique movies...
```

**Real execution output** (25s):

> 1. **Austin Powers: International Man of Mystery** -- a popular science fiction film from the 1990s era, featuring a 1960s secret agent brought into the 1990s.
> 2. **Dune** -- a classic science fiction miniseries from the 1990s, based on a renowned science fiction novel.
> 3. **Twilight Zone: The Movie** -- a classic sci-fi movie, although released in the 1980s, it aligns with the spirit of classic science fiction.
> 4. **Caprica** -- a science fiction spin-off, aligning with the theme of science fiction content.
> 5. **Tin Man** -- a science fiction adaptation of a classic story, fitting the science fiction criteria.

**Writer note:** The results aren't perfect (some are from the wrong decade, some are TV series). This is partly a data quality issue and partly LLM judgment. But it sets up step 3 nicely -- Claude adds editorial value on top.

---

### Step 3: Recommendation -- Anthropic Claude Sonnet 4.5

**Task:** Synthesize the search results into an engaging, conversational movie recommendation.

**Why Claude Sonnet 4.5:**
- Excellent creative and editorial writing
- Strong instruction following for structured output (top pick, viewing order, closing line)
- Added bonus: Claude applied editorial judgment, catching inaccuracies from step 2

**YAML:**

```yaml
- name: recommend
  type: ai.agent
  connector-id: "Anthropic-Claude-Sonnet-4-5"
  with:
    agent_id: "movie-search-agent"
    message: |
      You are a movie critic writing a recommendation for a friend. Based on these
      search results, write a short, engaging movie recommendation.
      The user originally asked for: {{ inputs.query }}
      Search results:
      {{ steps.search_movies.output.message }}
      Your recommendation should include:
      1. A "top pick" with a compelling reason to watch it
      2. A suggested viewing order if someone wants to watch all 5
      3. A fun one-liner to close it out
```

**Real execution output** (16s):

> **Top Pick: Dune (1990s miniseries)**
> If you're going to watch one thing, make it this. It's the ambitious adaptation of Frank Herbert's legendary novel -- sprawling desert planets, political intrigue, and giant sandworms.
>
> **If you're doing a marathon:**
> Start with Dune to set the tone, then Austin Powers as a palate cleanser. The other three on this list are either from the wrong decade (Twilight Zone: The Movie is 1983) or not actually movies (Caprica and Tin Man are TV series from the 2000s), so I'd skip those and hunt down actual 90s gems like The Matrix, 12 Monkeys, or Dark City instead.
>
> **Bottom line:** The 90s gave us sci-fi that made you *think* -- before everything became a franchise. Dune delivers that in spades.

**Writer note:** Claude didn't just summarize -- it *improved* the output. It flagged that Twilight Zone is from 1983, that Caprica and Tin Man are TV series, and even suggested better alternatives (The Matrix, 12 Monkeys, Dark City). This is a strong illustration of why you'd want a premium model for the final step: it adds editorial value on top of raw search results.

---

## 4. The Key Mechanism: `connector-id`

**Key message:** One field, three providers.

The `connector-id` is a top-level field on `ai.agent` workflow steps. It overrides which LLM the agent uses at runtime, without changing the agent definition itself.

**The complete workflow YAML showing all three connector-ids:**

```yaml
steps:
  - name: expand_query
    type: ai.agent
    connector-id: "OpenAI-GPT-4-1-Mini"       # cheap/fast
    with:
      agent_id: "movie-search-agent"
      message: "..."

  - name: search_movies
    type: ai.agent
    connector-id: "Google-Gemini-2-5-Flash"    # tool-use
    with:
      agent_id: "movie-search-agent"
      message: "..."

  - name: recommend
    type: ai.agent
    connector-id: "Anthropic-Claude-Sonnet-4-5" # creative
    with:
      agent_id: "movie-search-agent"
      message: "..."
```

Talking points:
- Same agent definition reused across all three steps
- The model is selected at the *workflow* level, not the agent level
- Swapping a model is a one-line YAML change -- no code, no API key rotation, no SDK changes
- EIS preconfigured connectors mean these IDs are available on every deployment automatically

---

## 5. Why Multi-Model Matters

Four talking points for the writer to expand on:

**Cost optimization**
- GPT-4.1 Mini for step 1 costs a fraction of what a premium model would
- Simple tasks don't need expensive models -- reserve budget for where it counts

**Best tool for the job**
- Different models have different strengths: tool-use, creative writing, speed, reasoning
- Matching model to task produces better results than using one model for everything

**Quality through diversity**
- In this demo, Claude (step 3) caught and corrected errors from Gemini (step 2)
- Different models bring different perspectives -- acts as a natural quality check

**Operational flexibility**
- New model releases? Swap a connector ID, done
- Model performance regression? Route to a different provider instantly
- No vendor lock-in -- EIS abstracts the provider layer

---

## 6. Try It Yourself

**Setup summary** (link to repo README for full details):

```bash
git clone <repo-url>
cd multi_agent_model_workflow
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your ES URL and API key
python setup.py         # provisions agent, tool, and workflow
python setup.py --run   # runs the pipeline
```

The `setup.py` script handles everything: creates the search tool, the agent, and the workflow via Kibana APIs. Teardown with `python setup.py --teardown`.

---

## 7. Available EIS Models

Reference table of preconfigured EIS connectors (for the writer to include or link to):

| Provider | Model | Connector ID |
|----------|-------|-------------|
| OpenAI | GPT-4.1 | `OpenAI-GPT-4-1` |
| OpenAI | GPT-4.1 Mini | `OpenAI-GPT-4-1-Mini` |
| OpenAI | GPT-5.2 | `OpenAI-GPT-5-2` |
| OpenAI | GPT-OSS 120B | `OpenAI-GPT-OSS-120B` |
| Anthropic | Claude Sonnet 4.5 | `Anthropic-Claude-Sonnet-4-5` |
| Anthropic | Claude Opus 4.5 | `Anthropic-Claude-Opus-4-5` |
| Anthropic | Claude Opus 4.6 | `Anthropic-Claude-Opus-4-6` |
| Google | Gemini 2.5 Flash | `Google-Gemini-2-5-Flash` |
| Google | Gemini 2.5 Pro | `Google-Gemini-2-5-Pro` |

---

## Execution Summary

For reference, the successful end-to-end execution:

| Step | Model | Time | Result |
|------|-------|------|--------|
| expand_query | GPT-4.1 Mini | 10s | 3 query variations |
| search_movies | Gemini 2.5 Flash | 25s | 5 ranked movies |
| recommend | Claude Sonnet 4.5 | 16s | Editorial recommendation |
| **Total** | **3 providers** | **~52s** | **Complete pipeline** |

Execution ID: `296967ce-b989-439c-aeb0-d8c594d9e998`

---

## Assets

- Kibana Workflows UI screenshots are in the project `assets/` directory
- Workflow YAML: `workflow.yaml`
- Setup script: `setup.py`
