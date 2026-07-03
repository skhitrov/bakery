# todo_fix — server-side hardening runbook

Server-side steps for the diary app on **176.113.82.5** (Ubuntu 24.04, `/opt/diary`).
The app-code + CI fixes are already done in the repo; these run **on the server** and
must be applied by a human (they change live infra / credentials).

> Order matters: do **1–2 first** (credentials/SSH), but keep an SSH session open and a
> known-good key/sudo user ready so you can't lock yourself out. Steps 3–6 are the ones
> you asked for, fully spelled out.

---

## 0. Prereqs / safety
- [ ] Have a **second SSH session open** while touching sshd/ufw (rollback lifeline).
- [ ] Confirm a working **non-root sudo user + SSH key** exists before disabling root/password login.
- [ ] TLS (step 3) needs a **domain name** pointing at 176.113.82.5 — Let's Encrypt will **not**
      issue for a bare IP. If you only have the IP, either get a domain or use a self-signed cert.

## 1. Rotate the root password (URGENT — it was exposed in cleartext, treat as compromised)
```bash
passwd root          # set a long random password
```

## 2. Lock down SSH (root + password login are currently enabled)
```bash
# /etc/ssh/sshd_config.d/99-hardening.conf
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
```
```bash
sshd -t && systemctl reload ssh        # validate BEFORE reload; verify from the 2nd session
```

---

## 3. nginx: TLS + HTTP→HTTPS + HSTS + server_tokens off + XFF overwrite
Current state: `server_tokens` commented (leaks version), **no TLS**, XFF uses
`$proxy_add_x_forwarded_for` (appends the client value → the app must overwrite/trust-last).

```bash
apt update && apt install -y certbot python3-certbot-nginx
# Point a DNS A record at 176.113.82.5 first, then:
certbot --nginx -d diary.example.com   # <-- your domain; auto-adds cert + 80→443 redirect
```

Then make `/etc/nginx/sites-available/diary` (or the certbot-edited site) match this — the
key manual edits are **`server_tokens off`** and **XFF = `$remote_addr`** (overwrite, not append):

```nginx
server {                         # HTTP → HTTPS
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name diary.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2 default_server;
    listen [::]:443 ssl http2 default_server;
    server_name diary.example.com;

    ssl_certificate     /etc/letsencrypt/live/diary.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/diary.example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    server_tokens off;
    client_max_body_size 2m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $remote_addr;   # overwrite — pairs with the app's trusted-proxy fix
        proxy_set_header X-Forwarded-Proto $scheme;         # lets the app set Secure cookie + HSTS
    }
}
```
```bash
nginx -t && systemctl reload nginx
```
Note: the **app already emits** CSP / `X-Content-Type-Options` / `X-Frame-Options` /
`Referrer-Policy` / HSTS (once it sees `X-Forwarded-Proto: https`), so you don't need to
duplicate them in nginx. Adding them with `add_header ... always` is optional defense-in-depth.
- [ ] `curl -I https://diary.example.com/login` shows TLS, HSTS, and a `Server:` header without a version.

## 4. Firewall: install ufw, allow 22/80/443 only
```bash
apt install -y ufw
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp            # allow SSH BEFORE enabling, or you lock yourself out
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
ufw status verbose
```
- [ ] uvicorn `:8000` stays localhost-only (not opened); only 22/80/443 are reachable.

## 5. Purge / rotate the live demo accounts in the prod DB
The prod DB contains the `seed.py` demo accounts (`curator@test.ru` admin,
`admin@bulochka.ru` teacher, `petrov@`/`sidorova@`/`kuznetsov@` parents), likely still on
default passwords (`pass123` / `teacher123`).

```bash
# See who exists
sqlite3 /opt/diary/diary.db "SELECT id, email, role FROM users;"
```

**Rotate a password** (also invalidates that user's live sessions via session_version):
```bash
cd /opt/diary && .venv/bin/python3 - <<'PY'
import sqlite3, getpass
from app.auth import hash_password
email = input("email to rotate: ").strip()
pw = getpass.getpass("new password: ")
con = sqlite3.connect("diary.db")
con.execute(
    "UPDATE users SET password=?, session_version=session_version+1 WHERE email=?",
    (hash_password(pw), email),
)
con.commit()
print("rows updated:", con.total_changes)
PY
```

**Or delete an unused demo account** (mind the FK: reassign/clear students first, since
`students.parent_id` references `users.id`):
```bash
sqlite3 /opt/diary/diary.db "UPDATE students SET parent_id=NULL WHERE parent_id=(SELECT id FROM users WHERE email='petrov@mail.ru');"
sqlite3 /opt/diary/diary.db "DELETE FROM users WHERE email='petrov@mail.ru';"
```
- [ ] No account still accepts a `seed.py` default password.
- [ ] **Never run `seed.py` on the prod box.**

## 6. Backup unit: chown backups, install hardened unit, daemon-reload
The active unit is `/etc/systemd/system/diary-backup.service`; deploy only copies the file
into `/opt/diary`, so it must be installed + reloaded. The hardened unit runs as `diary`, so
`backups/` (currently `root:root`) must be chowned or the backup fails.

```bash
chown -R diary:diary /opt/diary/backups
cp /opt/diary/diary-backup.service /etc/systemd/system/diary-backup.service
systemctl daemon-reload
systemctl start diary-backup.service          # test run
journalctl -u diary-backup.service -n 20 --no-pager
ls -la /opt/diary/backups                      # new diary_*.db owned by diary
systemctl status diary-backup.timer            # confirm the 08:00/20:00 timer is active
```

---

## Repo-side follow-ups (coordinate with the server changes above)
- [ ] Add GitHub **secret `SERVER_HOST_KEY`** = output of `ssh-keyscan 176.113.82.5` → enables
      host-key pinning in `deploy.yml` (falls back to TOFU until set).
- [ ] After creating a non-root deploy user (step 2): set repo **variable `DEPLOY_USER`** to it
      and add a NOPASSWD sudoers rule for `systemctl restart diary`; `deploy.yml` already
      switches to `sudo systemctl restart diary` for a non-root `DEPLOY_USER`.
- [ ] (Optional) Raise `MIN_PASSWORD_LENGTH` in `app/config.py` (kept at 6 for the demo/test
      convention) and adopt a hash-pinned dependency lockfile.
