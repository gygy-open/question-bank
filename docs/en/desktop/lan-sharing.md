# LAN Sharing

LAN sharing is an **optional switch** in the desktop edition: once on, the question bank on your computer is opened to colleagues on the **same local network**, and everyone shares the same data. It suits lightweight collaboration in small teams on the same network, such as teaching groups and computer labs.

::: warning Off by default · Trusted intranets only
LAN sharing is **off by default**. Only turn it on within an intranet you trust (such as an office / computer lab), and **do not** expose it directly to the internet. If you need a long-running, team-oriented online service, use the [server edition](/en/server/docker).
:::

## How It Works

- **When off**: the built-in service binds to `127.0.0.1` and is accessible only from this computer.
- **When on**: the built-in service binds to `0.0.0.0` instead, and a Windows Firewall allow rule is added, so devices on the same subnet can reach it at `http://<your IP>:<port>`.

Data always stays in the SQLite database on **your computer**; others access your service over the network. Therefore: **your computer must be on and running the app for others to access it.**

## Turning It On

1. Right-click the tray icon and check **LAN sharing**.
2. Windows shows a **UAC elevation prompt** (needed to add the firewall rule); click **Yes**.
3. The service restarts automatically and binds to the LAN.

## Getting the Access Address

Once it is on, colleagues access it using **your computer's LAN IP**.

### Option 1: View It in the App (Recommended)

With LAN sharing on, a **Share Access Address** item (Wi-Fi icon) appears at the **bottom of the app's sidebar**. Click it to see an address like `http://192.168.x.x:<port>/`, which you can **copy with one click** and send to colleagues — no need to look up your IP manually.

### Option 2: Look Up Your IP Manually

To check manually, open PowerShell or Command Prompt and run:

```powershell
ipconfig
```

In the output, find the **IPv4 Address** of your current network adapter (usually something like `192.168.x.x`).

Colleagues then open in their browser:

```
http://192.168.x.x:<port>
```

::: tip Mobile access
Phones must be connected to the **same Wi-Fi** as the host computer. Open the address above in a browser and sign in with your own account.
:::

## Notes for Multiple Users

- **Accounts**: everyone signs in with their own account. Administrators can create accounts for colleagues in [Users](/en/admin/users).
- **Concurrency**: SQLite suits small-scale concurrency; with more users or frequent writes, consider migrating to the [server edition](/en/server/docker).
- **Keep the host on**: sharing depends on your "host" computer; once it shuts down or quits the app, others lose access.
- **IP changes**: if the host gets its IP via DHCP, the address may change after a restart; ask your network administrator to assign the host a fixed IP.

## Turning Sharing Off

Right-click the tray icon and uncheck **LAN sharing**. The service restarts and binds back to `127.0.0.1`; the firewall rule is removed on uninstall.

## Security Recommendations

- Only turn it on within a trusted intranet; never map it to the internet.
- Give each colleague their own account rather than sharing one.
- Use strong passwords and regularly review activity in [Activity Logs](/en/features/activity-logs).
- For internet access / stronger security, deploy the [server edition](/en/server/docker).
