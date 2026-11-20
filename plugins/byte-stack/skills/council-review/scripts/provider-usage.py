#!/usr/bin/env python3
"""Print how much of each provider's 5-hour window is left: `provider<TAB>window<TAB>left%<TAB>resets`.

Usage: provider-usage.py [--help]

- gemini: the Antigravity `gemini-5h` bucket, read the way T3 Code's usage probe reads it: refresh the
  OAuth token T3 stores for Antigravity, then ask Google's internal `retrieveUserQuotaSummary`.
- codex: the newest Codex session log's last `rate_limits` event (`primary`, the 300-minute window).
  A window whose reset time has passed prints 100.
A provider it can't read prints `unknown`. Read only; never prints a token. Exit 0 always.
"""
import glob, json, os, sys, time, urllib.parse, urllib.request

if any(a in ("-h", "--help") for a in sys.argv[1:]):
    print(__doc__.strip())
    sys.exit(0)

UA = "antigravity/hub/2.24.0 (aidev_client; os_type=linux; arch=x64; cl=963137146)"
ENDPOINTS = ["https://daily-cloudcode-pa.googleapis.com", "https://cloudcode-pa.googleapis.com"]


def post(url, data, headers):
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def gemini():
    paths = glob.glob(os.path.expanduser("~/userdata/providers/antigravity/*/antigravity-acp/acp_token.json"))
    paths += glob.glob(os.path.expanduser("~/.t3/userdata/providers/antigravity/*/antigravity-acp/acp_token.json"))
    if not paths:
        return None
    tok = json.load(open(max(paths, key=os.path.getmtime)))
    form = {k: tok[k] for k in ("client_id", "client_secret", "refresh_token")} | {"grant_type": "refresh_token"}
    access = post("https://oauth2.googleapis.com/token", urllib.parse.urlencode(form).encode(),
                  {"Content-Type": "application/x-www-form-urlencoded"})["access_token"]
    body = json.dumps({"project": tok["project_id"]} if tok.get("project_id") else {}).encode()
    headers = {"Authorization": f"Bearer {access}", "User-Agent": UA, "Content-Type": "application/json"}
    for ep in ENDPOINTS:
        try:
            s = post(f"{ep}/v1internal:retrieveUserQuotaSummary", body, headers)
        except Exception:
            continue
        groups = [g for g in s.get("groups", []) if g.get("buckets")] or [{"buckets": s.get("buckets", [])}]
        for g in groups:
            for b in g.get("buckets", []):
                if b.get("bucketId") == "gemini-5h" and b.get("remainingFraction") is not None:
                    return round(b["remainingFraction"] * 100), b.get("resetTime", "")
    return None


def codex():
    logs = glob.glob(os.path.expanduser("~/.codex/sessions/*/*/*/*.jsonl"))
    for path in sorted(logs, key=os.path.getmtime, reverse=True)[:5]:
        last = None
        with open(path, errors="replace") as f:
            for line in f:
                if '"rate_limits"' not in line:
                    continue
                try:
                    last = json.loads(line)
                except ValueError:
                    continue
        if not last:
            continue
        stack = [last]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                limits = node.get("rate_limits")
                if isinstance(limits, dict) and isinstance(limits.get("primary"), dict):
                    p = limits["primary"]
                    resets = p.get("resets_at") or 0
                    if resets and resets < time.time():
                        return 100, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(resets))
                    return round(100 - float(p.get("used_percent", 0))), time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(resets))
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
    return None


for name, read in (("gemini", gemini), ("codex", codex)):
    try:
        got = read()
    except Exception:
        got = None
    print(f"{name}\t5h\t{got[0]}\t{got[1]}" if got else f"{name}\t5h\tunknown\t")
