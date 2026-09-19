# Putting this on GitHub

Written for someone who has not used GitHub before. Fifteen minutes, mostly
waiting. Nothing here requires a command line — the Claude Code route at the
bottom skips even the clicking.

## What GitHub is doing for you

Two jobs, and only two.

**Storing the record.** The ledger lives in the repo instead of on one PC. Every
change is a commit with a timestamp and an author, which is what makes "no
number was retro-adjusted" a provable claim rather than a promise.

**Running the collection on a schedule.** Three times a week, GitHub's computers
pull the slate, capture closing prices, and grade the completed week — whether
your laptop is on, off, or in a bag. The Sunday run is the one that matters. A
closing price not captured before kickoff cannot be recovered afterwards by any
means, and missed weeks were what hollowed out the predecessor project.

What GitHub does **not** do: judgment. Hypotheses, tier changes, and
PROPOSED → RATIFIED stay manual, permanently.

---

## 1. Make the repository

1. Go to github.com and sign in.
2. Top right, the **+** menu → **New repository**.
3. Name it `sports-props`. Not `nfl-props` — NCAA lives here too.
4. Choose **Public** — see the note at the bottom before you do.
5. Leave every checkbox unticked. Click **Create repository**.

You'll land on a page of setup instructions. Ignore all of it.

## 2. Upload the files

1. On that page, click **uploading an existing file**.
2. Unzip the repo on your PC first. Open the `sports-props` folder so you can
   see `CLAUDE.md`, `scripts`, `state`, and the rest.
3. Select everything inside and drag it into the browser window.
4. Wait for the uploads to finish, then click **Commit changes**.

Hidden folders don't drag. If `.github` didn't come across, the schedule won't
run — see the fix in step 5.

## 3. Tell it which season and leagues

Repository **Settings** → **Secrets and variables** → **Actions** →
**Variables** tab → **New repository variable**, twice:

| Name | Value | What it does |
|---|---|---|
| `SEASON` | `2026` | the season year |
| `ACTIVE_LEAGUES` | `["nfl"]` | which leagues the schedule runs |

When NCAA starts, change the second to `["nfl","ncaa"]`. That's the entire
switch — no code changes.

## 4. Add the odds key, if you have one

Same page, **Secrets** tab → **New repository secret**. Name it
`ODDS_API_KEY`, paste the key from the-odds-api.com.

Skip this and everything still runs; closing prices just have to be entered by
hand in the console, and the Sunday job will warn you about any row still
missing one.

## 5. Check the schedule is live

Click the **Actions** tab. You should see **weekly-capture** listed.

- If GitHub asks you to enable workflows, say yes.
- If the tab is empty, the `.github` folder didn't upload. Create it manually:
  **Add file → Create new file**, type `.github/workflows/weekly.yml` as the
  name (the slashes create the folders), paste in the contents of that file
  from the zip, commit.

Test it now rather than finding out on a Sunday: **weekly-capture** → **Run
workflow** → leave the defaults → **Run workflow**. Give it a minute and open
the run. Green tick means the plumbing works.

## 6. Pull it down to your PC

The repo is now the master copy, and your PC gets a synced copy of it. Install
**GitHub Desktop** from desktop.github.com — it's the click-based way to do
this. Sign in, **Clone a repository**, pick `sports-props`, choose a folder.

From then on: **Fetch origin** before you work (pulls in what the schedule did),
**Push origin** after (sends your logged rows up). The console's commits appear
there waiting to be pushed.

---

## 7. Publishing to the web — skip for now

The `publish-dashboard` workflow is in the repo but **switched off**. It only
runs if you set a repository variable `PUBLISH_PAGES` to `true`. Leave it
alone and it never fires, so the Actions tab stays green and you keep reading
it.

When you do want a URL: set that variable, then **Settings** → **Pages** →
**Source: GitHub Actions**. It publishes to
`https://<your-username>.github.io/sports-props/` and republishes after every
capture. Free, because the repo is public.

## Reading it on the desktop

`dashboards/index.html` is your one bookmark. Open it from the folder in any
browser — it lists each league with its newest week, links to earlier weeks,
and links to the registry in plain text. It is rebuilt every time a dashboard
is, so it never points at a stale file. After a **Fetch origin** in GitHub
Desktop, the scheduled builds are sitting right there.

That gives you the whole record without the console running. Start the console
(`python scripts/app.py`) only when you need to write — log a row, capture a
close, ratify.

## What public actually means here

Worth thirty seconds before you create the repo, because reversing it later
doesn't unpublish what was already indexed.

**Public means the ledger is readable by anyone, and findable by search.** Your
bets, your stakes, your reasoning, your losses — attached to your GitHub
account name. You work in an industry where your name is professionally
searchable; if that account carries your real name, this becomes part of what
someone finds. That is not a reason not to do it. It is a reason to decide on
purpose.

**Your API key is safe either way.** It lives in Actions secrets, never in the
repo, and nothing in the code contains a literal key.

**One real downside specific to this system.** If a hypothesis ever starts
working, publishing its triggers is how the edge stops working. That is a
Week 10 problem, not a Week 2 problem — but when the first hypothesis clears
its gate, revisit whether the registry should stay public.

**What public buys you**, beyond Pages being free: unlimited Actions minutes
instead of the 2,000/month cap on free private repos, and a record whose
integrity anyone can verify — which, for a system whose whole ethos is "don't
let the record flatter you," is closer to a feature than a cost.

If you'd rather not publish the reasoning, the middle path is a private repo
plus GitHub Pro at about $4/month. The published page is still public even
then; only the source is hidden.

---

## The weekly rhythm once this is up

| When | What happens | Who |
|---|---|---|
| Thursday | slate, injuries, usage pulled | automatic |
| Thu–Sat | log rows in the console, push | you |
| Sunday pre-kickoff | closing prices captured | automatic, or you by hand |
| Tuesday | grading, dashboard rebuilt, site republished | automatic |
| Tuesday | review tickets, ratify | you |

---

## The shortcut

Install Claude Code, point it at the folder, and say: *"create a private GitHub
repo called sports-props, push this, set the SEASON and ACTIVE_LEAGUES
variables, and run the workflow once to check it."*

It does steps 1 through 6 including the hidden `.github` folder, which is the
step most likely to go wrong by hand.
