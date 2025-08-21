# EU Daily RSS Digest (GitHub Actions)

This repo generates a **daily `digest.md`** from 10–20 RSS feeds using **GitHub Actions** on a schedule (06:30 UTC).

## How to use (no terminal needed)

1. Create a new empty repository on GitHub (private or public).
2. Click **Add file → Upload files** and upload these files from the ZIP:
   - `feeds.txt`
   - `requirements.txt`
   - `scripts/make_digest.py`
   - `.github/workflows/daily_digest.yml`
   - `digest.md`
3. Go to **Settings → Actions → General → Workflow permissions** and select **Read and write permissions**. Save.
4. (Optional) Edit `feeds.txt` to add/remove feeds (one URL per line).
5. The workflow will run every day at **06:30 UTC**. You can also trigger it manually via **Actions → Daily RSS Digest → Run workflow**.

The action uses the built-in **GITHUB_TOKEN** to commit `digest.md` back to the repo.

## Files
- `feeds.txt` — list of RSS feed URLs (one per line).
- `scripts/make_digest.py` — Python script that fetches and merges feeds.
- `.github/workflows/daily_digest.yml` — the scheduler workflow.
- `requirements.txt` — Python dependencies.
- `digest.md` — output file committed on each run.

