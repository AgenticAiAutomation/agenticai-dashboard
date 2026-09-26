# VPS service and port registry

**One source of truth for what runs on this box.** Check this before assigning
a port, adding a subdomain, or believing any other document.

Host: Hostinger KVM1, Mumbai · `root@187.127.173.209` (srv1707096)
DNS: Hostinger (`aurora.dns-parking.com`, `nebula.dns-parking.com`) — **not**
Cloudflare, whatever `DEPLOYMENT-CHECKLIST.md` says.

> **Why this file exists.** The wa-funnel spec stated "port 5005 is free — use
> it." It was not: `content-brain.service` had been bound to it for some time.
> Building on that assumption would have taken down a live service. Several
> older docs in this repo still name port 5003 for the dashboard API, which
> moved to 5004. A stale port number is not a documentation nit — it is an
> outage. Update this table in the same commit that adds or moves a service.

Last verified against the running box: **2026-09-25**.

## Application ports

| Port | systemd unit | What it is | Directory | User | Bind |
|---|---|---|---|---|---|
| 5000 | `cockroach.service` | Cockroach Party Social | `/var/www/cockroach-social` | root | 127.0.0.1 |
| 5001 | `agenticai.service` | Marketing site (Flask) | `/var/www/agenticai` | root | 127.0.0.1 |
| 5002 | `leadwa-api.service` | Leadwa API | `/var/www/leadwa/api` | www-data | 127.0.0.1 |
| 5003 | `agentic-platform.service` | Agentic Platform API (Concierge) | `/var/www/agentic-platform` | root | 127.0.0.1 |
| 5004 | `dashboard-api.service` | Dashboard API | `/var/www/agenticai-dashboard/api` | www-data | 127.0.0.1 |
| 5005 | `content-brain.service` | Content Brain (FastAPI) | `/var/www/content-brain` | root | **0.0.0.0** |
| 5006 | `wa-funnel.service` | WhatsApp qualification funnel | `/var/www/wa-funnel` | www-data | 127.0.0.1 |

The dashboard API (5004) reads 5006's SQLite file directly for the leads
desk — see `docs/WA_LEADS.md`. Both run as `www-data`, which is what makes
that work; if either service's user changes, the desk stops being able to
read or write and answers 503.
| 5007 | `concierge-embedder.service` | bge-m3 embedding daemon | `/var/www/agentic-platform` | root | 127.0.0.1 |

**Next free port: 5008.**

### Infrastructure ports

| Port | Service |
|---|---|
| 22 | sshd |
| 80, 443 | nginx |
| 3306, 33060 | mysql |
| 5432 | postgresql |
| 6379 | redis |
| 9000, 9001 | docker-proxy |
| 65529 | monarx-agent |

## Domains

| Hostname | nginx site | Upstream |
|---|---|---|
| `agenticaiautomation.co`, `www.` | `agenticai` | 127.0.0.1:5001 |
| `dashboard.agenticaiautomation.co` | `dashboard-frontend` | 127.0.0.1:5004 |
| `api.dashboard.agenticaiautomation.co` | `dashboard` | 127.0.0.1:5004 |
| `agentic-api.agenticaiautomation.co` | `agentic-platform` | 127.0.0.1:5003 |
| `api.leadwa.co` | `leadwa` | 127.0.0.1:5002 |
| `cockroachjantaparty.co`, `www.` | `cockroach` | 127.0.0.1:5000 |
| `wa.agenticaiautomation.co` | `wa-funnel` *(not yet created)* | 127.0.0.1:5006 |

`content-brain` (5005) has **no nginx server block** — it is reached on the raw
port, which is why it binds `0.0.0.0` rather than localhost.

## Two open security findings

Recorded here because they were found while assigning a port, not fixed:

1. **`content-brain` is exposed to the public internet.** It binds
   `0.0.0.0:5005`, and `http://187.127.173.209:5005/` returns 200 from outside
   the box — verified. That path bypasses nginx entirely: no TLS, none of the
   `site-hardening.conf` rules, no access log in the usual place. Either put it
   behind an nginx server block and rebind to `127.0.0.1`, or firewall the port.
2. **UFW is installed and enabled as a unit, but `ufw status` reports
   inactive.** Nothing is filtering at the host level, which is what makes (1)
   reachable. Every other app port binds to localhost and is therefore
   unreachable from outside by luck of the bind address, not by policy.

## Adding a service

1. Pick the next free port from the table above, then **confirm on the box**:
   ```bash
   ss -ltnp | grep ':<port> '
   ```
   An empty result is the only acceptable answer.
2. Bind to `127.0.0.1`, never `0.0.0.0`, and proxy through nginx.
3. Run as `www-data` unless there is a reason not to.
4. Add the row to both tables here in the same commit.
5. Record the change in `docs/FEATURE_LOG.md`.

## Checking this file is still true

```bash
ssh root@187.127.173.209 'ss -ltnp | grep -E ":(50[0-9][0-9]) "'
ssh root@187.127.173.209 'for f in /etc/nginx/sites-enabled/*; do echo "--- ${f##*/}"; grep -hE "^[[:space:]]*(server_name|proxy_pass)" "$f" | sort -u; done'
```
