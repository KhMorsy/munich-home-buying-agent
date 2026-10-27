# How to open the demo chat

The deployment URL is an **API**, not a website. Opening it in a browser shows:

```json
{"ok":true,"services":{"core_api":"healthy"}}
```

That means the agent is up. Chat goes through Studio or Agent Chat UI.

## Option 1 — LangSmith Studio (deployed agent, best for pitch)

1. Open the deployment:  
   https://eu.smith.langchain.com/o/bd6ee900-c5f7-44f7-9e39-81af4cd05900/host/deployments/589fa4d9-f87c-4cbc-844b-d1b6986c0452
2. Click **Studio**.

Or open Studio pointed at the API directly:

https://eu.smith.langchain.com/studio/?baseUrl=https://munich-home-buying-agent-f56e0da3152a599e974f4ecb12878735.eu.langgraph.app

Graph / assistant id: `agent`

## Option 2 — Agent Chat UI (hosted)

1. Open https://agentchat.vercel.app
2. Enter:
   - **Deployment URL:** `https://munich-home-buying-agent-f56e0da3152a599e974f4ecb12878735.eu.langgraph.app`
   - **Assistant / Graph ID:** `agent`
   - **LangSmith API key:** your `LANGSMITH_API_KEY` from `.env`
3. Continue → chat

## Option 3 — Local Studio (`langgraph dev`)

```bash
source .venv/bin/activate
langgraph dev --studio-url https://eu.smith.langchain.com
```

Then open the Studio link printed in the terminal (EU host).
