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
| `DEPLOY_SSH_KEY` | приватный ключ деплой-пары (публичный — в `~/.ssh/authorized_keys` на VPS) |

Для `systemctl restart` без пароля разрешите в sudoers:
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
