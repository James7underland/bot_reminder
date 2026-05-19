# Журнал разработки Telegram-бота-напоминалки

Этот документ будет отслеживать все этапы разработки, включая планы и результаты тестирования.

---

## Этап 1: Создание плана проекта

**Дата:** 2026-05-17

**Описание:** Создан первый документ `PROJECT_PLAN.md`, который определяет общий стек технологий, архитектуру и функциональные требования.

**Статус:** Завершено ✅

**Следующие шаги:** 
1.  Создать файл конфигурации.
2.  Установить необходимые зависимости.
3.  Написать первую версию модуля базы данных.

---

## Этап 2: Настройка конфигурации и базы данных

**Дата:** 2026-05-17

**Описание:** Созданы файлы `config.py` и `database.py`. Написана первая версия модуля базы данных с функциями для добавления, получения и обновления задач. Попытка написать unit-тесты с использованием `unittest` и `pytest` не удалась из-за проблем с инициализацией базы данных в тестовом контексте.

**Статус:** Частично завершено (тесты отложены) ⚠️

**Следующие шаги:** 
1.  Временно отложить написание тестов.
2.  Перейти к реализации ядра бота в `bot.py`.

---

## Этап 3: Ревизия плана, безопасность, переход на версионирование

**Дата:** 2026-05-17

**Описание:** Проведена ревизия всех материалов. Установлено: прототип
существует — `config.py`, `database.py`, `bot.py` присутствуют (нет
`scheduler.py`). Тесты не проходят: дефект тестовой БД (`:memory:` +
`scope="session"` при пер-вызовных соединениях SQLite — таблица исчезает до
первого запроса) и контрактное несоответствие (`database.py` возвращает
`completed` как `0/1`, тест ждёт Python `bool`). **Безопасность:** в
`config.py:6` обнаружен захардкоженный токен (тот, что утёк в чат) →
пользователь выполнил `revoke` в @BotFather; `config.py` переписан на чтение
из `.env` (`python-dotenv`), в `bot.py` добавлена проверка наличия токена.
Секрет устранён ДО первого git-коммита — в историю не попадает. Создан
мастер-план `WORK_PLAN.md` (v2): полный паритет с Microsoft To Do,
VPS-деплой, задел под PostgreSQL, без естественного языка для дат,
git-workflow (ветка на этап → merge в `main` при зелёных тестах), CI/CD на
GitHub Actions. Созданы `.gitignore`, `.env.example`, `requirements.txt`,
`requirements-dev.txt`.

**Статус:** Фаза 0 завершена ✅

**Результат Фазы 0:**
- `gh` CLI 2.92.0 установлен; пользователь авторизован (`James7underland`).
- Создан **private**-репозиторий
  `https://github.com/James7underland/bot_reminder`, default branch `main`.
- Первый коммит `8c869e4` (каркас + план + устранение секрета) запушен.
- Токен в git-историю не попал (проверено `git grep` по HEAD).

**Следующие шаги (Фаза 1 — ветка `phase/1-env-ci`):**
1.  Установить зависимости в `.venv` из `requirements-dev.txt`.
2.  `pyproject.toml`: конфиг pytest / coverage / ruff.
3.  `.github/workflows/ci.yml`: джобы setup/lint/test, кэш зависимостей.
4.  Branch protection на `main` (требование зелёного CI).
5.  Затем Фаза 2: `config.py`/`database.py` строго под тесты, с
    исправленной фикстурой БД.

---

## Этап 4: Фазы 1+2 — окружение, CI, зелёный слой данных

**Дата:** 2026-05-17

**Описание:** Фаза 1 и Фаза 2 объединены в один PR (#1, ветка
`phase/1-env-ci`): Фаза 1 добавляет CI, но тесты на старте красные, а
красную Фазу 1 нельзя влить в `main` («main всегда зелёный»); делить —
лишний churn (одобрено пользователем — он предпочитает bundled PR).

Фаза 1: зависимости установлены в `.venv` из `requirements-dev.txt`;
добавлены `pyproject.toml` (pytest/coverage/ruff) и
`.github/workflows/ci.yml` (jobs lint[non-blocking]/test, кэш pip).
Локальный прогон подтвердил дефект §2.2: все 8 тестов падали с
`sqlite3.OperationalError: no such table: tasks`.

Фаза 2: `tests/conftest.py` переписан — function-scope фикстура с
временной файловой БД (`tmp_path`) вместо `:memory:`+session (устранён
§2.2). В `database.py.get_tasks` добавлено приведение `completed` к Python
`bool` (контракт §2.3). Результат: **8/8 тестов зелёные**, покрытие
`database.py` **100%**, `config.py` 80% (непокрыт только
`except ImportError` опционального dotenv — не бизнес-логика).

**Branch protection:** технически недоступен — и classic protection, и
rulesets требуют GitHub Pro для private-репо (HTTP 403). Решение
пользователя: оставляем private, правило «merge только зелёного»
соблюдается **дисциплиной** (красные PR не мержатся). CI виден на каждом
PR.

**Статус:** Фаза 1 ✅. Фаза 2 — слой данных зелёный ✅; merge PR #1 в
`main` после зелёного CI на GitHub.

**Следующие шаги:**
1.  Закоммитить Фазу 2 на `phase/1-env-ci`, дождаться зелёного CI.
2.  Merge PR #1 в `main`. Включить `fail_under=90` в `pyproject.toml`.
3.  Фаза 3 (ветка `phase/3-bot-core`): тесты на `parse_add_command` и
    хендлеры (Telegram замокан), харденинг `bot.py`.

---

## Этап 5: Фаза 3 — ядро бота, тесты, харденинг

**Дата:** 2026-05-17

**Описание:** Ветка `phase/3-bot-core`. `parse_add_command` переписан с
хакерского черновика на строгую реализацию: только форматы
`YYYY-MM-DD HH:MM` и `DD.MM.YYYY HH:MM` (решение №4 — без естественного
языка), невалидный дата-подобный токен датой не считается, результат
нормализуется к `YYYY-MM-DD HH:MM:SS`. Добавлены `tests/test_parse.py`
(параметризованная таблица форматов/мусора/без даты) и
`tests/test_handlers.py` (все хендлеры с замоканным Telegram через
`AsyncMock`, без сети). `main()` и `__main__`-guard помечены
`# pragma: no cover` (сетевой polling вне unit-тестов).

Харденинг и качество: `fail_under=90` включён в `pyproject.toml`; весь
репозиторий приведён к ruff-чистоте (автофикс + ручные правки E402/E501/
F841, в т.ч. в старом `test_database.py`); lint-джоба в CI стала
блокирующей (убран `continue-on-error`). Логирование переведено на
ленивый `%`-стиль.

**Результат:** 32 теста зелёные; покрытие `bot.py` 100%,
`database.py` 100%, `config.py` 80% (только `except ImportError`
опционального dotenv), TOTAL 98.6%; ruff — `All checks passed`.

**Статус:** Фаза 3 — зелёная локально ✅; PR #2 → merge в `main` после
зелёного CI.

**Следующие шаги:**
1.  Merge PR #2 в `main`.
2.  Фаза 4 (ветка `phase/4-scheduler`): `scheduler.py` на APScheduler —
    отправка напоминаний по `due_date`, анти-дубль (миграция
    `reminder_sent`), тесты с инъекцией времени.
3.  Пользователь: создать локальный `.env` с новым токеном для ручного
    прогона бота.

---

## Этап 6: Фаза 4 — напоминания (APScheduler)

**Дата:** 2026-05-17

**Описание:** Ветка `phase/4-scheduler`. Схема: добавлена колонка
`reminder_sent` в `CREATE TABLE` + идемпотентная миграция `ALTER TABLE`
для БД, созданных до Фазы 4 (покрыта тестом на legacy-таблице).
`set_reminder` теперь сбрасывает `reminder_sent=0` (перенос срока →
напоминание сработает снова). Добавлены `database.get_due_tasks(now)`
(выборка: `completed=0 AND reminder_sent=0 AND due_date<=now`,
лексикографическое сравнение строк формата `YYYY-MM-DD HH:MM:SS`
эквивалентно временно́му) и `mark_reminder_sent`.

`scheduler.py`: `check_and_send_reminders(bot, now=None)` — чистая
тестируемая логика (БД + отправка через переданный `bot`), анти-дубль
через `mark_reminder_sent` после успешной отправки; при ошибке отправки
задача НЕ помечается (повтор на следующем тике — приоритет доставке).
`setup_scheduler` (AsyncIOScheduler, интервал `SCHEDULER_CHECK_INTERVAL`)
помечен `# pragma: no cover` (интеграция). Подключён в `bot.main()`.
`scheduler` добавлен в `[tool.coverage.run] source`.

**Результат:** 39 тестов зелёные; `bot.py`/`database.py`/`scheduler.py`
100%, `config.py` 80%, TOTAL 98.95%; ruff — `All checks passed`.

**Статус:** Фаза 4 — зелёная локально ✅; PR #3 → merge после зелёного CI.

**Следующие шаги:**
1.  Merge PR #3 в `main`.
2.  Фаза 5 — паритет с Microsoft To Do (под-фазы 5.1…5.8), начиная с
    5.1 (редактирование/перенос/uncomplete).
3.  Пользователь: `.env` с новым токеном для ручной проверки
    «уведомление приходит один раз».

---

## Этап 7: Фаза 5.1 — редактирование / перенос / отмена выполнения

**Дата:** 2026-05-17

**Описание:** Ветка `phase/5.1-edit-reschedule`. Команды `/edit <id>
<описание>`, `/reschedule <id> <дата>`, `/undone <id>`. Слой БД:
`update_task_description`, `mark_task_undone` (обе возвращают False для
несуществующего id). Парсер дат отрефакторен: общая функция `_match_due`,
из неё используют и `parse_add_command` (поведение неизменно — гарантия
существующими тестами), и новая `parse_datetime` (для `/reschedule`).
`/reschedule` использует уже существующий `set_reminder` (он сбрасывает
`reminder_sent` — перенос срока заставит напоминание сработать снова).
Миграции схемы не требовалось (используются существующие колонки).
Хелп обновлён. Хендлеры зарегистрированы в `bot.main()`.

**Результат:** 60 тестов зелёные (+21 в `tests/test_edit.py`: БД,
parse_datetime, все ветки трёх хендлеров); `bot.py`/`database.py`/
`scheduler.py` 100%, `config.py` 80%, TOTAL 99.25%; ruff чист.

**Статус:** Фаза 5.1 — зелёная локально ✅; PR #4 → merge после CI.

**Следующие шаги:**
1.  Merge PR #4 в `main`.
2.  Фаза 5.2 — списки/категории (таблица `lists`, миграция, привязка
    задач, команды управления списками).

---

## Этап 8: Фаза 5.2 — списки/категории

**Дата:** 2026-05-17

**Описание:** Ветка `phase/5.2-lists`. Схема: новая таблица `lists`
(`id`, `user_id`, `name`, `created_at`) + колонка `tasks.list_id`
(добавлена и в `CREATE TABLE`, и идемпотентной миграцией `ALTER` для
legacy-БД — покрыто тестом). Слой БД: `create_list`, `get_lists`
(изоляция по user), `rename_list`, `delete_list` (задачи списка
переносятся в «без списка», `list_id=NULL`), `assign_task_to_list`
(None = снять со списка), `get_tasks_by_list` (фильтр по списку или
`list_id IS NULL`, исключает выполненные по умолчанию).

Команды: `/lists`, `/newlist <имя>`, `/renamelist <id> <имя>`,
`/dellist <id>`, `/movetask <task_id> <list_id|0>`. `/list` расширен
необязательным аргументом `<id|0>` (0 — задачи без списка); поведение
`/list` без аргументов не изменилось (регрессия зелёная). `/movetask`
валидирует, что целевой список принадлежит пользователю.

**Результат:** 81 тест зелёный (+21 в `tests/test_lists.py`: БД,
все ветки 5 хендлеров, фильтр `/list`, миграция legacy);
`bot.py`/`database.py`/`scheduler.py` 100%, `config.py` 80%,
TOTAL 99.52%; ruff чист.

**Статус:** Фаза 5.2 — зелёная локально ✅; PR #5 → merge после CI.

**Следующие шаги:**
1.  Merge PR #5 в `main`.
2.  Фаза 5.3 — повторяющиеся задачи (правило повтора, генерация
    следующего экземпляра при выполнении; миграция `recurrence`).

---

## Этап 9: Фаза 5.3 — повторяющиеся задачи

**Дата:** 2026-05-17

**Описание:** Ветка `phase/5.3-recurring`. Колонка `recurrence`
(`CREATE TABLE` + идемпотентная миграция). `next_occurrence(due,
recurrence)` — чистая логика для daily/weekly/monthly/yearly с обрезкой
дня до конца месяца (`31.01 → 28/29.02`) и високоса (`29.02.2024 →
28.02.2025`), неизвестное значение → `ValueError`. `set_recurrence`
(валидирует значение, None — снять). `complete_task` заменяет в
обработчике `/done` прямой `mark_task_done`: выполняет задачу и, если она
повторяющаяся и имеет `due_date`, создаёт следующий экземпляр (тот же
`user_id`/описание/`list_id`/`recurrence`, новый `due_date`). Команда
`/repeat <id> <daily|weekly|monthly|yearly|off>`. `/done` сообщает о
следующем повторе; `/list` показывает «(повтор: …)».

Регрессия: 2 теста `/done` в `test_handlers.py` обновлены под новый
коллаборатор (`complete_task` вместо `mark_task_done`) — обоснованная
правка рефакторинга, не сокрытие падения. `mark_task_done` сохранён в
`database.py` (контракт `test_database.py` не тронут).

**Результат:** 103 теста зелёные (+22 в `tests/test_recurring.py`);
`bot.py`/`database.py`/`scheduler.py` 100%, `config.py` 80%,
TOTAL 99.60%; ruff чист.

**Статус:** Фаза 5.3 — зелёная локально ✅; PR #6 → merge после CI.

**Следующие шаги:**
1.  Merge PR #6 в `main`.
2.  Фаза 5.4 — важные задачи (флаг `important`) + сортировки в `/list`.

---

## Этап 10: Фаза 5.4 — важные задачи + сортировки

**Дата:** 2026-05-17

**Описание:** Ветка `phase/5.4-important`. Колонка `important`
(`CREATE TABLE` + идемпотентная миграция, тест legacy). `set_important`.
`get_tasks` получил необязательный `sort` (белый список:
`important`/`due`/`alpha`/`created`; `None`/неизвестное → `created_at` —
SQL и поведение для существующих вызовов неизменны, контракт
`test_database.py` сохранён; ORDER BY формируется только из whitelist,
пользовательский ввод в SQL не попадает). В `get_tasks` добавлено
приведение `important` к bool. Команды `/important`, `/unimportant`
(общий хелпер `_set_important`), `/list <important|due|alpha|created>`;
в выводе `/list` важные помечаются «[важно] ».

Регрессия: сообщение об ошибке аргумента `/list` сохранило подстроку
«ID списка» — тест `test_lists.test_list_filter_bad_id` остаётся зелёным.

**Результат:** 117 тестов зелёные (+14 в `tests/test_important.py`);
`bot.py`/`database.py`/`scheduler.py` 100%, `config.py` 80%,
TOTAL 99.63%; ruff чист.

**Статус:** Фаза 5.4 — зелёная локально ✅; PR #7 → merge после CI.

**Следующие шаги:**
1.  Merge PR #7 в `main`.
2.  Фаза 5.5 — подзадачи (таблица `steps`) и заметки (поле `notes`).

---

## Этап 11: Фаза 5.5 — подзадачи и заметки

**Дата:** 2026-05-17

**Описание:** Ветка `phase/5.5-steps-notes`. Таблица `steps`
(`task_id` FK → `tasks(id)` `ON DELETE CASCADE`, `completed`,
`created_at`) + колонка `tasks.notes` (`CREATE` + идемпотентная
миграция, тест legacy). Слой БД: `add_step` (None, если родительской
задачи нет — без опоры на исключение FK), `get_steps`
(`completed`→bool), `mark_step_done(done=)`, `delete_step`, `get_task`
(одиночная задача, `completed`/`important`→bool), `set_note`
(None — очистить). Команды: `/addstep`, `/steps` (показывает заметку +
подзадачи `[x]/[ ]`), `/stepdone`, `/stepundone` (общий хелпер
`_set_step`), `/delstep`, `/note <id> [текст]` (без текста — показать),
`/delnote`.

**Результат:** 133 теста зелёные (+16 в `tests/test_steps_notes.py`:
БД, все ветки хендлеров, миграция legacy); `bot.py`/`database.py`/
`scheduler.py` 100%, `config.py` 80%, TOTAL 99.72%; ruff чист.

**Статус:** Фаза 5.5 — зелёная локально ✅; PR #8 → merge после CI.

**Следующие шаги:**
1.  Merge PR #8 в `main`.
2.  Фаза 5.6 — «Мой день» (`/myday`: задачи с дедлайном сегодня +
    отмеченные «в мой день»).

---

## Этап 12: Фаза 5.6 — «Мой день»

**Дата:** 2026-05-17

**Описание:** Ветка `phase/5.6-myday`. Колонка `tasks.myday_date`
(`CREATE` + идемпотентная миграция, тест legacy). Слой БД:
`add_to_myday(task_id, day)`, `remove_from_myday`, `get_myday(user, day)`
— возвращает активные задачи, у которых либо дата дедлайна
(`substr(due_date,1,10)`) равна `day`, либо `myday_date == day`;
сортировка «сначала с дедлайном» (`due_date IS NULL, due_date,
created_at`). Команда `/myday` (список на сегодня),
`/myday add <id>`, `/myday remove|rm <id>`; дата «сегодня» берётся из
`datetime.now()` в обработчике, логика дат тестируется на уровне БД с
явным `day` (детерминированно).

**Результат:** 143 теста зелёные (+13 в `tests/test_myday.py`);
`bot.py`/`database.py`/`scheduler.py` 100%, `config.py` 80%,
TOTAL 99.75%; ruff чист.

**Статус:** Фаза 5.6 — зелёная локально ✅; PR #9 → merge после CI.

**Следующие шаги:**
1.  Merge PR #9 в `main`.
2.  Фаза 5.7 — поиск (`/search <текст>`) + гибкие напоминания
    (за N минут до срока).

---

## Этап 13: Фаза 5.7 — поиск + гибкие напоминания

**Дата:** 2026-05-17

**Описание:** Ветка `phase/5.7-search-reminders`. `search_tasks(user,
query)` — поиск по описанию и заметке среди активных задач,
регистронезависимо в т.ч. для кириллицы (фильтрация на стороне Python
через `str.lower()`, т.к. SQLite `LIKE`/`lower()` не покрывают Unicode
без ICU). Колонка `remind_before` (минуты; `CREATE` + идемпотентная
миграция). `set_remind_before` (валидирует ≥0). `get_due_tasks`
переписан: время срабатывания = `datetime(due_date, '-' ||
COALESCE(remind_before,0) || ' minutes')` — при NULL поведение
идентично прежнему (регрессия scheduler-тестов зелёная). Команды
`/search <текст>`, `/remindbefore <task_id> <минут|off>`.

Объём: «несколько напоминаний на одну задачу» в 5.7 не реализуется
(потребовало бы отдельной таблицы) — отмечено как возможный будущий
полиш; реализована настраиваемая упреждающая величина (за N минут).

**Результат:** 155 тестов зелёные (+12 в
`tests/test_search_reminders.py`); `bot.py`/`database.py`/`scheduler.py`
100%, `config.py` 80%, TOTAL 99.77%; ruff чист.

**Статус:** Фаза 5.7 — зелёная локально ✅; PR #10 → merge после CI.

**Следующие шаги:**
1.  Merge PR #10 в `main`.
2.  Фаза 5.8 — часовые пояса пользователя (хранить TZ, считать
    напоминания в TZ пользователя).

---

## Этап 14: Фаза 5.8 — часовые пояса (завершение Фазы 5)

**Дата:** 2026-05-17

**Описание:** Ветка `phase/5.8-timezones`. Таблица `user_settings`
(`user_id` PK, `timezone`). Новый модуль `tzutil.py` (stdlib
`zoneinfo`): `valid_timezone`, `to_utc`, `to_local`. Слой БД:
`get_timezone` (дефолт `UTC`), `set_timezone` (валидирует зону, upsert).
Канон хранения `due_date` — **UTC**: `/add` и `/reschedule`
конвертируют введённое пользователем время из его пояса в UTC перед
сохранением; `/list` показывает обратно в локальном поясе; `scheduler`
сравнивает в UTC (дефолтное `now` → `datetime.now(UTC)`). Команда
`/timezone [IANA]`. Ключевое свойство: дефолтный пояс `UTC` делает
`to_utc`/`to_local` тождественными, поэтому контракт `add_task`/
`get_tasks` и все 155 прежних тестов остаются зелёными без правок.
`tzutil` добавлен в `[tool.coverage.run] source`. ruff-автофикс
обновил `datetime.timezone.utc` → `datetime.UTC` (UP, Python 3.11).

**Результат:** 171 тест зелёный (+16 в `tests/test_timezones.py`:
tzutil, get/set_timezone, `/timezone`, интеграция /add→UTC,
/list→локально, дефолтный пользователь без изменений);
`bot.py`/`database.py`/`scheduler.py`/`tzutil.py` 100%, `config.py` 80%,
TOTAL 99.78%; ruff чист.

**Итог Фазы 5:** под-фазы 5.1–5.8 завершены и в `main` — достигнут
функциональный паритет с Microsoft To Do.

**Статус:** Фаза 5.8 — зелёная локально ✅; PR #11 → merge после CI.

**Следующие шаги:**
1.  Merge PR #11 в `main`.
2.  Фаза 6 — миграция на PostgreSQL, харденинг, деплой на VPS, CD
    (GitHub Actions → SSH), `systemd`, бэкап БД.

---

## Этап 15: Фаза 6a — автономная деплой-инфраструктура + харденинг

**Дата:** 2026-05-17

**Описание:** Ветка `phase/6a-deploy-hardening`. По решению (пользователь:
«делай, что считаешь нужным») сделана автономная часть Фазы 6 — без VPS,
без PostgreSQL. Аргументация порядка (деплой на SQLite раньше Postgres)
зафиксирована в ответе ассистента и `DEPLOYMENT.md` §5.

- **CI:** bump `actions/checkout@v4→v5`, `actions/setup-python@v5→v6`
  (Node 24; снят deprecation-warning, дедлайн 2026-06-02). Это закрывает
  ранее заведённую задачу-чип.
- **`.github/workflows/deploy.yml`:** SSH-деплой при push в `main`;
  gate-шаг проверяет наличие `DEPLOY_HOST`/`DEPLOY_SSH_KEY` и при их
  отсутствии завершает джобу success со «skip» — `main` не краснеет до
  настройки секретов.
- **`deploy/bot_reminder.service`** (systemd, `Restart=always`,
  `EnvironmentFile=.env`), **`deploy/backup.sh`** (`sqlite3 .backup` +
  ротация 14), **`DEPLOYMENT.md`** (пошаговый runbook: подготовка VPS,
  systemd, cron-бэкап, GitHub Secrets, заметка про PostgreSQL).
- **Харденинг:** глобальный `error_handler` (логирует необработанные
  исключения через `exc_info`), `application.add_error_handler(...)`.

**Результат:** 172 теста зелёные (+1 `tests/test_hardening.py`);
`bot.py`/`database.py`/`scheduler.py`/`tzutil.py` 100%, `config.py` 80%,
TOTAL 99.78%; ruff чист.

**Статус:** Фаза 6a — зелёная локально ✅; PR #12 → merge после CI.

**Осталось (Фаза 6b, требует пользователя):**
1.  VPS + GitHub Secrets + `.env` с новым токеном → CD по runbook.
2.  PostgreSQL — отдельной фазой по реальной потребности.

---

## Этап 16: Прод-баг — scheduler.start() без event loop (Фаза 6b)

**Дата:** 2026-05-19

**Описание:** При первом запуске на VPS (systemd) бот падал с
`RuntimeError: no running event loop` в `AsyncIOScheduler.start()`.
Причина: `setup_scheduler()` вызывал `scheduler.start()` синхронно в
`main()` — **до** старта event loop в `run_polling()`. Юнит-тесты не
ловили: `setup_scheduler` был помечен `# pragma: no cover` как
«интеграция» — классический случай, когда непокрытый код прячет баг.

**Исправление:** `scheduler.start()` перенесён в `application.post_init`
(PTB вызывает его внутри уже запущенного loop), остановка — в
`application.post_shutdown` (`scheduler.shutdown(wait=False)` при
`running`, graceful). `# pragma: no cover` снят; `setup_scheduler`
покрыт тестами (старт НЕ синхронный — регрессия на сам баг; старт/стоп
через post_init/post_shutdown).

**Результат:** 174 теста зелёные (+2); `scheduler.py` 100% (был с
pragma), TOTAL 99.79%; ruff чист.

**Статус:** PR #13 → merge после CI. Затем пользователь на сервере:
`git pull && pip install -r requirements.txt && systemctl restart
bot_reminder` (в дальнейшем — автоматически через CD).

---

## Этап 17: Харденинг логирования — токен не должен попадать в логи

**Дата:** 2026-05-19

**Описание:** На проде обнаружено: `httpx` на уровне INFO логирует
полный URL Telegram API, включающий токен бота, — он оседает в journald
и утёк при пересылке логов. (Пользователь перевыпускает токен через
BotFather.) Добавлена `quiet_third_party_loggers()` — поднимает уровень
`httpx`/`httpcore`/`apscheduler`/`telegram` до WARNING; вызывается при
импорте `bot`. Токен в логи больше не попадает.

**Результат:** 175 тестов зелёные (+1 `test_hardening.py`); `bot.py`
100%, TOTAL 99.79%; ruff чист.

**Статус:** PR #14 → merge после CI; затем на сервере `git pull` +
restart (или авто-деплой, когда настроен).

---

## Этап 18: Фикс deploy.yml под root (до настройки CD)

**Дата:** 2026-05-19

**Описание:** Сервер развёрнут под `root`. В `deploy.yml` рестарт был
`sudo systemctl restart` — на минимальном root-образе `sudo` может
отсутствовать, первый авто-деплой упал бы. Заменено на
`sudo -n systemctl ... 2>/dev/null || systemctl ...` — работает и под
root (plain), и под non-root с NOPASSWD-sudo. Поймано до настройки
секретов (trust-but-verify собственного workflow).

**Статус:** PR #15 → merge после CI. CD безопасно no-op до секретов.

---

## Этап 19: Первый авто-деплой упал — SSH-ключ через base64

**Дата:** 2026-05-19

**Описание:** После настройки секретов первый реальный запуск `Deploy`
(merge PR #15, run 26066605359) упал: `Load key id_deploy: error in
libcrypto` → `Permission denied (publickey)`. Причина: многострочный
OpenSSH-ключ, переданный через секрет и записанный `printf '%s\n'`,
повреждается по переносам строк (классическая проблема CD+SSH).
Решение: `DEPLOY_SSH_KEY` хранить в **base64 одной строкой**, в
`deploy.yml` декодировать `base64 -d`. Обновлён `DEPLOYMENT.md` (как
получить значение: `base64 -w0 ~/.ssh/cd_key`).

**Действие пользователя:** заменить значение секрета `DEPLOY_SSH_KEY` на
вывод `base64 -w0 ~/.ssh/cd_key`.

**Статус:** PR #16 → merge → его merge повторно запустит `Deploy` (уже с
base64-декодом и обновлённым секретом). Бот-код не затронут.

---

## Этап 20: Фаза 7.1 — модель «срок» vs «напоминание»

**Дата:** 2026-05-19

**Контекст:** Запрошен крупный апгрейд — Telegram Mini App + разделение
понятий «срок» (deadline, просрочка+красный) и «напоминание»
(reminder_at). Решения: HTTPS = Cloudflare Tunnel; порядок = бэкенд
раньше UI; срок = дата+время. Фаза 7 (бэкенд-редизайн) разбита на
7.1/7.2/7.3; Mini App = Фаза 8.

**7.1 (ветка `phase/7.1-deadline-reminder-model`):** добавлены колонки
`deadline`, `reminder_at`, `overdue_notified` (`CREATE` + идемпотентная
миграция; для legacy-строк `due_date` копируется в `reminder_at` —
текущее поведение напоминаний сохранено, тест миграции). Функции:
`set_deadline` (сбрасывает `overdue_notified`), `set_reminder_at`
(сбрасывает `reminder_sent`), `get_due_reminders` (reminder_at<=now,
active, не отправлено), `get_overdue_tasks` (deadline<now строго,
active, не уведомляли), `mark_overdue_notified`. Старые
`due_date`/`get_due_tasks`/`set_reminder` не тронуты (175 прежних
тестов зелёные) — переключение планировщика в 7.2.

**Результат:** 182 теста зелёные (+7 `tests/test_deadline_model.py`);
`bot.py`/`database.py`/`scheduler.py`/`tzutil.py` 100%, `config.py` 80%,
TOTAL 99.80%; ruff чист.

**Статус:** PR #17 → merge → авто-деплой. Далее 7.2 (планировщик).

---

## Этап 21: Фаза 7.2 — планировщик: напоминания + просрочка

**Дата:** 2026-05-19

**Описание:** Ветка `phase/7.2-scheduler-deadline`. `check_and_send_
reminders` переведён со старой `get_due_tasks` (по `due_date`) на новую
модель: общий хелпер `_notify(bot, tasks, prefix, mark)` шлёт
`prefix: описание` и помечает успешные (анти-дубль; ошибка отправки —
не помечаем, повтор на след. тике). Два прохода за тик:
напоминания — `get_due_reminders` → «Напоминаю» → `mark_reminder_sent`;
просрочка — `get_overdue_tasks` → «Просрочено» → `mark_overdue_notified`.
Задача с прошедшими и `reminder_at`, и `deadline` получит оба
уведомления.

Легаси `get_due_tasks`/`due_date`/`set_reminder` не удалялись (их
прямые тесты — `test_scheduler` get_due_tasks_*, `test_search_reminders`
— остаются зелёными); чистка/перевод команд — в 7.3. Тесты
`test_check_and_send_*` переписаны под `set_reminder_at`/`set_deadline`,
добавлены кейсы просрочки и «напоминание+просрочка вместе».

**Результат:** 184 теста зелёные; `bot.py`/`database.py`/`scheduler.py`/
`tzutil.py` 100%, `config.py` 80%, TOTAL 99.80%; ruff чист.

**Статус:** PR #18 → merge → авто-деплой. Далее 7.3 (команды/хелп).

---

## Этап 22: Фаза 7.3 — команды под новую модель (Фаза 7 завершена)

**Дата:** 2026-05-19

**Описание:** Ветка `phase/7.3-commands-new-model`. Slash-команды
приведены к модели срок/напоминание (slash — фолбэк, основной UI будет
Mini App):
- Новые `/deadline <id> <when|off>` и `/remind <id> <when|off>` через
  общий хелпер `_set_when` (tz пользователя → UTC, `off/нет/-` —
  сброс).
- `/add <desc> <when>` теперь дополнительно ставит `reminder_at`
  (раньше писал только legacy `due_date`, который новый планировщик не
  читает — напоминания из `/add` снова работают).
- `/reschedule` переключён с `set_reminder` на `set_reminder_at`.
- Команда `/remindbefore` удалена: её модель (за N минут до срока) в
  новой схеме не существует; это удаление устаревшей фичи, а не
  «починка тестов удалением». Хелп обновлён.
- Легаси DB-функции (`set_reminder`/`set_remind_before`/`get_due_tasks`/
  `due_date`/`remind_before`) пока оставлены (их прямые DB-тесты
  зелёные); полная зачистка — отдельной уборочной фазой при желании.

Тесты: reschedule-тесты перенацелены на `set_reminder_at`; удалены
тесты обработчика `/remindbefore`; добавлен `tests/test_deadline_cmd.py`
(валидация, успех с tz→UTC, off, не найдено для /deadline и /remind).

**Результат:** 191 тест зелёный; `bot.py`/`database.py`/`scheduler.py`/
`tzutil.py` 100%, `config.py` 80%, TOTAL 99.80%; ruff чист.
**Фаза 7 (бэкенд-редизайн) полностью завершена.**

**Статус:** PR #19 → merge → авто-деплой. Далее Фаза 8 — Telegram
Mini App (FastAPI + initData-авторизация + фронтенд + Cloudflare
Tunnel).

---

## Этап 23: Фаза 8.1 — HTTP API Mini App (FastAPI + initData)

**Дата:** 2026-05-19

**Описание:** Ветка `phase/8.1-webapp-api`. Добавлены зависимости
`fastapi`/`uvicorn` (requirements.txt). Локально `pip` шёл через
SOCKS-прокси пользователя (VPN) и падал без PySocks — обойдено
`NO_PROXY=*` (CI/сервер ставят как обычно).

`webapp.py`: `validate_init_data(init_data, token)` — чистая проверка
подписи Telegram WebApp (secret=HMAC("WebAppData",token);
hash=HMAC(secret,data_check_string); `compare_digest`); возвращает
пользователя или None. Зависимость `current_user_id` (заголовок
`X-Init-Data` → 401 при невалидном). REST: `GET/POST /api/tasks`,
`/complete`, `/uncomplete`, `PATCH /api/tasks/{id}` (описание/важность/
срок/напоминание, `clear_*`), `GET/POST /api/lists`, `/healthz`.
Вычисляемый флаг `overdue` (срок прошёл, не выполнено). Проверка
владения (`_require_own_task` → 404 на чужую задачу). Локальное
время → UTC через `to_utc`+часовой пояс пользователя. Старт через
`lifespan` (не deprecated `on_event`). `webapp` добавлен в coverage.

**Результат:** 212 тестов зелёные (+21 `tests/test_webapp.py`:
подпись/подделка/без user/невалидный JSON, авторизация, CRUD, overdue,
владение, списки, фильтр); `webapp.py` 99% (1 защитная ветка),
остальные модули 100%, TOTAL 99.74%; ruff чист.

**Статус:** PR #20 → merge → авто-деплой (сервер доустановит fastapi).
Бот по-прежнему работает; webapp пока не запускается на сервере — это
8.3. Далее 8.2 (фронтенд).

---

## Этап 24: Фаза 8.2 — фронтенд Mini App

**Дата:** 2026-05-19

**Описание:** Ветка `phase/8.2-miniapp-frontend`. `static/index.html` —
одностраничное приложение: подключает `telegram-web-app.js`, берёт
`Telegram.WebApp.initData`, шлёт его в заголовке `X-Init-Data` к API.
Тема — из `tg-theme-*` (нативный вид Telegram). Функции: список
активных/выполненных (тумблер), добавление, чекбокс
complete/uncomplete, звезда important, разворачиваемая панель задачи
(описание, `datetime-local` срок и напоминание, «убрать срок/напом.»),
**красная подсветка просроченных**, выбор/создание списков, фильтр по
списку. Вне Telegram (нет initData → 401) показывает подсказку.

`webapp.py`: смонтирован `StaticFiles(directory="static", html=True)`
по `"/"` — **после** всех API-маршрутов, поэтому `/api/*` и `/healthz`
имеют приоритет (подтверждено тестом). Бот/сервер не затронуты (systemd
по-прежнему запускает только `bot.py`; запуск webapp — 8.3).

**Результат:** 214 тестов зелёные (+2: статика отдаётся, API в
приоритете над mount); `webapp.py` 99% (1 защитная ветка), прочие 100%,
TOTAL 99.74%; ruff чист.

**Статус:** PR #21 → merge → авто-деплой. Далее 8.3 — Cloudflare
Tunnel + регистрация Mini App в @BotFather + запуск webapp на сервере
(пошагово с пользователем).

---

## Этап 25: Фаза 8.3a — инфраструктура webapp (автономно)

**Дата:** 2026-05-19

**Описание:** Ветка `phase/8.3-webapp-deploy`. Автономная часть 8.3
(без действий на сервере):
- `deploy/bot_webapp.service` — systemd-юнит, `uvicorn webapp:app`
  на `127.0.0.1:8080` (наружу — только через туннель), `Restart=always`.
- `deploy/cloudflared.service` — шаблон постоянного именованного
  туннеля (`TUNNEL_TOKEN` из `/etc/cloudflared.env`).
- `deploy.yml`: после `git pull` дополнительно рестартит `bot_webapp`
  (best-effort: `|| true` — пока юнит не создан, деплой не краснеет).
- `DEPLOYMENT.md` §6 — пошаговый runbook: сервис webapp, установка
  cloudflared (quick vs стабильный именованный), регистрация Mini App
  в @BotFather.

Python-код не менялся → 214 тестов зелёные, ruff чист.

**Статус:** PR #22 → merge → авто-деплой (на сервере webapp ещё не
запущен — это 8.3b с пользователем).

**Осталось (8.3b, требует пользователя):** на VPS поднять `bot_webapp`
и `cloudflared`, получить HTTPS-URL, привязать Mini App в @BotFather.

---

## Этап 26: Фаза 8.3c — Caddy вместо Cloudflare-туннеля

**Дата:** 2026-05-19

**Описание:** Ветка `phase/8.3c-caddy`. Уточнено: у пользователя есть
поддомен `ernstgku.beget.tech` и Beget позволяет ставить A-запись на
IP VPS. Cloudflare named tunnel с этим поддоменом невозможен (зона
`beget.tech` не в аккаунте пользователя). Решение — **Caddy прямо на
VPS**: стабильный `https://ernstgku.beget.tech`, авто-сертификат
Let's Encrypt (HTTP-01), reverse_proxy → `127.0.0.1:8080` (uvicorn
webapp). Проще и стабильнее туннеля, без сторонней зависимости.

Добавлены: `deploy/Caddyfile` (домен + reverse_proxy), `DEPLOYMENT.md`
§6.2 переписан под Caddy (установка из офиц. репозитория, копия
Caddyfile, порты 80/443, первая выдача сертификата); cloudflared
оставлен как альтернатива. Python не менялся → 214 тестов зелёные,
ruff чист.

**Статус:** PR #23 → merge → авто-деплой (Caddyfile появится в
`~/bot_reminder/deploy/` на сервере).

**Осталось (8.3b, пользователь):** A-запись `ernstgku.beget.tech`→IP,
открыть 80/443, поднять `bot_webapp`, установить Caddy + скопировать
Caddyfile, зарегистрировать Mini App в @BotFather.

---

## Этап 27: 8.3b — туннель (Caddy отпал, VPN на :443) + Фаза 8.4

**Дата:** 2026-05-19

**8.3b факт:** на VPS :443 занят контейнером `amnezia-xray` (VPN
пользователя) — Caddy с прямым 443 невозможен, не ломая VPN.
Перешли на `cloudflared` (исходящее соединение, конфликта нет). Быстрый
туннель поднят, Mini App открылся в Telegram (Menu Button →
`*.trycloudflare.com`). Дан `cloudflared-quick.service` для
персистентности (URL быстрого туннеля меняется при рестарте;
стабильный — путь B с доменом в Cloudflare, по желанию). `bot_webapp`
и `cloudflared` работают; авто-деплой `cloudflared` не рестартит → URL
не меняется при выкатке кода.

**Фаза 8.4 (ветка `phase/8.4-recur-myday`):** пользователь подтвердил —
нужен полный паритет Mini App. API: PATCH принимает `recurrence`
(валидация по `RECURRENCES`, 422 на мусор) и `clear_recurrence`;
`GET /api/myday` и `POST /api/tasks/{id}/myday` (toggle), `_today_local`
считает «сегодня» в tz пользователя. Фронтенд: селектор повтора в
панели задачи, тумблер «🗓 Мой день» (грузит `/api/myday`), кнопка
«в/из Мой день», повтор и «в Мой день» в мете.

**Результат:** 217 тестов зелёные (+5 в `test_webapp.py`); `webapp.py`
99% (1 защитная ветка), прочие 100%, TOTAL 99.74%; ruff чист.

**Статус:** PR #24 → merge → авто-деплой (uvicorn перезапустится,
интерфейс обновится; туннель/URL не трогаются). Далее 8.5
(подзадачи+заметки) → 8.6 (поиск+сортировки) → 8.7 (списки+tz).

---

## Этап 28: Фаза 8.5 — подзадачи + заметки в Mini App

**Дата:** 2026-05-19

**Описание:** Ветка `phase/8.5-steps-notes-ui`. API: PATCH принимает
`notes`/`clear_notes` (→ `set_note`). Подзадачи под задачей (ownership
через `_require_own_task`, шаг проверяется в `get_steps` —
`_require_step`): `GET /api/tasks/{id}/steps`,
`POST /api/tasks/{id}/steps` (422 на пустое),
`POST .../steps/{sid}/toggle`, `DELETE .../steps/{sid}`. Фронтенд:
textarea «Заметка» (сохраняется кнопкой; пусто → `clear_notes`),
блок подзадач (ленивая загрузка при открытии панели, чекбокс-тоггл,
✕-удаление, поле «+ шаг»).

**Результат:** 220 тестов зелёные (+4 `test_webapp.py`); `webapp.py`
99% (1 защитная ветка), прочие 100%, TOTAL 99.75%; ruff чист.

**Статус:** PR #25 → merge → авто-деплой. Далее 8.6 (поиск+сортировки).

---

## Этап 29: Фаза 8.6 — поиск + сортировки в Mini App

**Дата:** 2026-05-19

**Описание:** Ветка `phase/8.6-search-sort`. `GET /api/tasks` получил
`search` (→ `search_tasks`, перекрывает list/myday/completed) и `sort`
(→ `get_tasks(sort=)`, whitelist important/due/alpha/created). Фронтенд:
строка поиска с debounce 350 мс (поиск перекрывает фильтры) и селектор
сортировки.

**Результат:** 222 теста зелёные (+2 `test_webapp.py`); `webapp.py`
99% (1 защитная ветка), прочие 100%, TOTAL 99.75%; ruff чист.

**Статус:** PR #26 → merge → авто-деплой. Далее 8.7 — списки
(переименование/удаление/перенос задачи) + часовой пояс. Это закроет
паритет Mini App с ботом.

---

## Этап 30: Фаза 8.7 — списки + часовой пояс (Mini App = паритет)

**Дата:** 2026-05-19

**Описание:** Ветка `phase/8.7-lists-tz`. API: `PATCH /api/lists/{id}`
(переименование, ownership через `_require_own_list`, 422 на пустое),
`DELETE /api/lists/{id}` (задачи → без списка),
`POST /api/tasks/{id}/list` (перенос; цель-список проверяется на
принадлежность), `GET/PUT /api/settings` (часовой пояс; валидация через
`zoneinfo.ZoneInfo` → 422). Фронтенд: кнопки ✎/🗑 для выбранного
списка, селектор «Список» в панели задачи (перенос при сохранении),
⚙ — диалог часового пояса.

**Результат:** 225 тестов зелёные (+3 `test_webapp.py`); `webapp.py`
99% (1 защитная ветка), прочие 100%, TOTAL 99.76%; ruff чист.

**Итог Фазы 8:** Mini App функционально полностью совпадает с ботом
(задачи, срок/напоминание/просрочка, повторы, «Мой день», подзадачи,
заметки, поиск, сортировки, списки, часовой пояс). Slash-команды —
фолбэк.

**Статус:** PR #27 → merge → авто-деплой. Mini App-апгрейд завершён.

---

## Этап 31: Фаза 8.8 — SNI-роутер на :443 (постоянный URL, VPN цел)

**Дата:** 2026-05-19

**Контекст:** Пользователь хочет постоянный `https://ernstgku.beget.tech`
без вреда VPN. Диагностика: один IPv4 (нет 2-го IP/IPv6); VPN —
`vless`+`security:reality`, `dest`/`serverNames`=
`www.googletagmanager.com`, host :443. Reality не поддерживает
fallback на локальный веб-бэкенд, конфиг Amnezia править нельзя →
единственный путь: **L4 SNI-роутер на :443**.

⚠️ В выводе диагностики у пользователя засветился Reality `privateKey`
(секрет VPN-сервера) — рекомендовано пересоздать ключи в Amnezia; в чат
не сохраняю.

**Сделано (ветка `phase/8.8-sni-router`, автономно):**
`deploy/nginx-sni.conf` — `stream`+`ssl_preread`, SNI
`ernstgku.beget.tech` → `127.0.0.1:8443` (Caddy), `default` →
`127.0.0.1:8444` (xray). `deploy/Caddyfile` переведён на
`https_port 8443` (ACME по :80). `DEPLOYMENT.md` §6 переписан под
SNI-роутер: webapp → Caddy → перепубликация xray (commit-бэкап +
recreate по `docker inspect`, конфиг/ключи xray не трогаем) → nginx →
проверка → @BotFather → откат. Python не менялся → 225 тестов зелёные,
ruff чист.

**Статус:** PR #28 → merge → авто-деплой (nginx/caddy/xray ставятся
вручную по runbook). Далее с пользователем: `docker inspect
amnezia-xray` → генерирую точную безопасную команду пересоздания.