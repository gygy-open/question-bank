# Editions

QuestionBank comes in two deployment editions with **exactly the same features**. They differ in **where they run** and **the scale they suit**.

## Edition Model

```
QuestionBank
├── Desktop edition (Windows tray app)
│   ├── Personal use   —— binds to 127.0.0.1, local access only, single user
│   └── LAN sharing    —— enabled from the tray, binds to 0.0.0.0 + firewall rule, multiple users on the same subnet
└── Server edition (Docker Compose)
    —— MySQL + ChromaDB + Backend + Worker + Frontend, for teams / production
```

## Comparison

| Aspect | Desktop · Personal Use | Desktop · LAN Sharing | Server Edition |
|------|------------------|--------------------|----------|
| Runs on | Windows desktop app | Windows desktop app | Server / Docker |
| Installation | One-click installer | One-click installer | Docker Compose |
| Database | SQLite (built in) | SQLite (built in) | MySQL 8.0 |
| Access scope | This computer only | Same LAN | LAN / intranet / internet (self-configured) |
| Multiple users | Mainly single user | Yes, everyone shares one data set | Yes, built for teams |
| Data directory | `%APPDATA%/QuestionBank` | `%APPDATA%/QuestionBank` | Server volumes / MySQL |
| Upgrades | Install over the existing version | Install over the existing version | Pull new images and recreate |
| Maintenance effort | Very low | Low | Medium (requires running Docker/MySQL) |
| Best for | Individual teachers, lesson prep | Teaching groups, computer labs, small teams | Schools / organizations / production deployments |

## Which One Should I Use?

- **Only on your own computer** → Desktop edition · [Personal Use](/en/desktop/personal)
- **A few people sharing one question bank in the same office / computer lab** → Desktop edition · [LAN Sharing](/en/desktop/lan-sharing)
- **Larger teams that need an always-on service, intranet / internet access, or stronger concurrency and backups** → [Server edition](/en/server/docker)

::: tip Data is portable
The desktop and server editions share the same data model. As your team grows, you can migrate from the desktop edition to the server edition (export questions / migrate the database) without re-entering questions. See [Database & Migrations](/en/server/database) for the migration steps.
:::

## LAN Sharing vs. the Server Edition

Both support multiple users, but they serve different purposes:

- **LAN sharing** is a switch in the desktop edition: it temporarily opens the desktop app on your computer to colleagues on the same subnet and depends on your computer being on. It is **off by default** and suits lightweight collaboration.
- **The server edition** runs on an always-on server with MySQL, offering better concurrency, stability, and backups. It suits a team's official question bank service.
