# Деплой на VPS (runbook)

Артефакты в репозитории уже готовы. Ниже — шаги, которые выполняете **вы**
(требуют доступа к серверу). Пока эти шаги не сделаны, `deploy.yml`
безопасно пропускает деплой (CI/история `main` не страдают).

## 1. Подготовка VPS (один раз)

```bash
sudo apt update && sudo apt install -y python3.11 python3.11-venv git sqlite3
git clone https://github.com/James7underland/bot_reminder.git ~/bot_reminder
cd ~/bot_reminder
python3.11 -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp .env.example .env && nano .env      # вписать НОВЫЙ токен @BotFather
```

## 2. systemd (автозапуск/перезапуск)

```bash
sed "s/__USER__/$USER/g" deploy/bot_reminder.service \
  | sudo tee /etc/systemd/system/bot_reminder.service
sudo systemctl daemon-reload
sudo systemctl enable --now bot_reminder
systemctl status bot_reminder        # должно быть active (running)
```

`Restart=always` — бот сам поднимается после падения/перезагрузки.

## 3. Бэкап БД (cron, ежедневно)

```bash
crontab -e
# добавить строку:
0 3 * * * /home/<user>/bot_reminder/deploy/backup.sh >> ~/backup.log 2>&1
```

## 4. CD через GitHub Actions

Добавьте секреты репозитория (Settings → Secrets and variables → Actions):

| Секрет | Значение |
|---|---|
| `DEPLOY_HOST` | IP/домен VPS |
| `DEPLOY_USER` | пользователь SSH |
| `DEPLOY_SSH_KEY` | приватный ключ деплой-пары в **base64, одной строкой** (см. ниже) |

Значение `DEPLOY_SSH_KEY` получить на сервере (без переносов строк —
так ключ не ломается при передаче через секрет):
```
base64 -w0 ~/.ssh/cd_key
```
Скопировать всю строку → вставить в секрет. Публичный ключ
(`~/.ssh/cd_key.pub`) — в `~/.ssh/authorized_keys` на VPS.

Если деплой идёт под non-root, для `systemctl restart` без пароля
разрешите в sudoers (под root не требуется):
```
<user> ALL=(root) NOPASSWD: /bin/systemctl restart bot_reminder
```

После добавления секретов каждый merge в `main` автоматически
обновляет бота (`git pull` → `pip install` → `systemctl restart`).
Без секретов джоба `Deploy` завершается со статусом success и пометкой
«skipping deploy».

## 5. PostgreSQL (отложено, Фаза 6b)

Сейчас прод — SQLite (достаточно для одного процесса). Миграция на
PostgreSQL вынесена в отдельную фазу: SQL изолирован в `database.py`,
переключение делается там же + `psycopg` + строка подключения из `.env`.
Делать, когда появится реальная потребность (несколько инстансов/высокая
конкуренция).

## 6. Telegram Mini App (Фаза 8.3) — на сервере

Бэкенд Mini App (`webapp.py`) слушает только `127.0.0.1:8080`; наружу
отдаётся через Cloudflare Tunnel (HTTPS). Токен берётся из того же
`.env`.

**6.1. Сервис webapp (uvicorn):**
```bash
cd ~/bot_reminder && git pull --ff-only
./.venv/bin/pip install -r requirements.txt        # fastapi, uvicorn
cp deploy/bot_webapp.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bot_webapp
curl -s localhost:8080/healthz                     # {"ok":true}
```

**6.2. Cloudflare Tunnel.** Установить cloudflared:
```bash
curl -L -o /usr/local/bin/cloudflared \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
chmod +x /usr/local/bin/cloudflared
```
- *Быстрый старт (URL меняется при перезапуске):*
  `cloudflared tunnel --url http://127.0.0.1:8080` — выдаст
  `https://<rand>.trycloudflare.com`.
- *Стабильный URL (рекомендуется):* в дашборде Cloudflare Zero Trust
  → Networks → Tunnels → Create tunnel → Cloudflared; привязать
  public hostname к `http://127.0.0.1:8080`; скопировать **Tunnel
  token**, затем:
  ```bash
  cp deploy/cloudflared.service /etc/systemd/system/
  echo 'TUNNEL_TOKEN=<токен>' > /etc/cloudflared.env
  chmod 600 /etc/cloudflared.env
  sudo systemctl daemon-reload && sudo systemctl enable --now cloudflared
  ```

**6.3. Регистрация Mini App в @BotFather:**
- `/newapp` (или `/mybots` → бот → Bot Settings → Menu Button /
  Configure Mini App) → указать URL туннеля (HTTPS).
- Готово: в боте появится кнопка, открывающая интерфейс.

**Авто-деплой:** `deploy.yml` после `git pull` рестартит и
`bot_reminder`, и `bot_webapp` (best-effort: пока юнит не создан —
шаг не падает).
