# Мастер-план разработки Telegram-бота-напоминалки

> Актуальная дорожная карта проекта. Продолжает и консолидирует ранее начатые
> материалы (`PROJECT_PLAN.md`, `plan/phase_2_db_and_config.md`,
> `plan/phase_3_bot_core.md`).
>
> При противоречии с `PROJECT_PLAN.md` приоритет у этого файла (в частности:
> токен — в `.env`, **не** в `config.py`).

Дата составления: 2026-05-17. Версия: 2 (учтены решения пользователя).

---

## 0. Резюме текущего состояния (факты)

| Категория | Состояние |
|---|---|
| Планы | `PROJECT_PLAN.md`, `plan/phase_2`, `plan/phase_3` написаны |
| Исходный код | **Прототип существует:** `config.py`, `database.py`, `bot.py` (нет `scheduler.py`). Не «с нуля», а доработка/харденинг |
| Качество прототипа | Тесты НЕ проходят: (1) дефект `:memory:`+session §2.2; (2) `database.py` возвращает `completed` как `0/1`, а тест ждёт Python `bool` §2.3; (3) зависимости не установлены |
| Безопасность | `config.py` содержал **захардкоженный токен** (тот, что утёк) → токен отозван пользователем; `config.py` переписан на чтение из `.env` (до первого коммита, в историю не попал) |
| Тесты | `tests/test_database.py`, `tests/conftest.py` написаны «вперёд», падают (см. выше) |
| Окружение | `.venv` (Python 3.11) существует, но **пустой** — только `pip`, `setuptools` |
| Инструменты | `git` 2.51 установлен; **`gh` (GitHub CLI) НЕ установлен** |
| Инфраструктура | Нет `requirements.txt`, `.gitignore`, `.env`, git-репозитория, `DEVELOPMENT_LOG.md`, GitHub-репозитория, CI/CD |

---

## 1. Зафиксированные решения пользователя

1. **Полный паритет с Microsoft To Do** (без урезания объёма).
2. Хостинг для деплоя (Фаза 6) — **VPS**.
3. **Закладываем переход на PostgreSQL** — слой данных проектируется
   СУБД-агностично, миграция выполняется отдельной фазой.
4. **Естественный язык для дат не нужен** — только явные форматы
   `YYYY-MM-DD HH:MM` и `DD.MM.YYYY HH:MM`.
5. **Git-workflow:** ветка на каждый этап, коммит каждого шага, push в
   побочную ветку; после прохождения всех тестов и завершения этапа — merge
   в `main`.
6. **CI/CD:** настроить пайплайны и джобы для GitHub-репозитория.

---

## 2. Критические проблемы и их закрытие

### 2.1. Безопасность токена

- Старый токен был отправлен в чат → скомпрометирован.
  **Статус: пользователь выполнил `revoke` ✓.** Старый токен недействителен.
- Рекомендация: если токен также набирался в локальном терминале — очистить
  историю PowerShell (`(Get-PSReadlineOption).HistorySavePath`).
- Новый токен и все секреты — **только в `.env`** (не коммитится).
  `config.py` читает их из окружения через `python-dotenv`, валидирует
  наличие. `.env.example` — шаблон, коммитится. `.gitignore` исключает
  `.env`, `.venv/`, `__pycache__/`, `data/`, `*.db`, `*.pyc`.
- В GitHub Actions секреты (токен для тестов не нужен — Telegram мокается;
  SSH-ключ для деплоя) хранятся в **GitHub Secrets**, не в коде.

### 2.2. Дефект дизайна тестовой БД

`tests/conftest.py` патчит `DATABASE_PATH` на `":memory:"` со
`scope="session"`. SQLite `:memory:` живёт в рамках одного соединения; при
пер-вызовных соединениях таблица исчезнет → `no such table: tasks`. Плюс
session-scope ломает изоляцию.

**Решение (архитектурное требование):**
- `database.py` использует единую `get_connection()`, читающую актуальный
  `DATABASE_PATH` в момент вызова (чтобы патч работал).
- Тестовая БД — временный файл (`tmp_path`), фикстура `scope="function"`
  (свежая БД на тест → полная изоляция). `conftest.py` переписывается в
  Фазе 2.

### 2.3. Контракт БД зафиксирован существующими тестами

`database.py` реализуется строго под `tests/test_database.py`:

| Функция | Контракт |
|---|---|
| `init_db()` | Создаёт таблицу `tasks`, идемпотентна |
| `add_task(user_id:int, description:str, due_date:str=None) -> int` | `id` новой задачи (`int > 0`) |
| `get_tasks(user_id:int, completed:bool=False) -> list[dict]` | По умолчанию активные; фильтр по `user_id`; элементы — `dict` с `id, user_id, description, due_date, completed` |
| `mark_task_done(task_id:int) -> bool` | `False`, если задачи нет |
| `set_reminder(task_id:int, due_date:str) -> bool` | `False`, если задачи нет |

`completed` возвращается как Python `bool`; `due_date` по умолчанию `None`.

Схема `tasks` (MVP): `id INTEGER PK AUTOINCREMENT`, `user_id INTEGER NOT NULL`,
`description TEXT NOT NULL`, `due_date TEXT`,
`completed INTEGER NOT NULL DEFAULT 0`,
`created_at TEXT NOT NULL DEFAULT (datetime('now'))`. Схема эволюционирует
через обратимые миграции.

---

## 3. Культура тестирования (обязательно)

Стек: **Python + pytest** (термин «googletest» = требование строгой
культуры unit-тестов, не C++ Google Test).

- Тесты пишутся **параллельно с кодом**. Фаза не закрыта без тестов.
- Покрытие бизнес-логики (`database.py`, парсеры, scheduler-логика) **≥ 90%**
  (`pytest-cov`).
- Позитивные и негативные сценарии для каждой функции.
- Изоляция (function-scope, temp БД), детерминированность, без сети
  (Telegram мокается), время инъектируется/мокается.
- `tests/test_database.py` не выбрасывается; `conftest.py` правится только в
  части фикстуры БД.

---

## 4. Рабочий процесс: версионирование и CI/CD

### Ветвление и коммиты

- `main` — всегда зелёная и развёртываемая. Технический branch protection
  **недоступен** (требует GitHub Pro для private-репо), поэтому запрет
  прямого push и «merge только зелёного» соблюдаются **дисциплиной**: Claude
  не мержит красные PR. CI виден на каждом PR. (Решение пользователя §9.)
- На каждый этап — ветка `phase/<N>-<slug>` (напр. `phase/2-data-layer`).
- Коммит на каждый осмысленный шаг (атомарные коммиты, понятные сообщения).
- Push ветки → Pull Request → CI должен быть зелёным.
- **Merge в `main` только когда:** все тесты проходят, CI зелёный,
  Definition of Done этапа выполнен.
- После merge — следующий этап от свежего `main`.

### CI (настраивается рано, в Фазе 1)

GitHub Actions, workflow `.github/workflows/ci.yml`, триггеры: push в любую
`phase/*` и pull_request в `main`. Джобы:
- `lint`: `ruff` — `continue-on-error: true` до Фазы 2, потом блокирует.
- `test`: установка `requirements-dev.txt` (+ кэш pip), `pytest` +
  `pytest-cov`. fail-under=90 для бизнес-логики включается с Фазы 2.
Зелёный CI — обязательное условие merge, **соблюдается дисциплиной**
(технический branch protection недоступен на free private repo).

### CD (Фаза 6)

`.github/workflows/deploy.yml`, триггер: push/merge в `main`. Деплой по SSH
на VPS (ключ в GitHub Secrets), рестарт `systemd`-юнита, бэкап БД до
деплоя. До Фазы 6 deploy-workflow не активен.

---

## 5. Целевой объём (полный паритет с Microsoft To Do)

MVP (Фазы 2–4): добавление, список, выполнение, дедлайн, напоминание в срок.

Паритет (Фаза 5):
1. Редактирование/перенос/отмена выполнения.
2. Списки/категории.
3. Повторяющиеся задачи (день/неделя/месяц/кастом).
4. Важные задачи (флаг) + сортировки.
5. Подзадачи (steps) и заметки.
6. «Мой день».
7. Поиск, гибкие напоминания (за N минут, несколько).
8. Часовые пояса пользователя.

---

## 6. Архитектура

```
bot_reminder/
├── .github/workflows/   # ci.yml (Фаза 1), deploy.yml (Фаза 6)
├── .env / .env.example  # секреты / шаблон (.env НЕ в git)
├── .gitignore
├── requirements.txt
├── pyproject.toml       # конфиг pytest, ruff, coverage
├── config.py            # env через python-dotenv, валидация
├── db/                  # СУБД-агностичный слой (см. ниже)
│   ├── __init__.py      # публичный контракт §2.3
│   ├── connection.py    # get_connection() — SQLite сейчас, PG потом
│   └── migrations/      # обратимые миграции схемы
├── scheduler.py         # APScheduler: проверка и отправка напоминаний
├── bot.py               # точка входа, хендлеры, run_polling()
├── handlers/            # (с Фазы 5) хендлеры по доменам
├── data/                # tasks.db (НЕ в git)
├── plan/                # планы по фазам
├── tests/               # pytest: unit + интеграционные
└── DEVELOPMENT_LOG.md   # журнал прогресса
```

> **Примечание про §2.3:** существующие тесты импортируют
> `from database import ...`. Чтобы не ломать контракт, `database.py`
> остаётся фасадом, реэкспортирующим функции из пакета `db/` (либо `db/`
> вводится в Фазе 6 при миграции, а до этого — плоский `database.py`).
> Решение по структуре фиксируется в Фазе 2; СУБД-агностичность достигается
> изоляцией SQL в одном модуле и параметризованными запросами.

**Стек:** Python 3.11, `python-telegram-bot` v20+ (async), `APScheduler`,
`SQLite` → позже `PostgreSQL`, `python-dotenv`, `pytest` + `pytest-cov` +
`pytest-asyncio`, `ruff`.

---

## 7. Дорожная карта по фазам

Каждая фаза — отдельная ветка `phase/<N>-<slug>`, PR, зелёный CI, merge в
`main`, запись в `DEVELOPMENT_LOG.md`.

### Фаза 0 — Безопасность, git, GitHub-репозиторий

- Токен: `revoke` выполнен ✓; новый токен — локально в `.env`.
- `git init`, первый коммит каркаса.
- `.gitignore`, `.env`, `.env.example`, `requirements.txt`,
  `DEVELOPMENT_LOG.md`.
- Создать **private GitHub-репозиторий**, запушить `main`. ✅ Сделано:
  `github.com/James7underland/bot_reminder`.
- Branch protection: технически недоступен (Pro для private) → enforced
  дисциплиной (решение §9).
- **DoD:** репо на GitHub, `main` запушен, `.env`/токен вне git. ✅

### Фаза 1 — Окружение, инструменты, CI

> **Объединена с Фазой 2 в один PR (#1, ветка `phase/1-env-ci`).** Причина:
> Фаза 1 добавляет CI, на старте тесты красные; влить красную Фазу 1 в
> `main` нельзя («main всегда зелёный»). Делить — лишний churn. Поэтому
> Фазы 1+2 доводятся до зелёного на одной ветке и мержатся вместе.

- Наполнить `.venv` из `requirements-dev.txt`. ✅
- `pyproject.toml`: pytest (`testpaths=tests`, `pythonpath=.`), coverage,
  ruff. ✅
- **`.github/workflows/ci.yml`** (jobs lint/test, кэш pip). ✅
- Тесты: `pytest` запускается, ожидаемо «красный» — подтверждён дефект
  §2.2 (`no such table: tasks`). ✅
- **DoD:** CI работает на PR (#1); зависимости установлены. ✅

### Фаза 2 — Слой данных (`config.py`, `database.py`)

> Продолжает `plan/phase_2_db_and_config.md` с поправками §2.1–§2.3.

- `config.py`: загрузка `.env`, `TELEGRAM_BOT_TOKEN` (валидация),
  `DATABASE_PATH` (по умолчанию `./data/tasks.db`).
- `database.py` по контракту §2.3; SQL изолирован, запросы
  параметризованы (задел под PostgreSQL).
- Переписать `tests/conftest.py`: function-scope + temp-file БД. ✅
- `database.py`: `completed` → Python `bool` (контракт §2.3). ✅
- **DoD:** 8/8 тестов зелёные ✅; покрытие `database.py` **100%** ✅;
  далее CI зелёный → merge PR #1. (config.py 80%: непокрыт только
  `except ImportError` для опционального dotenv — не бизнес-логика.)
- Остаток (негативные тесты на пустой `description`/тип `user_id`) —
  можно добавить здесь же до merge или отдельным мелким PR.

### Фаза 3 — Ядро бота (`bot.py`)

> Продолжает `plan/phase_3_bot_core.md`.

- Хендлеры `/start`, `/help`, `/add`, `/list`, `/done`.
- `parse_add_command(text) -> (description, due_date|None)` — чистая
  функция. **Только форматы `YYYY-MM-DD HH:MM` и `DD.MM.YYYY HH:MM`**
  (естественный язык не реализуется — решение №4).
- Связка с `database.*`; `run_polling()`.
- Тесты: `test_parse.py` (таблица форматов, мусор, без даты),
  `test_handlers.py` (Telegram замокан, без сети). ✅
- **Сделано:** парсер переписан под 2 строгих формата (норм. к
  `YYYY-MM-DD HH:MM:SS`); 32 теста зелёные; `bot.py` 100%,
  `database.py` 100%, TOTAL 98.6%; `fail_under=90` включён; ruff чист,
  lint в CI стал блокирующим. `main()` помечен `# pragma: no cover`.
- **DoD:** CI зелёный → merge PR #2. Ручной сценарий add→list→done
  требует, чтобы пользователь создал `.env` с новым токеном (вне Claude).

### Фаза 4 — Напоминания (`scheduler.py`)

- `APScheduler`: job раз в минуту ищет наступившие `due_date`.
- Анти-дубль: миграция (`reminder_sent`/`notified_at`).
- Отправка пользователю, обработка ошибок (бот заблокирован и т.п.).
- Тесты: логика «пора напомнить» — чистая функция с инъекцией времени;
  тест анти-дубля; отправка мокается. ✅
- **Сделано:** `database.get_due_tasks(now)` + `mark_reminder_sent`;
  миграция `reminder_sent` (идемпотентная, + тест legacy-БД);
  `set_reminder` сбрасывает `reminder_sent`; `scheduler.py`
  (`check_and_send_reminders` — чистая логика, `setup_scheduler` —
  `pragma: no cover`); интегрирован в `bot.main()`. 39 тестов зелёные,
  `scheduler.py`/`database.py`/`bot.py` 100%, TOTAL 98.95%.
- **DoD:** CI зелёный → merge PR #3. Ручная проверка «уведомление один
  раз» — после настройки `.env` пользователем.

### Фаза 5 — Полный паритет с To Do (под-фазы 5.1…5.8)

Каждая под-фаза: свой `plan/phase_5_<feature>.md`, своя ветка, своя
миграция, свои тесты, регрессия (старые тесты зелёные).

- 5.1 Редактирование/перенос/uncomplete. ✅ `/edit`, `/reschedule`,
  `/undone`; БД `update_task_description`/`mark_task_undone`; парсер
  отрефакторен (`_match_due`, `parse_datetime`); миграции не требовалось;
  60 тестов зелёные, покрытие 99.25%. PR #4.
- 5.2 Списки/категории. ✅ Таблица `lists` + `tasks.list_id` (миграция,
  тест legacy); БД `create_list`/`get_lists`/`rename_list`/`delete_list`
  (задачи → без списка)/`assign_task_to_list`/`get_tasks_by_list`;
  команды `/lists`, `/newlist`, `/renamelist`, `/dellist`, `/movetask`,
  `/list <id|0>`; 81 тест, покрытие 99.52%. PR #5.
- 5.3 Повторяющиеся задачи. ✅ Колонка `recurrence` (миграция);
  `next_occurrence` (daily/weekly/monthly/yearly + clamp конца месяца и
  високос), `set_recurrence`, `complete_task` (выполняет и спавнит
  следующий экземпляр); `/repeat`, `/done` сообщает о повторе, `/list`
  показывает повтор; 103 теста, покрытие 99.60%. PR #6.
- 5.4 Важные задачи + сортировки. ✅ Колонка `important` (миграция);
  `set_important`; `get_tasks(sort=)` (important/due/alpha/created,
  default = created — поведение неизменно, контракт сохранён);
  `/important`, `/unimportant`, `/list <sort>`, маркер «[важно]»;
  117 тестов, покрытие 99.63%. PR #7.
- 5.5 Подзадачи и заметки. ✅ Таблица `steps` (FK + ON DELETE CASCADE) +
  колонка `notes` (миграция, тест legacy); БД `add_step`/`get_steps`/
  `mark_step_done`/`delete_step`/`get_task`/`set_note`; команды
  `/addstep`, `/steps`, `/stepdone`, `/stepundone`, `/delstep`,
  `/note`, `/delnote`; 133 теста, покрытие 99.72%. PR #8.
- 5.6 «Мой день». ✅ Колонка `myday_date` (миграция, тест legacy);
  `add_to_myday`/`remove_from_myday`/`get_myday` (дедлайн сегодня ИЛИ
  закреплено на сегодня; активные; due-first сортировка); команда
  `/myday [add|remove <id>]`; 143 теста, покрытие 99.75%. PR #9.
- 5.7 Поиск + гибкие напоминания. ✅ `search_tasks` (по описанию/заметке,
  регистронезависимо для кириллицы — фильтр в Python); колонка
  `remind_before` (миграция); `set_remind_before`; `get_due_tasks`
  учитывает `datetime(due_date,'-N minutes')`; команды `/search`,
  `/remindbefore`; 155 тестов, покрытие 99.77%. PR #10.
  (Несколько напоминаний на задачу — вне объёма 5.7, возможный полиш.)
- 5.8 Часовые пояса. ✅ Таблица `user_settings`; `tzutil` (zoneinfo:
  `valid_timezone`/`to_utc`/`to_local`); `get_timezone`/`set_timezone`;
  `due_date` хранится в UTC, ввод (`/add`,`/reschedule`) конвертируется
  из пояса пользователя, вывод (`/list`) — обратно; scheduler сравнивает
  в UTC; команда `/timezone`. Дефолт UTC → identity (контракт и 155
  прежних тестов не затронуты). 171 тест, покрытие 99.78%. PR #11.
- **DoD каждой под-фазы:** фича работает, покрытие новой логики ≥ 90%, CI
  зелёный, merge, лог обновлён.

> **Фаза 5 завершена полностью (5.1–5.8) — достигнут паритет с
> Microsoft To Do.** Далее — Фаза 6 (PostgreSQL, VPS, CD).

### Фаза 6 — усиление, деплой на VPS, CD

Разбита на 6a (автономно) и 6b (требует VPS/решения).

**Фаза 6a — автономная инфраструктура. ✅ (PR #12)**
- Bump GitHub Actions до Node 24 (`checkout@v5`, `setup-python@v6`) —
  снят deprecation-warning (дедлайн 2026-06-02).
- `.github/workflows/deploy.yml`: SSH-деплой при push в `main`;
  **безопасный no-op без секретов** (gate-шаг → success+skip, история
  `main` не краснеет).
- `deploy/bot_reminder.service` (systemd, `Restart=always`),
  `deploy/backup.sh` (`sqlite3 .backup` + ротация 14), `DEPLOYMENT.md`
  (runbook для шагов, требующих сервера).
- Харденинг: глобальный `error_handler` (логирует необработанные
  исключения), зарегистрирован в приложении.
- 172 теста, покрытие 99.78%, ruff чист.

**Фаза 6b — требует пользователя / отдельным решением:**
- VPS (хост/SSH), GitHub Secrets (`DEPLOY_HOST/USER/SSH_KEY`),
  `.env` с новым токеном → «оживление» CD по runbook.
- **PostgreSQL** (отложено сознательно): SQLite достаточно для одного
  процесса; SQL изолирован в `database.py`, миграция — отдельная фаза по
  реальной потребности (`psycopg`, `DATABASE_URL`, PG-сервис в CI).
- **DoD 6b:** бот 24/7 на VPS, CD по merge в `main` работает.

---

## 8. Сквозные правила (Definition of Done каждой фазы)

1. Новый код покрыт тестами (позитив + негатив); `pytest -q` зелёный.
2. Покрытие бизнес-логики ≥ 90%.
3. Никаких секретов в коде/гите; `.env` вне репозитория; секреты CI/CD — в
   GitHub Secrets.
4. Работа в ветке `phase/<N>-*`, атомарные коммиты, PR, **зелёный CI**.
5. Merge в `main` только при выполненном DoD; `main` всегда развёртываема.
6. Запись в `DEVELOPMENT_LOG.md`: сделано / отложено / сломалось.
7. Существующие тесты не «чинятся» удалением.

---

## 9. Решения по репозиторию (зафиксировано)

- **Имя репозитория:** `bot_reminder` (по умолчанию; можно изменить).
- **Владелец:** аккаунт, под которым пройдёт `gh auth login`.
- **Видимость:** **private**.
- **Способ создания:** установить `gh` CLI через winget → пользователь
  выполняет интерактивный `gh auth login` (браузер) → я создаю репо
  (`gh repo create bot_reminder --private`) и пушу `main`.

---

## 10. Ближайшие шаги (история — Фаза 0)

1. §9 подтверждён (private, gh CLI). **Фаза 0 в работе.**
2. Установить `gh` → пользователь `gh auth login` → создать репо, push `main`.
3. Фаза 1 (окружение + CI) → Фаза 2 (сделать существующие тесты зелёными).

> Фазы 0–6 завершены и развёрнуты (бот 24/7 на VPS, CI/CD живой). См.
> `DEVELOPMENT_LOG.md`.

---

## 11. Фаза 7–8 — Telegram Mini App (новая архитектура)

**Решения пользователя:** HTTPS — Cloudflare Tunnel; порядок — бэкенд
раньше UI; «срок» = дата+время. Slash-команды остаются фолбэком.

**Модель (Фаза 7):** разделены две сущности —
- `deadline` (срок): прошёл и не выполнено → «просрочено» (красный в UI)
  + одноразовое уведомление о просрочке;
- `reminder_at` (напоминание): отдельное время → уведомление «пора».

### Фаза 7 — редизайн модели (бэкенд, без инфраструктуры)
- **7.1 ✅ (PR #17):** колонки `deadline`/`reminder_at`/
  `overdue_notified`; миграция (`due_date`→`reminder_at`, поведение
  сохранено); функции `set_deadline`/`set_reminder_at`/
  `get_due_reminders`/`get_overdue_tasks`/`mark_overdue_notified`;
  182 теста, покрытие 99.8%.
- **7.2 ✅ (PR #18):** планировщик: напоминания из `reminder_at`, отдельные уведомления о просрочке из `deadline` (общий `_notify`, анти-дубль у каждого); 184 теста.
  уведомления о просрочке из `deadline` (анти-дубль у каждого).
- **7.3 ✅ (PR #19):** `/deadline`, `/remind` (новая модель, tz→UTC, off-сброс); `/add` и `/reschedule` пишут `reminder_at`; obsolete `/remindbefore` удалён (оффсет-модель ушла); хелп обновлён; 191 тест. **Фаза 7 завершена.**

### Фаза 8 — HTTP API + Telegram Mini App
- **8.1 ✅ (PR #20):** `webapp.py` — FastAPI; `validate_init_data`
  (HMAC-проверка Telegram `initData`, чистая функция); REST: задачи
  (list/create/complete/uncomplete/patch, флаг `overdue`), списки;
  проверка владения задачей (404 на чужую); tz→UTC. 212 тестов,
  `webapp.py` 99%.
- **8.2 ✅ (PR #21):** `static/index.html` — Mini App (Telegram WebApp JS, X-Init-Data, список active/done, чекбокс, звезда, datetime-local срок/напоминание, красная подсветка просрочки, списки/создание); FastAPI `StaticFiles` смонтирован после API (приоритет /api); 214 тестов.
  срока/напоминания, подсветка просроченных) + раздача статики FastAPI.
- **8.3a ✅ (PR #22):** инфраструктура webapp: `deploy/bot_webapp.service` (uvicorn 127.0.0.1:8080), `deploy/cloudflared.service`, deploy.yml рестартит и webapp (best-effort), runbook §6 в DEPLOYMENT.md.
- **8.3b (с пользователем):** Caddy на VPS → `https://ernstgku.beget.tech` (A-запись Beget→IP, порты 80/443, Let's Encrypt), регистрация Mini App в @BotFather. `deploy/Caddyfile` + runbook §6 — PR #23.
  @BotFather, запуск webapp на сервере (вместе с ботом) — пошагово с
  пользователем.
- Тестовая дисциплина: логика — в Python под pytest; Mini App — тонкий
  клиент над протестированным API.

### Фаза 8.4–8.7 — Mini App до паритета с ботом

8.1/8.2 — MVP UI. Пользователь запросил полный паритет; расширяем
API+фронтенд итерациями (PR → CI → авто-деплой; туннель не трогается).

- **8.4 ✅ (PR #24):** повторы (`recurrence` в PATCH + clear, валидация)
  и «Мой день» (`GET /api/myday`, `POST /api/tasks/{id}/myday`,
  `_today_local` по tz пользователя); во фронтенде — селектор повтора,
  тумблер «Мой день», кнопка «в Мой день», повтор в мете. 217 тестов.
- **8.5 ✅ (PR #25):** подзадачи (steps CRUD: GET/POST/toggle/DELETE под `/api/tasks/{id}/steps`, ownership через задачу) + заметки (`notes`/`clear_notes` в PATCH); фронтенд — textarea заметки, чек-лист подзадач с добавлением/✕/тогглом. 220 тестов.
- **8.6 ✅ (PR #26):** поиск (`GET /api/tasks?search=` → `search_tasks`, перекрывает фильтры) и сортировки (`?sort=important|due|alpha|created` → `get_tasks(sort=)`); фронтенд — строка поиска (debounce) + селектор сортировки. 222 теста.
- **8.7 ✅ (PR #27):** списки — PATCH/DELETE `/api/lists/{id}` (ownership), перенос `POST /api/tasks/{id}/list`; настройки — GET/PUT `/api/settings` (часовой пояс, валидация ZoneInfo→422); фронтенд — ✎/🗑 списка, селектор «Список» в задаче, ⚙ часовой пояс. 225 тестов. **Mini App = паритет с ботом.**
- **8.8 (PR #28, инфра):** SNI-роутер на :443 без вреда VPN. VPN =
  VLESS+Reality на :443 (Amnezia) → xray-fallback и второй IP
  недоступны; решение — **nginx `stream`+`ssl_preread` на :443**: SNI
  домена Mini App → Caddy:8443 → webapp, всё прочее → xray
  (перепубликован на 127.0.0.1:8444; конфиг xray НЕ тронут).
  `deploy/nginx-sni.conf`, `Caddyfile` (https_port 8443), runbook §6 +
  откат. Пересоздание контейнера — по `docker inspect` пользователя
  (commit-бэкап, Reality-ключи сохраняются).
- **8.9 (PR #29, инфра):** домен решён. `ernstgku.beget.tech`
  (технический Beget) A-запись менять нельзя → тупик. Зарегистрирован
  **`reminderr.ru`** (Beget, .RU 199 ₽/год), A → VPS
  `155.212.227.167` (Beget DNS, NS не трогаем). Конфиги
  `deploy/Caddyfile`/`nginx-sni.conf`/`DEPLOYMENT.md` переведены на
  `reminderr.ru`. Путь А (нативный `https://reminderr.ru` через
  SNI-роутер) — то, что изначально и хотел пользователь.
- **8.3b (с пользователем):** HTTPS наружу. Caddy отпал — :443 занят
  VPN (`amnezia-xray`). Идём через `cloudflared` (исходящий, без
  конфликта): быстрый туннель работает (`*.trycloudflare.com`),
  оформляется в `cloudflared-quick.service`; стабильный URL — путь B
  (домен в Cloudflare) по желанию.

---

## 12. Фаза 9 — допиливание паритета с Microsoft To Do

Реалистичный остаток (после Фазы 8): custom recurrence, smart-views,
snooze, ручной порядок, мелочи UI. Вне scope: файловые вложения,
расшаривание списков (требуют отдельной подсистемы/модели прав).

- **9.1 ✅ (PR #30):** Custom recurrence. Расширены значения
  `recurrence`: `every:N:d/w/m/y` и `weekdays:MO,WE,FR` (помимо легаси
  пресетов). `is_valid_recurrence`, обновлён `next_occurrence` и
  `complete_task` (custom тоже спавнит следующий экземпляр). API PATCH
  валидирует новые формы. Фронтенд: в панели задачи опция «свой
  шаблон» с «каждые N единиц» / «по дням недели» (Пн…Вс). 245 тестов.
- **9.2 ✅ (PR #31):** Smart-views в Mini App. БД: `get_planned` (актив + дедлайн ИЛИ напоминание, сорт по дедлайну, потом напом., потом created) и `get_important_tasks` (актив + important=1, сорт по дедлайну). API `GET /api/planned` и `GET /api/important` (ownership через initData). Фронтенд: вместо чекбокса «Мой день» — селектор «Все / Мой день / Планируется / Важно» — переключает запрос. 247 тестов.
- 9.3 Snooze напоминания (+15 мин / +1 ч / завтра).
- 9.4 Ручной порядок задач (drag/up-down через `order_index`).
- 9.5 Мелкая UI-полировка (прогресс подзадач, порядок/цвет списков).
