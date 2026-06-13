# ---------------------------------------------------------------------------
# Dockerfile for netbox-pve-sync plugin
#
# Extends the official NetBox Docker image and installs this plugin.
# Usage:
#   docker build -t netbox-pve-sync .
#   docker compose up -d
# ---------------------------------------------------------------------------

ARG NETBOX_VERSION=v4.6.2
FROM netboxcommunity/netbox:${NETBOX_VERSION}

# Copy the plugin source into the container
COPY . /opt/netbox-pve-sync/

# Install the plugin into NetBox's virtualenv
RUN /opt/netbox/venv/bin/pip install --no-cache-dir /opt/netbox-pve-sync/

# Copy standalone sync modules to a known path (for sync engine)
RUN cp /opt/netbox-pve-sync/sync.py /opt/netbox-pve-sync/config.py \
       /opt/netbox-pve-sync/state_db.py /opt/netbox/netbox/ 2>/dev/null || true
