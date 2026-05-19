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

## 6. Telegram Mini App — SNI-роутер на :443 (Фаза 8.8)

`webapp.py` слушает `127.0.0.1:8080`. На :443 — nginx `stream` +
`ssl_preread`: по SNI отдаёт `reminderr.ru` в Caddy (HTTPS
:8443 → webapp), всё прочее — в xray (VPN). Конфиг xray не меняется,
меняется только порт его публикации в Docker.

Предусловия: A-запись `reminderr.ru` → IP VPS; открыты 80/443.

**6.1. Сервис webapp:**
```bash
cd ~/bot_reminder && git pull --ff-only
./.venv/bin/pip install -r requirements.txt
cp deploy/bot_webapp.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now bot_webapp
curl -s localhost:8080/healthz                     # {"ok":true}
```

**6.2. Caddy на :8443 (за роутером, ACME по :80):**
```bash
apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | tee /etc/apt/sources.list.d/caddy-stable.list
apt update && apt install -y caddy
cp ~/bot_reminder/deploy/Caddyfile /etc/caddy/Caddyfile
systemctl restart caddy
```

**6.3. Перепубликация порта xray (деликатный шаг).** Конфиг xray НЕ
редактируем. Контейнер пересоздаётся с тем же образом/сетью/volume/env,
но порт `0.0.0.0:443` → `127.0.0.1:8444`. Перед этим — резервный образ
для отката:
```bash
docker commit amnezia-xray amnezia-xray:prebackup
docker inspect amnezia-xray > ~/amnezia-xray.inspect.json
```
Точную команду `docker rm` + `docker run` (с сохранением всех
mounts/env/network/restart из inspect) сгенерировать по содержимому
`amnezia-xray.inspect.json` — НЕ пересоздавать «вслепую».

**6.4. nginx SNI-роутер на :443:**
```bash
apt install -y nginx
nginx -V 2>&1 | tr ' ' '\n' | grep -q stream && echo "stream OK"
cp ~/bot_reminder/deploy/nginx-sni.conf /etc/nginx/stream-sni.conf
grep -q stream-sni /etc/nginx/nginx.conf \
  || echo 'include /etc/nginx/stream-sni.conf;' >> /etc/nginx/nginx.conf
nginx -t && systemctl restart nginx
```

**6.5. Проверка:**
```bash
curl -sI https://reminderr.ru/healthz | head -1   # HTTP/2 200
```
И отдельно проверить, что VPN-клиент по-прежнему подключается.

**6.6. Регистрация в @BotFather:** `/mybots` → бот → Bot Settings →
Menu Button → URL `https://reminderr.ru`. После этого
`cloudflared-quick` можно отключить:
`systemctl disable --now cloudflared-quick`.

**6.7. Откат:** `systemctl stop nginx`; пересоздать `amnezia-xray` из
`amnezia-xray:prebackup` с `-p 0.0.0.0:443:443` → VPN снова напрямую
на 443 (Mini App вернуть на Cloudflare-туннель).

**Авто-деплой:** `deploy.yml` рестартит `bot_reminder` и `bot_webapp`;
nginx/caddy/xray не трогает (их меняем вручную, редко).
