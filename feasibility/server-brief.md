# Server brief — piano test site over HTTPS

Written for the Server repo session. Context: Piano-Master HTTPS feasibility test (see RESULTS.md). The probe page to deploy (as /opt/piano/www/index.html) is /home/tedc/repos/Piano-Master/feasibility/https-probe/index.html.

**Goal:** add a second site to the existing Caddy so the piano app can be served at `https://192.168.2.128/` with Caddy's internal CA, without affecting Docmost at `https://kb.durinforge.internal`.

**Requirements**
1. **Caddy site block** for `${SERVER_IP}` in `setup/templates/Caddyfile.tmpl`:
   - `tls internal` (the same CA as the KB, so the existing root stays valid);
   - `root * /srv/piano` with `file_server`;
   - the same security headers as the KB block;
   - it doesn't matter which site Caddy lists first. Clients connecting by IP send no SNI, and Caddy should pick the IP certificate.
2. **Static content directory** on the host, e.g. `/opt/piano/www`, root-owned and world-readable. Mount it **read-only** into the caddy service at `/srv/piano` in `setup/templates/docker-compose.yml.tmpl`.
   - The setup scripts create the directory but **don't manage its contents**. App deploys (starting with the test page) put files there.
   - If it's empty, drop in a placeholder `index.html` only when none is present.
3. **Keep all existing guarantees:**
   - Caddy stays bound to `${SERVER_IP}:443` only;
   - no port 80;
   - `verify-lan.sh` P01 still reports exactly ports 22, 443 and 445;
   - never `docker compose down -v`, because `caddy_data` holds the CA.
4. **Tests:**
   - Add to `verify.sh` / `verify-lan.sh`: `curl --cacert caddy-root-ca.crt https://${SERVER_IP}/` returns 200;
   - the certificate served without SNI has `IP Address:192.168.2.128` in its SAN and chains to the existing root;
   - existing H01–H05 still pass.
5. **Docs:** a new client doc, e.g. `setup/docs/13-ipad-client.md`:
   - get `caddy-root-ca.crt` onto the iPad (AirDrop, email, or Files);
   - Settings › General › VPN & Device Management › install the profile;
   - check the SHA-256 fingerprint is `19A112C4CEEBBAD929B5EBFA21E4FDAF9CDC07DF6EB2522F8B1D375F3FD7D972`;
   - Settings › General › About › Certificate Trust Settings › switch on **Full Trust**.
6. **Rollout:**
   - `sudo ./setup.sh --dry-run`, then `sudo ./setup.sh`, then a second run must report **0 changed**, then `sudo ./verify.sh`, then `./verify-lan.sh` from the workstation;
   - expect a few seconds of KB downtime while Caddy restarts;
   - work on a branch and open a PR as usual.

**Report back:** the final URL, the `openssl s_client -connect 192.168.2.128:443` subject and SAN output, and the verify results.

