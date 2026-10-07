# Sleeper Fantasy Football MCP Server

Gives Claude live, direct access to any Sleeper fantasy football league:
rosters, matchups, transactions, and league settings -- straight from
Sleeper's free public API. No login or API key needed.

## What it can do

Once connected, Claude can call:

- **find_my_leagues** -- look up all your leagues by Sleeper username
- **get_league_info** -- league name, scoring settings, roster requirements
- **get_league_users** -- every team owner's name/team name
- **get_all_rosters** -- every team's current starters, bench, and IR, with
  real player names (not just IDs), plus records and points
- **get_matchups** -- head-to-head scores for any week
- **get_transactions** -- waiver adds/drops and trades for any week
- **get_player_info** -- look up any NFL player by Sleeper player ID

This is the tool you want for "pull my current league and tell me who to
trade for" -- it replaces sending roster screenshots.

## Step 1: Deploy it (free, ~5 minutes)

You need a public HTTPS URL for this server -- Claude connects to it from
Anthropic's cloud, not from your own computer, so it can't just run on your
laptop.

**Using Render (recommended, free tier):**

1. Create a free account at https://render.com
2. Push this folder to a GitHub repo (or use Render's "deploy from a public
   Git repo" option, or Render's manual upload if you don't want to use git)
3. In Render, click **New > Web Service**, point it at the repo
4. Render will detect `render.yaml` automatically and set everything up:
   - Build command: `pip install -r requirements.txt`
   - Start command: `python server.py --http`
5. Click **Deploy**. Once it's live, Render gives you a URL like
   `https://sleeper-mcp-server-xxxx.onrender.com`

That URL is what you'll give to Claude in Step 2.

**Alternatives:** Railway, Fly.io, and Cloudflare Workers also have free
tiers and work the same way -- set the start command to
`python server.py --http` and they'll give you a public URL the same way.

> Note: Render's free tier spins down after ~15 minutes of no traffic and
> takes a few seconds to wake back up on the next request. That's fine for
> this use case -- you're not calling it constantly.

## Step 2: Connect it to Claude

1. Go to **claude.ai > Settings > Connectors**
2. Click **Add custom connector**
3. Paste your deployed URL (e.g. `https://sleeper-mcp-server-xxxx.onrender.com`)
4. Click **Add**

Free accounts get 1 custom connector -- this uses it.

## Step 3: Use it

In any chat, ask Claude something like:

> "Use find_my_leagues to look up my Sleeper leagues for username
> [your_sleeper_username], then pull the full rosters for my league."

Once Claude has your `league_id` (you can also just grab it from your
league's URL on sleeper.app -- it's the number after `/leagues/`), it can
call `get_all_rosters` any time to get everyone's current team, live and
up to date, no screenshots needed.

## Running it locally first (optional, to test before deploying)

```bash
pip install -r requirements.txt
python server.py          # stdio mode, for Claude Desktop local config
# or
python server.py --http   # http mode, same as what gets deployed
```

If you want to test it with Claude Desktop locally instead of deploying,
add this to your Claude Desktop MCP config:

```json
{
  "mcpServers": {
    "sleeper": {
      "command": "python",
      "args": ["/absolute/path/to/server.py"]
    }
  }
}
```

## Finding your league_id manually

Open your league on sleeper.app (or in the Sleeper app) and look at the
URL: `https://sleeper.app/leagues/<league_id>/...` -- that long number is
your `league_id`.
