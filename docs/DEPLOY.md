# Deploying Ripken to Digital Ocean

## 1. Provision Droplet

- Ubuntu 24.04, 1GB RAM / 1 vCPU ($6/mo)
- Add your SSH key during creation

## 2. Initial Server Setup

```bash
# SSH in
ssh root@<droplet-ip>

# Create swapfile (required for Next.js builds)
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# Install Docker
curl -fsSL https://get.docker.com | sh

# Firewall
ufw allow OpenSSH
ufw allow 80
ufw allow 443
ufw enable
```

## 3. Deploy Application

```bash
git clone https://github.com/Noah-Brown/ripken.git ~/ripken
cd ~/ripken

# Create .env (copy from .env.example, fill in production values)
cp .env.example .env
nano .env  # Set DASHBOARD_PASSWORD, SESSION_SECRET, SITE_ADDRESS, etc.

# Key production env vars:
# SITE_ADDRESS=ripken.noahbrown.io
# DASHBOARD_PASSWORD=<your-password>
# SESSION_SECRET=<generate with: openssl rand -hex 32>
# FRONTEND_URL=https://ripken.noahbrown.io
# ALLOWED_ORIGINS=https://ripken.noahbrown.io
# NEXT_PUBLIC_API_URL=https://ripken.noahbrown.io
# YAHOO_REDIRECT_URI=https://ripken.noahbrown.io/auth/yahoo/callback

docker compose up -d --build
```

## 4. DNS

Add an A record: `ripken.noahbrown.io` -> `<droplet-ip>`

Caddy will automatically provision a Let's Encrypt certificate once DNS propagates.

## 5. Yahoo OAuth

1. Update redirect URI in Yahoo Developer App to `https://ripken.noahbrown.io/auth/yahoo/callback`
2. Visit `https://ripken.noahbrown.io/auth/yahoo` to authenticate

## 6. Backups

```bash
mkdir -p ~/ripken/backups

# Add cron job
cat > /etc/cron.d/ripken-backup << 'CRON'
0 4 * * * root sqlite3 /root/ripken/data/fantasy_dashboard.db ".backup /root/ripken/backups/fantasy_dashboard_$(date +\%Y\%m\%d).db" && find /root/ripken/backups -name "*.db" -mtime +7 -delete
CRON
```

## 7. Redeploying

An SSH alias `ripken` is configured locally (`~/.ssh/config`) for the production server.

```bash
ssh ripken "cd ~/ripken && git pull && docker compose up -d --build"
```

Or manually:
```bash
ssh ripken
cd ~/ripken
git pull
docker compose up -d --build
```
