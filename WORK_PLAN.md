# Мастер-план разработки Telegram-бота-напоминалки

> Актуальная дорожная карта проекта. Продолжает и консолидирует ранее начатые
> материалы (`PROJECT_PLAN.md`, `plan/phase_2_db_and_config.md`,
> `plan/phase_3_bot_core.md`).
>
> При противоречии с `PROJECT_PLAN.md` приоритет у этого файла (в частности:
> токен – в `.env`, **не** в `config.py`).

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
| Окружение | `.venv` (Python 3.11) существует, но **пустой** – только `pip`, `setuptools` |
| Инструменты | `git` 2.51 установлен; **`gh` (GitHub CLI) НЕ установлен** |
| Инфраструктура | Нет `requirements.txt`, `.gitignore`, `.env`, git-репозитория, `DEVELOPMENT_LOG.md`, GitHub-репозитория, CI/CD |

---

## 1. Зафиксированные решения пользователя

1. **Полный паритет с Microsoft To Do** (без урезания объёма).
2. Хостинг для деплоя (Фаза 6) – **VPS**.
3. **Закладываем переход на PostgreSQL** – слой данных проектируется
   СУБД-агностично, миграция выполняется отдельной фазой.
4. **Естественный язык для дат не нужен** – только явные форматы
   `YYYY-MM-DD HH:MM` и `DD.MM.YYYY HH:MM`.
5. **Git-workflow:** ветка на каждый этап, коммит каждого шага, push в
   побочную ветку; после прохождения всех тестов и завершения этапа – merge
   в `main`.
6. **CI/CD:** настроить пайплайны и джобы для GitHub-репозитория.

---

## 2. Критические проблемы и их закрытие

### 2.1. Безопасность токена

- Старый токен был отправлен в чат → скомпрометирован.
  **Статус: пользователь выполнил `revoke` ✓.** Старый токен недействителен.
- Рекомендация: если токен также набирался в локальном терминале – очистить
  историю PowerShell (`(Get-PSReadlineOption).HistorySavePath`).
- Новый токен и все секреты – **только в `.env`** (не коммитится).
  `config.py` читает их из окружения через `python-dotenv`, валидирует
  наличие. `.env.example` – шаблон, коммитится. `.gitignore` исключает
  `.env`, `.venv/`, `__pycache__/`, `data/`, `*.db`, `*.pyc`.
- В GitHub Actions секреты (токен для тестов не нужен – Telegram мокается;
  SSH-ключ для деплоя) хранятся в **GitHub Secrets**, не в коде.

### 2.2. Дефект дизайна тестовой БД

`tests/conftest.py` патчит `DATABASE_PATH` на `":memory:"` со
`scope="session"`. SQLite `:memory:` живёт в рамках одного соединения; при
пер-вызовных соединениях таблица исчезнет → `no such table: tasks`. Плюс
session-scope ломает изоляцию.

**Решение (архитектурное требование):**
- `database.py` использует единую `get_connection()`, читающую актуальный
  `DATABASE_PATH` в момент вызова (чтобы патч работал).
- Тестовая БД – временный файл (`tmp_path`), фикстура `scope="function"`
  (свежая БД на тест → полная изоляция). `conftest.py` переписывается в
  Фазе 2.

### 2.3. Контракт БД зафиксирован существующими тестами

`database.py` реализуется строго под `tests/test_database.py`:

| Функция | Контракт |
|---|---|
| `init_db()` | Создаёт таблицу `tasks`, идемпотентна |
| `add_task(user_id:int, description:str, due_date:str=None) -> int` | `id` новой задачи (`int > 0`) |
| `get_tasks(user_id:int, completed:bool=False) -> list[dict]` | По умолчанию активные; фильтр по `user_id`; элементы – `dict` с `id, user_id, description, due_date, completed` |
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

- `main` – всегда зелёная и развёртываемая. Технический branch protection
  **недоступен** (требует GitHub Pro для private-репо), поэтому запрет
  прямого push и «merge только зелёного» соблюдаются **дисциплиной**: Claude
  не мержит красные PR. CI виден на каждом PR. (Решение пользователя §9.)
- На каждый этап – ветка `phase/<N>-<slug>` (напр. `phase/2-data-layer`).
- Коммит на каждый осмысленный шаг (атомарные коммиты, понятные сообщения).
- Push ветки → Pull Request → CI должен быть зелёным.
- **Merge в `main` только когда:** все тесты проходят, CI зелёный,
  Definition of Done этапа выполнен.
- После merge – следующий этап от свежего `main`.

### CI (настраивается рано, в Фазе 1)

GitHub Actions, workflow `.github/workflows/ci.yml`, триггеры: push в любую
`phase/*` и pull_request в `main`. Джобы:
- `lint`: `ruff` – `continue-on-error: true` до Фазы 2, потом блокирует.
- `test`: установка `requirements-dev.txt` (+ кэш pip), `pytest` +
  `pytest-cov`. fail-under=90 для бизнес-логики включается с Фазы 2.
Зелёный CI – обязательное условие merge, **соблюдается дисциплиной**
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
│   ├── connection.py    # get_connection() – SQLite сейчас, PG потом
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
> вводится в Фазе 6 при миграции, а до этого – плоский `database.py`).
> Решение по структуре фиксируется в Фазе 2; СУБД-агностичность достигается
> изоляцией SQL в одном модуле и параметризованными запросами.

**Стек:** Python 3.11, `python-telegram-bot` v20+ (async), `APScheduler`,
`SQLite` → позже `PostgreSQL`, `python-dotenv`, `pytest` + `pytest-cov` +
`pytest-asyncio`, `ruff`.

---

## 7. Дорожная карта по фазам

Каждая фаза – отдельная ветка `phase/<N>-<slug>`, PR, зелёный CI, merge в
`main`, запись в `DEVELOPMENT_LOG.md`.

### Фаза 0 – Безопасность, git, GitHub-репозиторий

- Токен: `revoke` выполнен ✓; новый токен – локально в `.env`.
- `git init`, первый коммит каркаса.
- `.gitignore`, `.env`, `.env.example`, `requirements.txt`,
  `DEVELOPMENT_LOG.md`.
- Создать **private GitHub-репозиторий**, запушить `main`. ✅ Сделано:
  `github.com/James7underland/bot_reminder`.
- Branch protection: технически недоступен (Pro для private) → enforced
  дисциплиной (решение §9).
- **DoD:** репо на GitHub, `main` запушен, `.env`/токен вне git. ✅

### Фаза 1 – Окружение, инструменты, CI

> **Объединена с Фазой 2 в один PR (#1, ветка `phase/1-env-ci`).** Причина:
> Фаза 1 добавляет CI, на старте тесты красные; влить красную Фазу 1 в
> `main` нельзя («main всегда зелёный»). Делить – лишний churn. Поэтому
> Фазы 1+2 доводятся до зелёного на одной ветке и мержатся вместе.

- Наполнить `.venv` из `requirements-dev.txt`. ✅
- `pyproject.toml`: pytest (`testpaths=tests`, `pythonpath=.`), coverage,
  ruff. ✅
- **`.github/workflows/ci.yml`** (jobs lint/test, кэш pip). ✅
- Тесты: `pytest` запускается, ожидаемо «красный» – подтверждён дефект
  §2.2 (`no such table: tasks`). ✅
- **DoD:** CI работает на PR (#1); зависимости установлены. ✅

### Фаза 2 – Слой данных (`config.py`, `database.py`)

> Продолжает `plan/phase_2_db_and_config.md` с поправками §2.1–§2.3.

- `config.py`: загрузка `.env`, `TELEGRAM_BOT_TOKEN` (валидация),
  `DATABASE_PATH` (по умолчанию `./data/tasks.db`).
- `database.py` по контракту §2.3; SQL изолирован, запросы
  параметризованы (задел под PostgreSQL).
- Переписать `tests/conftest.py`: function-scope + temp-file БД. ✅
- `database.py`: `completed` → Python `bool` (контракт §2.3). ✅
- **DoD:** 8/8 тестов зелёные ✅; покрытие `database.py` **100%** ✅;
  далее CI зелёный → merge PR #1. (config.py 80%: непокрыт только
  `except ImportError` для опционального dotenv – не бизнес-логика.)
- Остаток (негативные тесты на пустой `description`/тип `user_id`) –
  можно добавить здесь же до merge или отдельным мелким PR.

### Фаза 3 – Ядро бота (`bot.py`)

> Продолжает `plan/phase_3_bot_core.md`.

- Хендлеры `/start`, `/help`, `/add`, `/list`, `/done`.
- `parse_add_command(text) -> (description, due_date|None)` – чистая
  функция. **Только форматы `YYYY-MM-DD HH:MM` и `DD.MM.YYYY HH:MM`**
  (естественный язык не реализуется – решение №4).
- Связка с `database.*`; `run_polling()`.
- Тесты: `test_parse.py` (таблица форматов, мусор, без даты),
  `test_handlers.py` (Telegram замокан, без сети). ✅
- **Сделано:** парсер переписан под 2 строгих формата (норм. к
  `YYYY-MM-DD HH:MM:SS`); 32 теста зелёные; `bot.py` 100%,
  `database.py` 100%, TOTAL 98.6%; `fail_under=90` включён; ruff чист,
  lint в CI стал блокирующим. `main()` помечен `# pragma: no cover`.
- **DoD:** CI зелёный → merge PR #2. Ручной сценарий add→list→done
  требует, чтобы пользователь создал `.env` с новым токеном (вне Claude).

### Фаза 4 – Напоминания (`scheduler.py`)

- `APScheduler`: job раз в минуту ищет наступившие `due_date`.
- Анти-дубль: миграция (`reminder_sent`/`notified_at`).
- Отправка пользователю, обработка ошибок (бот заблокирован и т.п.).
- Тесты: логика «пора напомнить» – чистая функция с инъекцией времени;
  тест анти-дубля; отправка мокается. ✅
- **Сделано:** `database.get_due_tasks(now)` + `mark_reminder_sent`;
  миграция `reminder_sent` (идемпотентная, + тест legacy-БД);
  `set_reminder` сбрасывает `reminder_sent`; `scheduler.py`
  (`check_and_send_reminders` – чистая логика, `setup_scheduler` –
  `pragma: no cover`); интегрирован в `bot.main()`. 39 тестов зелёные,
  `scheduler.py`/`database.py`/`bot.py` 100%, TOTAL 98.95%.
- **DoD:** CI зелёный → merge PR #3. Ручная проверка «уведомление один
  раз» – после настройки `.env` пользователем.

### Фаза 5 – Полный паритет с To Do (под-фазы 5.1…5.8)

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
  default = created – поведение неизменно, контракт сохранён);
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
  регистронезависимо для кириллицы – фильтр в Python); колонка
  `remind_before` (миграция); `set_remind_before`; `get_due_tasks`
  учитывает `datetime(due_date,'-N minutes')`; команды `/search`,
  `/remindbefore`; 155 тестов, покрытие 99.77%. PR #10.
  (Несколько напоминаний на задачу – вне объёма 5.7, возможный полиш.)
- 5.8 Часовые пояса. ✅ Таблица `user_settings`; `tzutil` (zoneinfo:
  `valid_timezone`/`to_utc`/`to_local`); `get_timezone`/`set_timezone`;
  `due_date` хранится в UTC, ввод (`/add`,`/reschedule`) конвертируется
  из пояса пользователя, вывод (`/list`) – обратно; scheduler сравнивает
  в UTC; команда `/timezone`. Дефолт UTC → identity (контракт и 155
  прежних тестов не затронуты). 171 тест, покрытие 99.78%. PR #11.
- **DoD каждой под-фазы:** фича работает, покрытие новой логики ≥ 90%, CI
  зелёный, merge, лог обновлён.

> **Фаза 5 завершена полностью (5.1–5.8) – достигнут паритет с
> Microsoft To Do.** Далее – Фаза 6 (PostgreSQL, VPS, CD).

### Фаза 6 – усиление, деплой на VPS, CD

Разбита на 6a (автономно) и 6b (требует VPS/решения).

**Фаза 6a – автономная инфраструктура. ✅ (PR #12)**
- Bump GitHub Actions до Node 24 (`checkout@v5`, `setup-python@v6`) –
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

**Фаза 6b – требует пользователя / отдельным решением:**
- VPS (хост/SSH), GitHub Secrets (`DEPLOY_HOST/USER/SSH_KEY`),
  `.env` с новым токеном → «оживление» CD по runbook.
- **PostgreSQL** (отложено сознательно): SQLite достаточно для одного
  процесса; SQL изолирован в `database.py`, миграция – отдельная фаза по
  реальной потребности (`psycopg`, `DATABASE_URL`, PG-сервис в CI).
- **DoD 6b:** бот 24/7 на VPS, CD по merge в `main` работает.

---

## 8. Сквозные правила (Definition of Done каждой фазы)

1. Новый код покрыт тестами (позитив + негатив); `pytest -q` зелёный.
2. Покрытие бизнес-логики ≥ 90%.
3. Никаких секретов в коде/гите; `.env` вне репозитория; секреты CI/CD – в
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

## 10. Ближайшие шаги (история – Фаза 0)

1. §9 подтверждён (private, gh CLI). **Фаза 0 в работе.**
2. Установить `gh` → пользователь `gh auth login` → создать репо, push `main`.
3. Фаза 1 (окружение + CI) → Фаза 2 (сделать существующие тесты зелёными).

> Фазы 0–6 завершены и развёрнуты (бот 24/7 на VPS, CI/CD живой). См.
> `DEVELOPMENT_LOG.md`.

---

## 11. Фаза 7–8 – Telegram Mini App (новая архитектура)

**Решения пользователя:** HTTPS – Cloudflare Tunnel; порядок – бэкенд
раньше UI; «срок» = дата+время. Slash-команды остаются фолбэком.

**Модель (Фаза 7):** разделены две сущности –
- `deadline` (срок): прошёл и не выполнено → «просрочено» (красный в UI)
  + одноразовое уведомление о просрочке;
- `reminder_at` (напоминание): отдельное время → уведомление «пора».

### Фаза 7 – редизайн модели (бэкенд, без инфраструктуры)
- **7.1 ✅ (PR #17):** колонки `deadline`/`reminder_at`/
  `overdue_notified`; миграция (`due_date`→`reminder_at`, поведение
  сохранено); функции `set_deadline`/`set_reminder_at`/
  `get_due_reminders`/`get_overdue_tasks`/`mark_overdue_notified`;
  182 теста, покрытие 99.8%.
- **7.2 ✅ (PR #18):** планировщик: напоминания из `reminder_at`, отдельные уведомления о просрочке из `deadline` (общий `_notify`, анти-дубль у каждого); 184 теста.
  уведомления о просрочке из `deadline` (анти-дубль у каждого).
- **7.3 ✅ (PR #19):** `/deadline`, `/remind` (новая модель, tz→UTC, off-сброс); `/add` и `/reschedule` пишут `reminder_at`; obsolete `/remindbefore` удалён (оффсет-модель ушла); хелп обновлён; 191 тест. **Фаза 7 завершена.**

### Фаза 8 – HTTP API + Telegram Mini App
- **8.1 ✅ (PR #20):** `webapp.py` – FastAPI; `validate_init_data`
  (HMAC-проверка Telegram `initData`, чистая функция); REST: задачи
  (list/create/complete/uncomplete/patch, флаг `overdue`), списки;
  проверка владения задачей (404 на чужую); tz→UTC. 212 тестов,
  `webapp.py` 99%.
- **8.2 ✅ (PR #21):** `static/index.html` – Mini App (Telegram WebApp JS, X-Init-Data, список active/done, чекбокс, звезда, datetime-local срок/напоминание, красная подсветка просрочки, списки/создание); FastAPI `StaticFiles` смонтирован после API (приоритет /api); 214 тестов.
  срока/напоминания, подсветка просроченных) + раздача статики FastAPI.
- **8.3a ✅ (PR #22):** инфраструктура webapp: `deploy/bot_webapp.service` (uvicorn 127.0.0.1:8080), `deploy/cloudflared.service`, deploy.yml рестартит и webapp (best-effort), runbook §6 в DEPLOYMENT.md.
- **8.3b (с пользователем):** Caddy на VPS → `https://ernstgku.beget.tech` (A-запись Beget→IP, порты 80/443, Let's Encrypt), регистрация Mini App в @BotFather. `deploy/Caddyfile` + runbook §6 – PR #23.
  @BotFather, запуск webapp на сервере (вместе с ботом) – пошагово с
  пользователем.
- Тестовая дисциплина: логика – в Python под pytest; Mini App – тонкий
  клиент над протестированным API.

### Фаза 8.4–8.7 – Mini App до паритета с ботом

8.1/8.2 – MVP UI. Пользователь запросил полный паритет; расширяем
API+фронтенд итерациями (PR → CI → авто-деплой; туннель не трогается).

- **8.4 ✅ (PR #24):** повторы (`recurrence` в PATCH + clear, валидация)
  и «Мой день» (`GET /api/myday`, `POST /api/tasks/{id}/myday`,
  `_today_local` по tz пользователя); во фронтенде – селектор повтора,
  тумблер «Мой день», кнопка «в Мой день», повтор в мете. 217 тестов.
- **8.5 ✅ (PR #25):** подзадачи (steps CRUD: GET/POST/toggle/DELETE под `/api/tasks/{id}/steps`, ownership через задачу) + заметки (`notes`/`clear_notes` в PATCH); фронтенд – textarea заметки, чек-лист подзадач с добавлением/✕/тогглом. 220 тестов.
- **8.6 ✅ (PR #26):** поиск (`GET /api/tasks?search=` → `search_tasks`, перекрывает фильтры) и сортировки (`?sort=important|due|alpha|created` → `get_tasks(sort=)`); фронтенд – строка поиска (debounce) + селектор сортировки. 222 теста.
- **8.7 ✅ (PR #27):** списки – PATCH/DELETE `/api/lists/{id}` (ownership), перенос `POST /api/tasks/{id}/list`; настройки – GET/PUT `/api/settings` (часовой пояс, валидация ZoneInfo→422); фронтенд – ✎/🗑 списка, селектор «Список» в задаче, ⚙ часовой пояс. 225 тестов. **Mini App = паритет с ботом.**
- **8.8 (PR #28, инфра):** SNI-роутер на :443 без вреда VPN. VPN =
  VLESS+Reality на :443 (Amnezia) → xray-fallback и второй IP
  недоступны; решение – **nginx `stream`+`ssl_preread` на :443**: SNI
  домена Mini App → Caddy:8443 → webapp, всё прочее → xray
  (перепубликован на 127.0.0.1:8444; конфиг xray НЕ тронут).
  `deploy/nginx-sni.conf`, `Caddyfile` (https_port 8443), runbook §6 +
  откат. Пересоздание контейнера – по `docker inspect` пользователя
  (commit-бэкап, Reality-ключи сохраняются).
- **8.9 (PR #29, инфра):** домен решён. `ernstgku.beget.tech`
  (технический Beget) A-запись менять нельзя → тупик. Зарегистрирован
  **`reminderr.ru`** (Beget, .RU 199 ₽/год), A → VPS
  `155.212.227.167` (Beget DNS, NS не трогаем). Конфиги
  `deploy/Caddyfile`/`nginx-sni.conf`/`DEPLOYMENT.md` переведены на
  `reminderr.ru`. Путь А (нативный `https://reminderr.ru` через
  SNI-роутер) – то, что изначально и хотел пользователь.
- **8.3b (с пользователем):** HTTPS наружу. Caddy отпал – :443 занят
  VPN (`amnezia-xray`). Идём через `cloudflared` (исходящий, без
  конфликта): быстрый туннель работает (`*.trycloudflare.com`),
  оформляется в `cloudflared-quick.service`; стабильный URL – путь B
  (домен в Cloudflare) по желанию.

---

## 12. Фаза 9 – допиливание паритета с Microsoft To Do

Реалистичный остаток (после Фазы 8): custom recurrence, smart-views,
snooze, ручной порядок, мелочи UI. Вне scope: файловые вложения,
расшаривание списков (требуют отдельной подсистемы/модели прав).

- **9.1 ✅ (PR #30):** Custom recurrence. Расширены значения
  `recurrence`: `every:N:d/w/m/y` и `weekdays:MO,WE,FR` (помимо легаси
  пресетов). `is_valid_recurrence`, обновлён `next_occurrence` и
  `complete_task` (custom тоже спавнит следующий экземпляр). API PATCH
  валидирует новые формы. Фронтенд: в панели задачи опция «свой
  шаблон» с «каждые N единиц» / «по дням недели» (Пн…Вс). 245 тестов.
- **9.2 ✅ (PR #31):** Smart-views в Mini App. БД: `get_planned` (актив + дедлайн ИЛИ напоминание, сорт по дедлайну, потом напом., потом created) и `get_important_tasks` (актив + important=1, сорт по дедлайну). API `GET /api/planned` и `GET /api/important` (ownership через initData). Фронтенд: вместо чекбокса «Мой день» – селектор «Все / Мой день / Планируется / Важно» – переключает запрос. 247 тестов.
- **9.3 ✅ (PR #32):** Snooze напоминаний. БД: `snooze_reminder(task_id, minutes) -> bool` сдвигает `reminder_at` к `now(UTC)+minutes` и сбрасывает `reminder_sent`. API: `POST /api/tasks/{id}/snooze` (422 при `minutes<=0`, 404 на чужую). Фронтенд: кнопки `+15 мин`, `+1 ч`, `до завтра 9:00` (последняя считает локальную дельту до 09:00 завтра). 249 тестов.
- **9.4 ✅ (PR #33):** Ручной порядок задач. БД: колонка `order_index` (миграция: бэкфилл по `id`), `add_task` ставит `max+1` для пользователя, дефолтная сортировка `get_tasks`/`get_tasks_by_list` теперь по `order_index, created_at` (sort=`created` сохраняет старую семантику). `move_task_up`/`move_task_down` свопят `order_index` с ближайшим активным соседом того же user+list (включая `list_id IS NULL`); крайняя и выполненная задача → False. API: `POST /api/tasks/{id}/move-up` / `…/move-down` (404 на чужую, тело `{"moved": bool}`). Фронтенд: в строке задачи две маленькие кнопки ▲/▼ рядом со звездой. 257 тестов.
- **9.5 ✅ (PR #34):** UI-полировка. (a) Прогресс подзадач: `get_steps_counts(user_id)` – один SQL `GROUP BY task_id`, без N+1; декорируется в `/api/tasks` / `/api/myday` / `/api/planned` / `/api/important` полями `steps_done` / `steps_total`; в Mini App в meta задачи появляется `📋 N/M`. (b) Цвет списка: колонка `lists.color` (`#0088CC` по умолчанию), валидация `^#[0-9A-Fa-f]{6}$`, `set_list_color(list_id, color)`; PATCH `/api/lists/{id}` принимает `{name?, color?}` и возвращает полный dict списка (422 на пустое тело/битый цвет); в Mini App кнопка 🎨 открывает нативный color picker, опции в селекте окрашены `color: <hex>`. 261 тест.

## Phase 10 – стабильность и эксплуатация

Жалоба пользователя: периодически залипает менюшка в Mini App
(невозможно выбрать цвет или ввести имя списка) – помогает только
перезапуск. Это **продолжение паритета**: пользователь воспринимает
такие хвосты как «бот сырой», а не «новая фича не нужна».

- **10.1 ✅ (PR #35):** Залипания UI и блокировки БД.
  (a) Frontend: убраны нативные `window.alert/prompt/confirm` – в
  Telegram WebView они не возвращают фокус в JS-цикл, из-за чего
  следующие клики «не доходят». Введены обёртки `uiAlert/uiConfirm/
  uiPrompt`, поверх `Telegram.WebApp.showAlert/showConfirm` (где есть)
  и кастомного inline-оверлея для prompt (поддержка Enter/Escape и
  Telegram BackButton как «Отмена»). Для color-picker – гарантированный
  cleanup скрытого `<input type="color">` на blur и 60-сек таймауте.
  (b) Backend: `get_connection()` теперь включает `journal_mode=WAL`
  и `busy_timeout=5000` – без этого `bot_reminder` (планировщик) и
  `bot_webapp` (HTTP API) пишут в одну БД через эксклюзивный лок, и
  запросы из Mini App могли висеть на блокировке. Регресс-тест
  проверяет, что новые соединения отдают WAL и 5-сек ожидание.

- **10.2 ✅ (PR #36):** Backup/restore – пользовательский экспорт/импорт.
  `export_user_data(user_id)` отдаёт полный JSON-снимок (версия 1):
  списки (с цветами), задачи (с привязкой к именам списков, а не id –
  иначе импорт упирался бы в чужие id), подзадачи, часовой пояс.
  `import_user_data(user_id, payload, mode="merge"|"replace")` –
  `merge` дописывает рядом (по имени списка не дублирует), `replace`
  предварительно вычищает данные пользователя. Все вставки в одной
  транзакции – при сбое в середине rollback оставляет БД целой.
  API: `GET /api/export` и `POST /api/import` (422 на невалидный
  payload/режим). Кривые элементы (пустое имя/описание, не-dict в
  tasks, плохой цвет) пропускаются, не падая. Frontend: 📦 скачивает
  `reminder-backup-<ts>.json`, ↩ открывает файл-пикер и спрашивает
  «replace» vs «merge». 269 тестов.
- **10.8 ✅ (PR #42):** Виджет статистики в Mini App. В шапке справа
  от заголовка маленький бэйдж `N активн. · ★ M · 📋 K`, тянется из
  `/api/stats` (Phase 10.3) после каждого `load()`. По клику
  открывается `uiAlert` с детальной разбивкой: активных, важных,
  выполненных, списков, открытых подзадач, дата самой старой
  активной. Используется флаг `_silent` для запроса – если
  `/stats` недоступен, бэйдж просто скрыт без тоста. 294 теста.
- **10.7 ✅ (PR #41):** Undo для удаления списка. БД: колонка
  `lists.deleted_at TEXT` (миграция), `delete_list` теперь
  soft-delete (ставит `deleted_at = now()`, задачи сохраняют
  `list_id` на время окна отмены). `get_lists` исключает удалённые
  по умолчанию, `include_deleted=True` для restore-эндпоинта.
  `restore_list(id)` снимает пометку. `purge_deleted_lists(hours=24)`
  физически удаляет старые с отвязкой задач – вызывается раз в час
  через новый scheduler job `purge_deleted`. `import_user_data` в
  merge-режиме игнорирует soft-deleted списки по имени. API:
  `POST /api/lists/{id}/restore` (404 на чужую/активную). Frontend:
  при удалении списка вместо confirm – `uiUndoToast` с кнопкой
  «Отменить» на 8 сек (вызывает restore). 294 теста.
- **10.6 ✅ (PR #40):** Drag-and-drop переупорядочивание. `database.
  reorder_task(task_id, after_task_id)` ставит задачу сразу после
  указанной в той же подгруппе (user + list), `after=None` → в начало;
  одна транзакция с пересчётом всех `order_index = i+1`. API:
  `POST /api/tasks/{id}/reorder {after: int|null}` (404 на чужую,
  409 на несовместимую подгруппу). Frontend: pointer-events drag c
  ручкой `⠿` и оптимистичной перерисовкой DOM перед PATCH'ом; включён
  только в режимах, где порядок осмыслен (Все/список без сортировки/
  без поиска). 289 тестов.
- **10.5 ✅ (PR #39):** Picker часовых поясов. Курируемый список ~58
  городов в `tzutil.list_common_timezones()` с группами Россия/СНГ/
  Европа/Азия/Америка/Океания/Африка и текущим смещением (UTC±HH:MM,
  пересчитывается с учётом DST). `GET /api/timezones` отдаёт его под
  initData-авторизацией. Фронтенд: 4-й универсальный модал `uiSelect`
  (с поиском по подстроке и группировкой) заменил free-text prompt;
  выбранный пояс сохраняется через PUT `/api/settings`. Тост `OK
  Часовой пояс сохранён` вместо blocking `uiAlert`. 283 теста.
- **10.4 ✅ (PR #38):** Mini-App polish. (a) Тост-уведомления об ошибках:
  `api()` теперь не глотает не-401 ошибки молча – показывает `uiToast`
  с серверным `detail` или HTTP-кодом; сетевые сбои (`fetch` reject)
  тоже сурфятся. Доступен флаг `_silent` в опциях запроса, если
  нужно явно подавить (пока не используется). (b) Сохранение состояния
  UI: `view` (Все/Мой день/Планируется/Важно), `listId`, `sort`,
  `showDone` персистятся в `localStorage` через `saveUI/loadUI`; при
  следующем открытии Mini App открывается на том же фильтре. Тесты
  не изменены – frontend-only PR, 279 проходят.
- **10.3 ✅ (PR #37):** Здоровье и логирование.
  (a) `/healthz` теперь делает `SELECT 1` через `db_ping`, отдаёт
  `{ok, db, uptime_seconds, tasks_total, tasks_active, lists_total,
  users}`; если БД не отвечает → HTTP 503 (внешний монитор/systemd
  таймер видит). При отказе `get_global_counts` 200 OK не ломается,
  только лог-варнинг.
  (b) `GET /api/stats` – сводка для текущего пользователя
  (`active`/`completed`/`important`/`lists`/`steps_open`/
  `oldest_open_at`); под initData-авторизацией.
  (c) `logsetup.setup_logging(name)` – единая идемпотентная настройка:
  stdout-хендлер (journald) + RotatingFileHandler 5×10 МБ при заданном
  env `LOG_DIR`. Шумные сторонние логгеры (httpx/httpcore/apscheduler/
  telegram) глушатся до WARNING (httpx пишет URL Telegram API с
  токеном – критично не выводить на INFO). `bot.py`/`webapp.py`
  перевешены на `setup_logging`. systemd-юниты (`bot_reminder.service`,
  `bot_webapp.service`) получают `Environment=LOG_DIR=...` и
  `ExecStartPre` для создания каталога. 279 тестов.

## Phase 11 – Mini-App-only бот + заметки

Запрос пользователя: «Команды бота больше не нужны – у нас же есть
Mini App» + «Нужно добавить раздел с заметками (отдельный раздел)».

- **11.1 ✅ (PR #43):** Стрипнут весь чат-интерфейс. `bot.py` ужат
  с ~810 строк до ~140 – оставлены только `start`/`help` (с WebApp-
  кнопкой), `fallback_text` (любое не-командное сообщение → подсказка
  открыть Mini App) и `error_handler`. Удалены ~25 командных хендлеров
  (`/add`, `/list`, `/done`, `/edit`, `/deadline`, `/remind`,
  `/reschedule`, `/lists`, `/newlist`, `/renamelist`, `/dellist`,
  `/movetask`, `/repeat`, `/important`, `/unimportant`, `/addstep`,
  `/steps`, `/stepdone`, `/stepundone`, `/delstep`, `/note`,
  `/delnote`, `/myday`, `/search`, `/timezone`). Чистка тестов:
  удалены 4 чисто-handler-файла (`test_handlers.py`, `test_parse.py`,
  `test_edit.py`, `test_deadline_cmd.py`); из mixed-файлов
  (`test_lists`, `test_important`, `test_myday`, `test_recurring`,
  `test_steps_notes`, `test_search_reminders`, `test_timezones`)
  вырезаны handler-тесты – DB-слой остаётся, пользовательские сценарии
  живут в `test_webapp.py`. Планировщик (рассылка напоминаний и
  purge soft-deleted) сохранён. 196 тестов, TOTAL 99.30%.
### Phase 11.25 – Фикс bulk-бара (всегда висел)

- **11.25 ✅:** Корень бага выделения: `.bulk-bar{display:flex}` перебивал
  атрибут `[hidden]` (равная специфичность, авторский стиль > UA), из-за
  чего панель массовых действий висела ВСЕГДА — показывала «0 выбрано» со
  всеми кнопками, «Отмена» не прятала её, и в архиве были видны все
  кнопки (т.к. `_applyBulkBarMode` отрабатывает только при реальном входе
  в режим выделения, которого не было — бар уже висел). Фикс — одна
  строка CSS `.bulk-bar[hidden]{display:none}` (специфичность (0,2,0) >
  (0,1,0)), теперь `hidden` главнее. Проверено в браузере (preview):
  display none→flex→none по `hidden`; в архиве видна только «Вернуть».

### Phase 11.24 – Откат кнопки fullscreen

- **11.24 ✅:** По просьбе пользователя убрана кнопка «на весь экран»
  (⛶), добавленная в 11.23-PR6: удалён `#fsBtn` из шапки,
  `_setupFullscreen()` и его вызов, CSS `body.tg-fullscreen`. Иконки
  maximize/minimize в `ICONS` оставлены (не мешают). `_setupWindowMode`
  снова только `ready()`/`expand()` + body-класс. Альтернатива на
  будущее, если понадобится: Launch Mode → Fullscreen в BotFather.

### Phase 11.23 – Доп. замечания после проверки (7 пунктов)

Запрос после проверки 11.22: ещё 7 правок. Реализуется тремя PR (PR4-PR6).
Нумерация замечаний: #1 fullscreen (повтор), #2 заголовок раздела,
#3 «Вернуть» в архиве, #4 формат даты ДД.ММ.ГГГГ, #5 сброс полей при
выполнении, #6 баг фантомного выделения, #7 уведомления без кнопок.

- **11.23-PR6 ✅:** Повторная попытка fullscreen через Bot API 8.0 (#1).
  После включения Main App в BotFather (reminderr.ru) возвращаем кнопку
  ⛶ в шапке. `_setupFullscreen()`: показывается только если
  `tg.requestFullscreen` есть и `tg.isVersionAtLeast('8.0')`. Клик
  переключает `requestFullscreen`/`exitFullscreen`; подписка на
  `fullscreenChanged` (меняет иконку maximize↔minimize, body-класс
  `tg-fullscreen`) и `fullscreenFailed` (тост с причиной, кроме
  ALREADY_FULLSCREEN). CSS: в `tg-fullscreen` шапка сдвигается на
  safe-area (`--tg-safe-area-inset-top`/`env(safe-area-inset-top)`),
  чтобы не уезжать под чёлку/статус-бар. На клиентах < 8.0 кнопка
  просто скрыта (graceful degradation, проверено в preview). Чисто
  фронт. (Альтернатива без кода: Launch Mode → Fullscreen в BotFather.)
- **11.23-PR5 ✅:** Сброс полей при выполнении + уведомления без кнопок
  (#5, #7). #5: `complete_task` теперь при переводе в архив очищает
  `deadline`, `reminder_at`, `important` и сбрасывает `reminder_sent`/
  `overdue_notified` (плюс `completed_at` из 11.22). Это чинит баг: при
  возврате задачи в активные больше НЕ «выстреливает» старое
  просроченное напоминание/просрочка. Рекуррентность не ломается —
  следующий экземпляр строится из снимка `row` до UPDATE. #7: из
  уведомлений убраны inline-кнопки +15м/+1ч/✓Готово — `_notify` шлёт
  простой текст (удалены `_reminder_keyboard`, параметр `with_buttons`,
  импорт telegram-кнопок в scheduler). В `bot.py` удалён
  `reminder_callback` (snz:/done:) и его регистрация/импорты. Тесты:
  −5 callback-тестов (test_hardening), 2 scheduler-теста проверяют
  отсутствие `reply_markup`, +1 на #5. 253 теста.
- **11.23-PR4 ✅:** Заголовок раздела + «Вернуть» в архиве + формат даты
  + фикс выделения (#2, #3, #4, #6). #2: `_updateTitle()` ставит в шапку
  имя текущего раздела/вида (Важно / Мой день / Запланировано / Архив /
  имя списка / Все задачи / Заметки) вместо постоянного «Мои задачи».
  #3: в bulk-баре в архиве показывается только кнопка «Вернуть»
  (bulk-uncomplete), остальные действия скрыты (`_applyBulkBarMode`).
  #4: отображение дат – `fmtDisp()` → ДД.ММ.ГГГГ ЧЧ:ММ (срок/напоминание/
  выполнение), `shortDate`/stats → locale ru-RU; сериализация для API
  (`fmt`) не тронута. #6: в `load()` выделение сверяется с реально
  отрисованными задачами – устаревшие id выкидываются, при пустом наборе
  выходим из режима (чинит «фантомный» счётчик и неработающую отмену);
  смена раздела сбрасывает выделение. Проверено в браузере (preview):
  JS парсится без ошибок. Чисто фронт – 257 тестов без изменений.
- **11.22 итог:** все 15 финальных замечаний закрыты (PR1-PR3).

### Phase 11.22 – Финальные замечания (15 пунктов)

Запрос пользователя: финальный список из 15 правок; «если одобрю – работа
завершена». Реализуется тремя PR.

- **#1** «Открыть» в меню чатов Telegram (Main Mini App у BotFather).
- **#2** Полностью убрать fullscreen (⛶) – идею масштабирования отменяем.
- **#3** В «Архиве» убрать тумблер «Показывать выполненные».
- **#4** Кнопки ▲▼★ срабатывали через раз (SVG-иконка съедала клик).
- **#5** Шрифты/кнопки в стиле BotFather.
- **#6** Одиночный тап по задаче = выделить (для bulk), не открывать/не
  редактировать название.
- **#7** Снизу карточки – полоска со стрелкой, по ней раскрывается описание.
- **#8** Из описания убрать «Отложить»; снуз – на выбранную дату/время.
- **#9** В «Заметках» убрать напоминания (противоречит смыслу).
- **#10** Время напоминания/просрочки показывать в часовом поясе настроек.
- **#11** В архиве нельзя помечать важными, но ▲▼ и перемещение работают.
- **#12** При помещении в архив показывать время выполнения.
- **#13** Везде среднее тире (–) вместо длинного (–).
- **#14** В заметках не показывать счётчик активных задач.
- **#15** Счётчик «активн.» – по разделам; добавление задачи – в текущий
  раздел; в архив через «+» нельзя (только при выполнении).

- **11.22-PR3 ✅:** Заметки без напоминаний + среднее тире + дизайн +
  кнопка «Открыть» (#9, #13, #5, #1). #9: удалены напоминания заметок –
  фронт (поле «Напомнить», кнопка «Убрать напом.», badge ⏰, CSS .nrem),
  API (NotePatch.reminder_at/clear_reminder + ветка PATCH), планировщик
  (note-pass + _note_text + импорты), БД-функции set_note_reminder/
  get_due_note_reminders/mark_note_reminder_sent и note-reminder из
  export/import. Колонки notes.reminder_at/reminder_sent оставлены
  дремать (миграция идемпотентна). #13: сплошная замена длинного тире
  (U+2014) на среднее (U+2013) – 764 вхождения в 23 файлах (бинарная
  замена, CRLF сохранён). #5: системный шрифт-стек как у Telegram
  (Segoe UI/Roboto/SF) + сглаживание; кнопки – заливка theme-цветом,
  font-weight 600, отклик на нажатие. #1: глобальная кнопка-меню
  «Открыть» (Mini App) задаётся в post_init без chat_id – видна во всех
  чатах сразу, как у BotFather; per-chat вызов в start() оставлен
  подстраховкой. (Main Mini App в BotFather – ручной шаг, описан в PR.)
  257 тестов.
- **11.22-PR2 ✅:** Часовой пояс + время выполнения + посекционные счётчики
  (#10, #12, #15). #10: `_decorate` теперь конвертирует `deadline`/
  `reminder_at`/`completed_at` из UTC в часовой пояс пользователя
  (`_to_local_or_none`), `overdue` считается ДО конвертации (в UTC).
  Введены `_decorate_many`/`_decorate_one` – tz/now/counts считаются раз
  на запрос. #12: колонка `tasks.completed_at` (+миграция); ставится в
  `complete_task`/`mark_task_done`, снимается в `mark_task_undone` и
  bulk-`uncomplete`; включена в export/import; на карточке выполненной
  задачи – «✓ выполнено <локальное время>». #15: счётчик в шапке –
  посекционный (в «Важном» – важные, в списке – активные списка, в
  архиве – «N в архиве»), считается из уже загруженного списка;
  `addTask` наследует раздел (важное/мой день/выбранный список); в архив
  через «+» добавлять нельзя – строка ввода и FAB скрыты во view archive.
  260 тестов (+5: completed_at, bulk-uncomplete, tz-конвертация
  `_decorate`, round-trip срока, архивный completed_at в tz).
- **11.22-PR1 ✅:** Взаимодействие со списком + правила архива
  (#2,#3,#4,#6,#7,#8,#11,#14). Фронтенд: удалён весь fullscreen-код
  (`_setupWindowMode` сведён к `ready()`/`expand()`+body-класс; вырезаны
  `fsBtn`, `_enterFullscreen`, pseudo-fs/баннер, CSS `.fs-*`). Делегат
  клика по строке использует `e.target.closest("[data-act]")` – SVG
  больше не глотает клик (#4). Одиночный тап по `.row` вне кнопок =
  enter/toggle select (#6); раскрытие панели – по `.expand-strip`
  снизу (#7). Из панели убрана секция «Отложить» (#8). Звезда «важно»
  не рендерится в архиве (#11); тумблер showDone виден только в обычном
  списке (#3); drag/стрелки включены и в архиве (#11); stats-badge
  скрыт в «Заметках» (#14). Бэкенд: `_move_task`/`reorder_task`
  оперируют в группе своего `completed` (архив – кросс-списочно),
  `get_archived_tasks` сортирует по `order_index` – ручной порядок в
  архиве сохраняется. 255 тестов.
- **11.21 ✅ (PR #64):** Fullscreen – полная диагностика через нативный
  `showAlert` (пятый заход; впоследствии фича удалена в 11.22-PR1 по
  требованию пользователя).
- **11.20 ✅ (PR #63):** Fullscreen – instant CSS feedback + persistent banner.
  Четвёртый заход после жалобы «всё ещё не включается». Изменение
  стратегии: pseudo-fs ВКЛЮЧАЕТСЯ СРАЗУ на клик (мгновенный визуальный
  отклик – body занимает 100vw/100vh окна), параллельно в фоне пробует
  TG-API + browser-API. Если реальный fullscreen сработал – pseudo-fs
  снимается. Если нет – pseudo-fs остаётся + появляется жёлтый
  **persistent-баннер** наверху: «CSS-режим: содержимое заполняет окно
  Telegram, но само окно увеличить может только Telegram. Обнови
  Telegram Desktop до 11.5+». В баннере точная диагностика причин
  отказа TG/браузера. ✕ скрывает баннер. Принципиальное ограничение
  объявлено явно: из WebApp нельзя увеличить окно TG-клиента – только
  через Bot API 8.0 (TG ≥ 11.5).
- **11.19 ✅ (PR #62):** Напоминания для заметок. БД: колонки
  `notes.reminder_at TEXT`, `notes.reminder_sent INTEGER` (миграция +
  CREATE TABLE). `set_note_reminder(id, utc|None)` сбрасывает
  `reminder_sent`; `get_due_note_reminders(now)` для планировщика;
  `mark_note_reminder_sent(id)` после доставки. Scheduler:
  `_notify(items, prefix, mark, text_for=...)` обобщён – для задач
  использует `_task_text(t)=t.description`, для заметок –
  `_note_text(n)=title || body[:140]`. Третий вызов в
  `check_and_send_reminders` шлёт «📓 Заметка: …» без snooze-кнопок
  (у заметки нет состояния «выполнено»). API: PATCH `/api/notes/{id}`
  принимает `reminder_at` и `clear_reminder`; пустой PATCH с одним
  только напоминанием не даёт 422. Фронтенд: в редакторе заметки –
  `<input type="datetime-local">` «Напомнить» + кнопка «Убрать
  напом.»; на карточке – badge `⏰ <дата>` если задано. Экспорт/импорт
  переносит `reminder_at` в payload. 253 теста.
- **11.18 ✅ (PR #61):** Floating action button (FAB) для добавления.
  Круглая «+» в правом нижнем углу, 56×56 px, акцентный цвет
  (`--btn`), мягкая тень с подъёмом на hover. В разделе «📋 Задачи»
  клик скроллит к input «+ Новая задача» и фокусирует его. В разделе
  «📓 Заметки» – открывает редактор новой заметки (триггерит клик
  на `#newNoteBtn`). Скрывается в multi-select-режиме через
  `body.select-mode .fab { opacity: 0 }`. Иконка – SVG plus
  (`stroke-width: 2.5` для выделения).
- **11.17 ✅ (PR #60):** SVG-иконки в кнопках (вместо эмодзи). Lucide-стиль:
  `stroke="currentColor"`, viewBox `0 0 24 24`, 20×20 px. `ICONS{...}`
  словарь + `applyIcons(root)` хелпер, читает `data-icon="name"`
  атрибуты. Заменены: `≡`→menu, `⋯`→more, `⛶/🗗`→maximize/minimize,
  `✕`→x, `✓`→check, `★/☆`→star/star-off, `📁`→folder, `⠿`→grip,
  `▲▼`→chev-up/down, `+`→plus, `✎`→pencil, `🎨`→palette, `🗑`→trash.
  Применяется к статическим элементам на DOMContentLoaded и к
  динамическим (rows, drawer-lists) – после рендера. Эмодзи остались
  там, где они контентные: 📋 «Задачи» / 📓 «Заметки», 🗓 «Мой день»,
  ☐/☑ в markdown, 📌 на закреплённых заметках, empty-state-иконки.
- **11.16 ✅ (PR #59):** Empty-states по видам + анимация выполнения
  задачи. Серое «Пока нет задач» заменено на полноценный компонент
  `.empty-state` (большая эмодзи 64px, заголовок, подсказка); тексты
  индивидуальные для each view: ☀️ Сегодня свободно / 📅 Нет планов /
  ⭐ Нет важных / 🗂 Архив пуст / ✨ Пока нет задач / 🔎 Ничего не
  найдено. Для заметок – 📓 Заметок пока нет (с подсказкой про
  markdown). Анимация при отметке задачи как выполненной: 350 мс
  fade-out + slide-right через `@keyframes task-complete`. Возврат
  в активные – без анимации (тут она бы только мешала).
- **11.15 ✅ (PR #58):** Fullscreen – диагностика + CSS pseudo-fs fallback.
  Третий заход после жалобы «всё ещё не работает». Кнопка ⛶ теперь
  ВСЕГДА видна на десктопе (раньше скрывалась, если API не поддержано).
  На клик: 1) пробует `tg.requestFullscreen()`, ждёт `fullscreenChanged`
  350 мс; 2) если TG молча игнорирует – пробует `document.documentElement
  .requestFullscreen()`; 3) если оба упали (например, iframe permissions
  policy блокирует) – применяется `body.pseudo-fs { position:fixed;
  inset:0; width:100vw; height:100vh; z-index:9999 }` и в тосте
  выводится **точная диагностика**: на каком шаге что произошло
  (`tg → ignored`, `browser → ex: NotAllowedError`, ...). Так
  пользователь видит, в чём корень.
- **11.14 ✅ (PR #57):** Sidebar-drawer + компактная шапка (как в MS To Do).
  Header ужат до строки: `≡ Заголовок [stats] ⛶ ⋯`. Нажатие `≡` открывает
  левую панель навигации с: (a) переключателем разделов «📋 Задачи / 📓
  Заметки»; (b) видами задач (Все / Мой день / Планируется / Важно /
  Архив); (c) списками с цветной точкой, hover-action'ами ✎/🎨/🗑,
  кнопкой `+` для создания. Overflow `⋯` ведёт к редким действиям
  (часовой пояс / экспорт / импорт). Внутри tasksSection остался только
  компактный input «+ Новая задача» и inline-bar с поиском + сортировкой
  (✦ значки вместо словесных меток) + переключателем «✓». Все старые
  `#listSel`/`#viewSel`/`#newList`/`#tzBtn`/etc. остались скрытыми
  и работают как раньше – drawer и overflow программно дёргают их клики
  (минимум переделок логики). 248 тестов остаются зелёными.
- **11.13 ✅ (PR #56):** Fullscreen – двухуровневая стратегия. (a)
  Сначала пробуем `tg.requestFullscreen()` (Bot API 8.0, TG Desktop
  11.5+). (b) Если не поддержано / отказало – fallback на нативный
  `document.documentElement.requestFullscreen()` (Chromium-based TG
  Desktop его честно поддерживает; срабатывает при user-gesture клика
  ⛶). `_isFullscreen()` объединяет оба индикатора. Слушаются и
  `tg.onEvent('fullscreenChanged'/'fullscreenFailed')`, и
  `document.fullscreenchange` – иконка ⛶↔🗗 синхронизируется в обоих
  случаях. Также убрано `body.is-desktop {max-width: 760px}` – оно
  оставляло чёрные поля по бокам даже в OS-fullscreen.
- **11.12 ✅ (PR #55):** Контраст заметок + рабочий fullscreen + дизайн-полировка.
  (a) Заметки: внутри карточки ВСЕ тексты принудительно `#1f2937`
  (title), `#475569` (meta), `#1d4ed8` (ссылки), `#16a34a` (✓-чекбоксы)
  через `!important` – в dark-теме TG больше не белое-на-светлом.
  Тени + hover-lift для воздуха. (b) Fullscreen-toggle: `tg.isVersion
  AtLeast("8.0")` определяет поддержку API; на десктопе автозапуск
  +`requestFullscreen()`; кнопка ⛶ ↔ 🗗 – синхронизируется через
  `fullscreenChanged`/`fullscreenFailed` события. Без поддержки –
  кнопка скрыта + тост-подсказка про апдейт TG. (c) Дизайн: чек-бокс
  с реальным ✓ внутри, scale-hover; задача – мягкая тень,
  hover-elevation; левый цветной accent-strip по цвету списка
  (`--accent` CSS-переменная); drag-handle на hover становится явным;
  spacing увеличен. 248 тестов остаются зелёными.
- **11.11 ✅ (PR #54):** Архив выполненных + меню команд бота.
  (a) `get_archived_tasks(user_id)` – выполненные (без soft-deleted),
  сортировка по `id DESC` (приближённо порядок завершения, без
  отдельной колонки `completed_at`). API `GET /api/archive` (с
  decorate'ом и steps-counts). Frontend: новая опция «🗂 Архив»
  в `#viewSel`; drag/manual-order в архиве отключён. (b) Bot: в
  `main()` через `post_init` пост-инициализация дёргает
  `bot.set_my_commands` со списком `[/start, /help]` – теперь
  Telegram-автокомплит `/` показывает их подсказки. Обёрнуто в
  try/except, чтобы не валить старт. 248 тестов.
- **11.10 ✅ (PR #53):** Soft-delete задач с undo. БД: колонка
  `tasks.deleted_at` (миграция + CREATE TABLE). `delete_task` /
  `restore_task` (idempotent) / `purge_deleted_tasks(hours=24)`
  (одной транзакцией; подзадачи каскадом по FK). Все SELECT'ы списка
  фильтруют `deleted_at IS NULL`: `get_tasks`, `get_tasks_by_list`,
  `get_myday`, `get_planned`, `get_important_tasks`, `search_tasks`,
  `get_due_reminders`, `get_overdue_tasks`, `get_steps_counts`,
  `get_user_stats`, `_move_task`/`reorder_task`, `bulk_update_tasks`,
  `get_tasks_linked_to_note`, `export_user_data`. Scheduler job
  `purge_deleted` теперь чистит и задачи (отдельный try/except).
  Webapp: `DELETE /api/tasks/{id}` → soft, `POST /api/tasks/{id}/
  restore` → undo (404 на активную/чужую), `_require_own_task` теперь
  отвергает soft-deleted (кроме restore). Фронтенд: кнопка
  «🗑 Удалить» (красная) в панели задачи; после клика – `uiUndoToast`
  с превью описания, «Отменить» возвращает за 8 сек. 245 тестов.
- **11.9 ✅ (PR #52):** Клик-по-чекбоксу в карточках заметок.
  `mdToHtml` теперь объединяет регексп для `- [ ]` / `- [x]` и
  присваивает каждому чек-боксу последовательный `data-cb`. На клик в
  `noteCard`: `toggleNoteCheckboxLine(body, idx)` переключает `- [ ] `
  ↔ `- [x] ` в N-й чек-бокс-строке тела, оптимистично перерисовываем
  `.nbody`, PATCH `/api/notes/{id}` с `_silent: true` (на ошибке
  `loadNotes()`). Клик по чек-боксу не открывает редактор – `stop
  Propagation`. Курсор pointer, лёгкая scale-анимация на hover.
  239 тестов остаются зелёными.
- **11.8 ✅ (PR #51):** Размеры окна – десктоп шире, мобайл компактно.
  (a) `body.is-desktop` / `body.is-mobile` по `tg.platform`; на десктопе
  body центрируется в `max-width: 760px` – на широких мониторах
  список не размазывается. (b) Кнопка `⛶` в шапке (только десктоп) –
  ручной триггер `tg.requestFullscreen()` / `exitFullscreen()`.
  Автозапуск в `_setupWindowMode` остаётся, но клиенты часто
  отказывают без user-gesture – кнопка-страховка. (c) Диагностика
  `console.log` платформы, viewport_height, isExpanded – видно из
  devtools, если жалоба «окно не разворачивается». Frontend-only,
  239 тестов остаются зелёными.
- **11.7 ✅ (PR #50):** Inline-edit задачи + snooze-кнопки в
  уведомлениях. (a) Двойной клик по тексту задачи → `<input>` поверх,
  Enter сохраняет / Esc отменяет / blur сохраняет; `li.editing`
  скрывает панель, чтобы не путаться. (b) Scheduler `_notify`
  прикладывает InlineKeyboardMarkup `[+15м, +1ч, ✓ Готово]` к
  каждому уведомлению; callback-data – короткие токены `snz:<id>:
  <mins>` и `done:<id>`. Bot: `CallbackQueryHandler` с whitelist-
  проверкой и валидацией принадлежности задачи. `snz` → `snooze_
  reminder`, `done` → `complete_task`; в обоих случаях редактируется
  исходное сообщение, чтобы видеть результат («Отложено на N мин: …»
  / «✓ Выполнено: …»). Тесты: snooze callback сдвигает reminder_at,
  done закрывает задачу и пишет «Выполнено», foreign callback
  игнорится, garbage data не ломает обработчик, whitelist отвергает.
  239 тестов.
- **11.6 ✅ (PR #49):** Связь задача ↔ заметка. БД: колонка
  `tasks.note_id INTEGER` (миграция). `set_task_note(task_id,
  note_id|None)` – устанавливает/снимает связь (валидацию ownership
  делает webapp). `get_tasks_linked_to_note(user_id, note_id)` –
  активные задачи, связанные с заметкой, отсортированы как обычные.
  API: PATCH `/api/tasks/{id}` принимает `note_id` (валидирует, что
  заметка своя через `_require_own_note`) и `clear_note: true` для
  отвязки; новый `GET /api/notes/{id}/tasks` отдаёт список связанных
  задач (404 на чужую заметку). Frontend: в панели задачи кнопка
  «📓 Прикрепить заметку» (открывает `uiSelect` по своим заметкам),
  «Отвязать» – если уже привязана; в meta-строке индикатор
  «📓 заметка». В редакторе заметки – лениво подгружаемая строчка
  «🔗 связано с задачами (N): …». 234 теста.
- **11.5 ✅ (PR #48):** Markdown в теле заметок. Hand-rolled
  `mdToHtml(raw)` без зависимостей. Поддержка: `**bold**` /
  `__bold__`, `*italic*` / `_italic_`, `` `inline code` ``,
  `[text](url)` (только http(s)/tg/mailto/relative – иначе текстом),
  авто-ссылки на http(s)/tg-URL, чек-листы `- [ ]` / `- [x]`,
  переносы строк. Безопасность: вся входная строка эскейпится через
  `esc()` ДО парсинга, ссылки кладутся в стэш с маркером U+0001 –
  следующие шаги (bold/italic) не повреждают их содержимое. Frontend-
  only; в редакторе остаётся raw-textarea (нет live preview, минимум
  кода). 230 тестов остаются зелёными.
- **11.4 ✅ (PR #47):** Bulk-actions для задач. БД: `bulk_update_tasks
  (user_id, ids, action, list_id=None)` – фильтрует id по user_id
  (защита от чужих), `_BULK_ACTIONS` = `complete|uncomplete|star|
  unstar|move`. Для `complete` каждый элемент идёт через
  `complete_task` (нужна рекуррентность). Остальные – одним UPDATE
  в транзакции. `move` валидирует, что список свой и активный
  (ValueError). API: `POST /api/tasks/bulk {ids[], action,
  list_id?}` → `{affected}` (422 на битый action или чужой list_id).
  Frontend: long-press 500мс на тексте задачи → режим мульти-выбора
  (тач+мышь, через Pointer Events; haptic feedback на мобильном).
  Топ-бар с действиями ✓ / ★ / ☆ / 📁 / ✕. Drag-handle и стрелки
  скрыты в режиме выбора. `📁` использует `uiSelect` для выбора
  списка. Также убран лишний префикс «Команды бота больше не нужны»
  в fallback-сообщении бота (по запросу пользователя). 230 тестов.
- **11.3b ✅ (PR #46):** Hotfix аутентификации Mini App. Bug-report
  пользователя со скрином: «platform: tdesktop · initData length: 0».
  Корень – `KeyboardButton` в `ReplyKeyboardMarkup` НЕ передаёт
  initData на десктопе (там семантика «send data back», а не auth).
  Замена на `InlineKeyboardButton + InlineKeyboardMarkup` в
  приветствии + `bot.set_chat_menu_button(MenuButtonWebApp)` для
  верхней «Открыть». 222 теста.
- **11.3 ✅ (PR #45):** Single-user whitelist + диагностика 401 +
  smart-fullscreen. (a) Конфиг `ALLOWED_USER_IDS` / `ALLOWED_USERNAMES`
  (CSV); пустые = доступ всем. `is_user_allowed(user_id, username)`
  пускает по любому из двух. (b) `current_user_id` теперь возвращает
  403 на «свой подпис, но не в allowlist»; 401 – на битую подпись.
  `validate_init_data` пишет точечные WARNING'и (нет токена / нет
  hash / нет user / mismatch), чтобы диагностировать причину прямо
  из лога. Новый `GET /api/whoami` (без авторизации) – отдаёт
  `{ok, allowed, allowlist_active}` для curl-диагностики. Bot-side:
  `/start` и `fallback` отказывают «доступ ограничен». Scheduler
  пропускает чужие user_id при активном ID-allowlist'е. (c)
  Frontend: smart-fullscreen: на десктопных платформах (`tdesktop`,
  `macos`, `web*`, `windows`, `linux`) – `tg.expand()` +
  `tg.requestFullscreen()` (API 8.0); на мобиле – НЕ расширяем
  (оставляем «маленькое окно», как просил пользователь). Страница
  401/403 теперь информативная (platform, длина initData, какие
  настройки проверять). `getInitData()` перечитывается на каждый
  запрос. 221 тест.
- **11.2 ✅ (PR #44):** Раздел заметок. БД: новая таблица `notes`
  (`id, user_id, title?, body, pinned, color, created_at, updated_at,
  deleted_at`). Функции `add_note`, `get_notes(include_deleted=)`,
  `get_note`, `update_note(*, title, body, pinned, color,
  clear_title)`, `delete_note`/`restore_note` (soft-delete по
  10.7-паттерну), `purge_deleted_notes(hours=24)`, `search_notes`.
  Pinned-first, потом `updated_at DESC, id DESC`. API: GET/POST
  `/api/notes`, PATCH/DELETE/POST-restore `/api/notes/{id}`, поиск
  через `?search=`. Scheduler-job `purge_deleted` теперь чистит и
  заметки. Export/import (Phase 10.2): добавлен `notes` массив в
  схеме (опциональный – старые бэкапы без `notes` работают).
  `get_user_stats` отдаёт `notes`. Frontend: вкладки «📋 Задачи /
  📓 Заметки», отдельная секция с grid 2×N карточек, поиск,
  редактор-модал (заголовок, тело, 8 цветов пастелью, pin/unpin,
  удаление с undo-тостом). Состояние секции персистится в
  localStorage. 210 тестов, TOTAL 98.93%.

