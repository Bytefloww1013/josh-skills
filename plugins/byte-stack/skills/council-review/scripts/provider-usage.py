#!/usr/bin/env python3
"""Print how much of each provider's usage is left: `provider<TAB>window<TAB>left%<TAB>resets`.

Usage: provider-usage.py [--help]

- gemini: one row per T3 Antigravity account (provider instance), read the way T3 Code's usage probe reads
  it: refresh the OAuth token T3 stores in the account's folder (`providers/antigravity/<sha256 of the
  instance id>`), then ask Google's internal `retrieveUserQuotaSummary`. The row is the tighter of the
  `gemini-5h` and `gemini-weekly` buckets, and `window` says which (`5h` or `weekly`). The `antigravity`
  instance prints as `gemini`, any other as `gemini:<instance id>` (`gemini:antigravity_2`). An account
  Google refuses prints `unknown` with the reason in `resets` (`verify the account`: 403, the user must
  open the sign-in link in that account's `antigravity-acp/log/acp-server-*.log`).
- codex: the newest Codex session log's last `rate_limits` event (`primary`, the 300-minute window).
  A window whose reset time has passed prints 100.
A provider it can't read prints `unknown`. Read only; never prints a token. Exit 0 always.
"""
import glob, hashlib, json, os, sys, time, urllib.error, urllib.parse, urllib.request

if any(a in ("-h", "--help") for a in sys.argv[1:]):
    print(__doc__.strip())
    sys.exit(0)

UA = "antigravity/hub/2.24.0 (aidev_client; os_type=linux; arch=x64; cl=963137146)"
ENDPOINTS = ["https://daily-cloudcode-pa.googleapis.com", "https://cloudcode-pa.googleapis.com"]


def post(url, data, headers):
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def antigravity_instances():
    """T3's Antigravity provider instance ids, from its settings; `antigravity` alone when they can't be read."""
    for root in ("~/userdata", "~/.t3/userdata"):
        try:
            instances = json.load(open(os.path.expanduser(f"{root}/settings.json"))).get("providerInstances", {})
        except (OSError, ValueError):
            continue
        ids = [k for k, v in instances.items() if isinstance(v, dict) and v.get("driver") == "antigravity" and v.get("enabled", True)]
        if ids:
            return sorted(ids, key=lambda k: (k != "antigravity", k))
    return ["antigravity"]


def gemini(instance):
    """(left%, resets, window) for one Antigravity account, or (None, reason, "5h") when it can't be read."""
    folders = [os.path.expanduser(f"{root}/providers/antigravity/{hashlib.sha256(instance.encode()).hexdigest()}/antigravity-acp")
               for root in ("~/userdata", "~/.t3/userdata")]
    folder = next((f for f in folders if os.path.isdir(f)), None)
    if not folder:
        return None, "no folder", "5h"
    # The OAuth client is the same for every account; T3 writes it to acp_token.json in the first one.
    clients = glob.glob(os.path.expanduser("~/userdata/providers/antigravity/*/antigravity-acp/acp_token.json"))
    clients += glob.glob(os.path.expanduser("~/.t3/userdata/providers/antigravity/*/antigravity-acp/acp_token.json"))
    if not clients:
        return None, "no client", "5h"
    client = json.load(open(clients[0]))
    own = os.path.join(folder, "acp_token.json")
    try:
        refresh = json.load(open(os.path.join(folder, "antigravity-oauth-token")))["token"]["refresh_token"]
    except (OSError, ValueError, KeyError, TypeError):
        refresh = json.load(open(own)).get("refresh_token") if os.path.exists(own) else None
    if not refresh:
        return None, "not logged in", "5h"
    form = {"client_id": client["client_id"], "client_secret": client["client_secret"], "refresh_token": refresh,
            "grant_type": "refresh_token"}
    access = post("https://oauth2.googleapis.com/token", urllib.parse.urlencode(form).encode(),
                  {"Content-Type": "application/x-www-form-urlencoded"})["access_token"]
    project = json.load(open(own)).get("project_id") if os.path.exists(own) else None
    body = json.dumps({"project": project} if project else {}).encode()
    headers = {"Authorization": f"Bearer {access}", "User-Agent": UA, "Content-Type": "application/json"}
    reason = "unreadable"
    for ep in ENDPOINTS:
        try:
            s = post(f"{ep}/v1internal:retrieveUserQuotaSummary", body, headers)
        except urllib.error.HTTPError as e:
            try:
                message = json.loads(e.read() or b"{}").get("error", {}).get("message", "")
            except ValueError:
                message = ""
            reason = "verify the account" if "Verify your account" in message else f"HTTP {e.code}"
            continue
        except Exception:
            continue
        groups = [g for g in s.get("groups", []) if g.get("buckets")] or [{"buckets": s.get("buckets", [])}]
        found = {}
        for g in groups:
            for b in g.get("buckets", []):
                if b.get("bucketId") in ("gemini-5h", "gemini-weekly") and b.get("remainingFraction") is not None:
                    found[b["bucketId"]] = (round(b["remainingFraction"] * 100), b.get("resetTime", ""))
        if found:
            window = min(found, key=lambda k: found[k][0])
            return found[window][0], found[window][1], window.removeprefix("gemini-")
    return None, reason, "5h"


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


for instance in antigravity_instances():
    name = "gemini" if instance == "antigravity" else f"gemini:{instance}"
    try:
        left, resets, window = gemini(instance)
    except Exception:
        left, resets, window = None, "", "5h"
    print(f"{name}\t{window}\t{left if left is not None else 'unknown'}\t{resets}")
try:
    got = codex()
except Exception:
    got = None
print(f"codex\t5h\t{got[0]}\t{got[1]}" if got else "codex\t5h\tunknown\t")
