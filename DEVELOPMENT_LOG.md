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

---

## Этап 32: Фаза 8.9 — домен `reminderr.ru` (тупик с beget.tech)

**Дата:** 2026-05-19

**Описание:** Beget подтвердил: у технического поддомена
`ernstgku.beget.tech` A-запись менять нельзя (только виртуальный
хостинг) → для VPS непригоден, путь с ним закрыт. Пользователь
зарегистрировал настоящий домен **`reminderr.ru`** (Beget, зона .RU,
199 ₽/год) и при регистрации направил его A-записью на VPS
`155.212.227.167` (DNS Beget, NS не меняем — Cloudflare не нужен).
Это разблокировало изначально желаемый путь А: нативный
`https://reminderr.ru` через SNI-роутер (нулевой Cloudflare).

Ветка `phase/8.9-domain-reminderr`: в `deploy/Caddyfile`,
`deploy/nginx-sni.conf`, `DEPLOYMENT.md` домен заменён
`ernstgku.beget.tech` → `reminderr.ru` (исторические записи журнала не
переписываем — beget-тупик часть истории). Python не менялся → 225
тестов зелёные, ruff чист.

**Статус:** PR #29 → merge → авто-деплой кладёт верные конфиги на
сервер. Ждём активации домена (`nslookup reminderr.ru` =
155.212.227.167), затем runbook §6 (webapp → Caddy → commit-бэкап
xray → cutover → nginx → проверка Mini App+VPN → @BotFather).

---

## Этап 33: Фаза 9.1 — custom recurrence (MS To Do parity finishing)

**Дата:** 2026-05-20

**Описание:** После запуска `https://reminderr.ru` в проде пользователь
запросил «доделать до конца паритет с MS To Do». Честная оценка: ядро
уже было (Фазы 5/8). Остался реалистичный остаток (9.1–9.5),
расшаривание/вложения сознательно вне scope.

**9.1 (ветка `phase/9.1-custom-recurrence`):** `recurrence` принимает
помимо легаси-пресетов (`daily`/`weekly`/`monthly`/`yearly`) две формы:
- `every:N:[dwmy]` — каждые N единиц (валидируется регексом, N≥1);
- `weekdays:MO,WE,FR` — конкретные дни недели (CSV из `MO/TU/WE/TH/FR/SA/SU`,
  без повторов, ≥1 элемента).

`is_valid_recurrence()` — единая валидация. `next_occurrence()`
вычисляет следующую дату (для `weekdays` ищет ближайший подходящий
день в окне 1..7 дней; для `every:m/y` — с clamp последнего дня).
`complete_task()` теперь использует `is_valid_recurrence` (раньше
проверял жёстко по `RECURRENCES` — custom не спавнил следующий
экземпляр; баг найден тестом и исправлен). API `PATCH /api/tasks/{id}`
валидирует через ту же функцию (422 на мусор). Фронтенд: в панели
задачи добавлена опция «свой шаблон…» с двумя режимами (каждые N
единиц / по дням недели), парсинг/инициализация формы из текущего
значения, сборка строки при сохранении, валидация в UI.

Бот-команда `/repeat` оставлена с пресетами (advanced — через Mini
App; это согласуется с тем, что slash — фолбэк).

**Результат:** 245 тестов зелёные (+11 в `test_recurring.py`/`test_webapp.py`
для парсинга/валидации/спавна/API); `bot.py`/`database.py`/
`scheduler.py`/`tzutil.py` 100%, `config.py` 80%, `webapp.py` 99%,
TOTAL 99.77%; ruff чист.

**Статус:** PR #30 → merge → авто-деплой обновит Mini App; туннель/
сертификат/VPN не трогаются (как обычно). Далее 9.2 — smart-views
«Планируется» и «Важно» как отдельные экраны.

---

## Этап 34: Фаза 9.2 — smart-views «Планируется» и «Важно»

**Дата:** 2026-05-20

**Описание:** Ветка `phase/9.2-smart-views`. БД: `get_planned(user)` —
актив + (deadline OR reminder_at), сорт по `deadline IS NULL, deadline,
reminder_at IS NULL, reminder_at, created_at`; `get_important_tasks(user)` —
актив + `important=1`, сорт по дедлайну. Общий хелпер `_rows_to_tasks`
приводит `completed`/`important` к Python bool. API: `GET /api/planned`,
`GET /api/important` (ownership через initData). Фронтенд: чекбокс
`#myDay` заменён на селектор `#viewSel` с пунктами Все/🗓 Мой день/
📅 Планируется/⭐ Важно; `load()` маршрутизирует к нужному эндпоинту;
поиск перекрывает view, как и раньше.

**Результат:** 247 тестов зелёные (+2 в `test_webapp.py` — DB-фильтры
и ordering + API + 401 без авторизации); `bot.py`/`database.py`/
`scheduler.py`/`tzutil.py` 100%, `config.py` 80%, `webapp.py` 99%,
TOTAL 99.77%; ruff чист.

**Статус:** PR #31 → merge → авто-деплой обновит Mini App (туннель/
сертификат/VPN не трогаются). Далее 9.3 — snooze напоминания (+15 мин /
+1 ч / завтра).

---

## Этап 35: Фаза 9.3 — snooze напоминаний

**Дата:** 2026-05-20

**Описание:** Ветка `phase/9.3-snooze`. БД: добавлена
`snooze_reminder(task_id, minutes) -> bool` — сдвигает `reminder_at` к
`now(UTC) + minutes` (а не к старому значению + minutes; это семантика
«напомни ещё раз через…»), сбрасывает `reminder_sent`, возвращает `False`
при `minutes<=0` или отсутствии задачи. Использован паттерн
`datetime.now(UTC).replace(tzinfo=None)` (как в `scheduler.py`) — без
`utcnow()`-DeprecationWarning. API: `POST /api/tasks/{id}/snooze` с
Pydantic-моделью `Snooze {minutes:int}`; 422 при `minutes<=0`, 404 на
чужую задачу, при успехе возвращает декорированную задачу. Фронтенд:
под полем «Напомнить в …» добавлена строка «Отложить:» с тремя кнопками
`+15 мин`, `+1 ч`, `до завтра 9:00`; последняя в JS считает разницу до
завтрашнего 09:00 в локальной зоне и шлёт минуты в API.

**Результат:** 249 тестов зелёные (+2: DB-уровень
`test_db_snooze_reminder_sets_future_and_resets_sent` с ±1 мин допуском
+ ошибки при `minutes<=0`/несуществующем id; API
`test_api_snooze` — 200 на валидный, 422 на `0`, 404 на чужую);
`bot.py`/`database.py`/`scheduler.py`/`tzutil.py` 100%, `config.py` 80%,
`webapp.py` 99%, TOTAL 99.77%; ruff чист.

**Статус:** PR #32 → merge → авто-деплой. Далее 9.4 — ручная сортировка
задач (`order_index`, drag/стрелки в Mini App).

---

## Этап 36: Фаза 9.4 — ручной порядок задач

**Дата:** 2026-05-20

**Описание:** Ветка `phase/9.4-reorder`. БД: добавлена колонка
`order_index INTEGER` в `tasks` (идемпотентная миграция с бэкфиллом
по `id` — id монотонный, исходный порядок сохраняется); `add_task`
вставляет с `COALESCE(MAX(order_index), 0) + 1` per user, так что новая
задача попадает в конец ручного списка (как в Microsoft To Do). Дефолт
`_SORT_ORDERS`/`get_tasks` теперь `order_index, created_at` —
`created_at` остаётся доступным как явный `sort="created"`; тот же
order и в `get_tasks_by_list`. Smart-views (`get_myday`/`get_planned`/
`get_important_tasks`) сохраняют свою специализированную сортировку
(дедлайн/напоминание раньше). Логика свопа в `_move_task(direction)`:
ищем «соседа» — активную задачу того же пользователя в том же списке
(`list_id IS NULL` или `= ?`) — с минимально большим/меньшим
`order_index`, и обмениваем их `order_index`. False — для крайней,
выполненной, или несуществующей задачи. `move_task_up` /
`move_task_down` — публичные обёртки. Уникальность `order_index`
per-user гарантирована `add_task`, поэтому простой своп без сдвига
интервалов. API: `POST /api/tasks/{id}/move-up` / `…/move-down`
(ownership, тело `{"moved": bool}`, 404 на чужую). Фронтенд: в строке
задачи две маленькие ghost-кнопки ▲/▼ слева от звезды (`.mv` CSS,
не открывают панель — клик `.ttl` навешен отдельно). Обновлены
заголовки/описания.

**Результат:** 257 тестов зелёные (+8: order_index уникален per-user,
дефолт сортировки `manual`, своп ↑/↓, изоляция по user+list,
пропуск выполненных, защита от invalid task_id, API move-up/down 200,
404 на чужую); `bot.py`/`database.py`/`scheduler.py`/`tzutil.py` 100%,
`config.py` 80%, `webapp.py` 99%, TOTAL 99.78%; ruff чист.

**Статус:** PR #33 → merge → авто-деплой. Далее 9.5 — UI-полировка
(прогресс подзадач, заметнее «срочно/просрочено», порядок/цвет списков).

---

## Этап 37: Фаза 9.5 — UI-полировка (счётчик подзадач + цвет списка)

**Дата:** 2026-05-20

**Описание:** Ветка `phase/9.5-polish`. (a) Счётчик подзадач: новая
`get_steps_counts(user_id) -> {task_id: {"done": N, "total": M}}` —
один SQL `JOIN tasks ON steps.task_id = tasks.id GROUP BY task_id`,
чтобы избежать N+1 при отрисовке списка. `_decorate(task, now, counts)`
получает опциональный аргумент `counts` и добавляет `steps_done` /
`steps_total` (0/0 если в counts нет). Каждый list-эндпоинт
(`/api/tasks`, `/api/myday`, `/api/planned`, `/api/important`) делает
ровно один вызов `get_steps_counts` и применяет к каждому элементу.
Фронтенд: в `meta` задачи (под текстом) появляется строка `📋 N/M`,
когда `steps_total > 0`.

(b) Цвет списка: добавлена колонка `lists.color TEXT NOT NULL
DEFAULT '#0088CC'` (миграция идемпотентна, CREATE TABLE тоже обновлён);
валидация `is_valid_color('#RRGGBB')` через regex `^#[0-9A-Fa-f]{6}$`;
`set_list_color(list_id, color) -> bool` пишет цвет и возвращает False
для битых значений/несуществующих id. Pydantic `ListPatch` теперь
`name: str | None` + `color: str | None`; эндпоинт `PATCH /api/lists/
{id}` 422 на пустое тело, 422 на битый цвет, возвращает полный dict
списка (старый тест переписан под более широкий контракт). Фронтенд:
к панели списков добавлена кнопка 🎨, которая создаёт скрытый
`<input type="color">` с текущим значением и открывает нативный
системный пикер; опции селекта окрашены `style="color:<hex>"` с
префиксом `●` (плотно поддерживается в Chrome/Firefox/Safari).

**Результат:** 261 тест зелёный (+4: `get_steps_counts` агрегирует и
не возвращает задачи без подзадач; `/api/tasks` и `/api/myday`
декорируют `steps_*`; валидатор цвета + `set_list_color` happy/
unhappy; API `PATCH /api/lists/{id}` принимает color/имя/оба, 422 на
пустое тело и битый цвет, 404 на чужую); `bot.py`/`scheduler.py`/
`tzutil.py` 100%, `database.py` 99% (миграция-ALTER не покрыта, т.к.
тестовая БД свежая), `webapp.py` 99%, `config.py` 80%, TOTAL 99.72%;
ruff чист.

**Статус:** PR #34 → merge → авто-деплой. Phase 9 (MS To Do parity
finishing) **завершена**: 9.1 custom recurrence, 9.2 smart-views,
9.3 snooze, 9.4 manual reorder, 9.5 UI polish — все в `main`. Из
изначально объявленного «вне области» осталось только sharing/
multi-user и файловые вложения (отдельная фаза, если понадобится).

---

## Этап 38: Фаза 10.1 — стабильность Mini App и блокировки БД

**Дата:** 2026-05-20

**Описание:** Пользователь сообщил, что после Phase 9.5 в Mini App
**периодически залипает менюшка** — невозможно выбрать цвет или
ввести имя списка/задачи, помогает только перезапуск сервиса.
Диагностика выявила два независимых источника проблемы.

**(а) Нативные модалы в Telegram WebView.** В коде осталось 11 вызовов
`window.alert/prompt/confirm` (создание/переименование/удаление списка,
часовой пояс, валидация рекуррентности). В Telegram WebApp эти модалы
поддерживаются нестабильно: фокус после закрытия не всегда
возвращается в JS-event-loop, и следующий клик «не доходит» — UI
выглядит замороженным до полного перезапуска. Решение: введены
обёртки `uiAlert/uiConfirm/uiPrompt` поверх:
- `Telegram.WebApp.showAlert(msg, cb)` — официальный non-blocking alert;
- `Telegram.WebApp.showConfirm(msg, cb)` — confirm;
- кастомный inline-overlay для prompt (у TG нет нативного), с
  поддержкой Enter/Escape и Telegram BackButton как «Отмена».

Все 11 вызовов переписаны на промис-based API. Дополнительно
закрыта **утечка `<input type="color">`** в обработчике 🎨: если
пользователь закрыл системный пикер без выбора, событие `change` не
приходило и hidden-`<input>` оставался в DOM. Теперь cleanup
происходит на `blur` и через safety-timeout 60 сек.

**(б) SQLite без WAL и busy_timeout.** `bot_reminder` (планировщик
APScheduler) и `bot_webapp` (FastAPI) — два процесса, оба пишут в
одну SQLite. Без `journal_mode=WAL` писатель блокирует читателей
эксклюзивно: запрос Mini App мог висеть на блокировке, пока
планировщик не освободит лок. На запросах от UI это тоже выглядело
как «менюшка зависла». Решение в `get_connection()`:
- `PRAGMA journal_mode = WAL` (один писатель + N читателей параллельно;
  устанавливается единожды и сохраняется в файле, повторный PRAGMA — no-op);
- `PRAGMA busy_timeout = 5000` (ждать 5 сек, а не падать с
  `OperationalError: database is locked`);
- `sqlite3.connect(..., timeout=5.0)` (страховка на Python-уровне).

**Результат:** 262 теста зелёных (+1: `test_db_connection_uses_wal_and
_busy_timeout` проверяет журнал WAL, busy_timeout=5000 и foreign_keys=ON
на каждом новом соединении); `bot.py`/`scheduler.py`/`tzutil.py` 100%,
`database.py` 99%, `webapp.py` 99%, `config.py` 80%, TOTAL 99.72%;
ruff чист.

**Статус:** PR #35 → merge → авто-деплой. После раскатки пользователь
проверит — если залипания исчезли, переходим к 10.2 (backup/restore).

---

## Этап 39: Фаза 10.2 — экспорт / импорт пользовательских данных

**Дата:** 2026-05-20

**Описание:** Ветка `phase/10.2-backup-export`. Дополняет уже
существующий cron-бэкап (`deploy/backup.sh` — sqlite3 `.backup`,
ежедневно в 3:00, 14 копий) **пользовательским** экспортом/импортом,
чтобы данные можно было унести/восстановить без доступа к серверу.

**Backend.** `export_user_data(user_id)` собирает полный снимок
(version=1): списки (имя+цвет+created_at), задачи (все 14 значимых
полей: from `description` до `order_index`; `list_id` заменён на
`list_name` — id-привязка не выживает миграцию между БД), подзадачи
встроены в задачу как массив `steps`, часовой пояс в `user`. Один
проход по БД с предзагрузкой шагов в `dict[task_id -> list]`, чтобы
не делать N+1.

`import_user_data(user_id, payload, mode)`:
- `merge` (default) — существующие списки пользователя достаются по
  имени и переиспользуются; задачи дозаписываются с пересчётом
  `order_index = max+i`, чтобы не конфликтовать с уже имеющимися;
- `replace` — сначала `DELETE FROM tasks/lists WHERE user_id=?`
  (steps удаляются каскадом по ON DELETE CASCADE).
- Вся вставка — в одной транзакции (`BEGIN`/`COMMIT`/`ROLLBACK`):
  сбой посреди не оставляет частичных данных.
- Дефенсивные пропуски (пустое имя, не-dict в `tasks`, кривой цвет —
  fallback к `#0088CC`) — без падения.

Pydantic `ImportBody{payload: dict, mode: str = "merge"}`. API:
`GET /api/export` → JSON-снимок; `POST /api/import` → 200 со счётчиком
`{lists, tasks, steps}` или 422 на битый payload/неизвестный mode.

**Frontend.** Две кнопки в баре списков:
- 📦 «Экспорт» — `api("/export")` → `Blob` → `<a download>` с именем
  `reminder-backup-<exported_at>.json`; затем `uiAlert` со счётчиком.
- ↩ «Импорт» — спрятанный `<input type="file" accept="application/
  json">`, после выбора — `JSON.parse`, `uiConfirm` «replace vs merge»,
  POST `/import`, `uiAlert` с результатом, refresh.

**Результат:** 269 тестов зелёные (+6: round-trip export→import между
двумя user_id, `merge` не дублирует список с тем же именем, `replace`
вычищает + импортирует, дефенсивные пропуски malformed-элементов,
rollback при ошибке в середине (через `monkeypatch`-обёртку
sqlite3.Cursor), валидация payload — все плохие формы кидают
ValueError, API endpoint 200/422); `bot.py`/`scheduler.py`/`tzutil.py`
100%, `database.py`/`webapp.py` 99%, `config.py` 80%, TOTAL 99.74%;
ruff чист.

**Статус:** PR #36 → merge → авто-деплой. После — 10.3 (здоровье +
ротация логов).

---

## Этап 40: Фаза 10.3 — здоровье и логирование

**Дата:** 2026-05-20

**Описание:** Ветка `phase/10.3-health-logs`. Три блока эксплуатации.

**(а) Расширенный `/healthz`.** Теперь делает реальный пинг БД через
`db_ping()` (одно соединение + `SELECT 1`, ловит `sqlite3.Error`).
В ответе помимо `ok` поля `db`, `uptime_seconds` (с момента старта
процесса, `time.monotonic`) и сводные счётчики `tasks_total`/
`tasks_active`/`lists_total`/`users` из `get_global_counts()`. При
неотвечающей БД эндпоинт возвращает **HTTP 503** — внешний монитор
(systemd timer, Caddy upstream healthcheck и т.п.) сразу видит
проблему. Если БД ОК, но счётчики сломались — 200 не падает, только
warning в лог.

**(б) `GET /api/stats`.** Per-user сводка
(`active`/`completed`/`important`/`lists`/`steps_open`/
`oldest_open_at`). Один проход через 6 коротких SELECT'ов. С
initData-авторизацией. Готовая база для будущего виджета в Mini App.

**(в) Унифицированные логи с ротацией.** Новый модуль `logsetup.py`
с `setup_logging(name, level=INFO)`:
- StreamHandler в stdout → попадает в systemd journal автоматически;
- `RotatingFileHandler` 5×10 МБ при заданном env `LOG_DIR` (без env
  файлового логирования нет — удобно для локальной разработки и
  CI);
- идемпотентность через маркер на root-логгере (gunicorn/uvicorn могут
  переимпортировать модуль — не дублируем хендлеры);
- глушение шумных сторонних логгеров (`httpx`/`httpcore`/`apscheduler`/
  `telegram`) до WARNING. `httpx` пишет URL запроса к Telegram API с
  токеном бота на INFO — критично не светить;
- soft-fail на недоступном `LOG_DIR`: warning + продолжаем со
  stdout-only, чтобы не валить процесс.

`bot.py` и `webapp.py` перевешены на `setup_logging`. systemd-юниты
`bot_reminder.service` / `bot_webapp.service` получают
`Environment=LOG_DIR=...` и `ExecStartPre=/usr/bin/install -d` для
гарантии существования каталога.

**Результат:** 279 тестов зелёные (+10:
`db_ping` happy/failure-path, `get_global_counts` агрегирует,
`get_user_stats` (+`completed`, +`important`, +`steps_open`),
`/api/stats` с авторизацией и 401, `/healthz` богатый формат, 503
при отказе БД, 200 при отказе счётчиков с warning в лог,
`setup_logging` idempotent + глушит noisy, добавляет
RotatingFileHandler с правильным именем файла при `LOG_DIR`, мягко
падает при отказе mkdir); `bot.py`/`scheduler.py`/`tzutil.py` 100%,
`database.py`/`webapp.py` 99%, `config.py` 80%, TOTAL **99.75%**;
ruff чист.

**Статус:** PR #37 → merge → авто-деплой. После — выявленные пользователем
проблемы эксплуатации закрыты. Следующие итерации — по обратной связи.

---

## Этап 41: Фаза 10.4 — Mini-App polish (тост ошибок + персист состояния)

**Дата:** 2026-05-20

**Описание:** Ветка `phase/10.4-ux-polish`. Frontend-only PR
(бэкенд не трогается, 279 тестов остаются зелёными).

**(а) Toast-уведомления об ошибках API.** До этого PR `api()` молча
возвращал JSON ошибки — пользователь не видел, что запрос упал, а в
консоли остался след «`Uncaught (in promise)`». Теперь:
- сетевые сбои (`fetch` reject — отсутствие интернета, CORS, DNS)
  сурфятся как `«Нет сети: …»`;
- HTTP 4xx/5xx (кроме 401, который уже рисует баннер) показываются
  через `uiToast("Ошибка: " + body.detail)` с попыткой вытащить
  серверное сообщение из JSON (если оно не JSON — фолбэк на код);
- 401 — как и раньше, заменяет body на «Откройте из Telegram».

`uiToast(msg, kind="err"|"ok")` — лёгкий неблокирующий оверлей
снизу-по-центру, анимируется (`opacity + translateY`), исчезает через
4 сек. Параметр запроса `_silent: true` подавляет тост — оставлен на
будущее (для опционально-молчащих fire-and-forget вызовов).

**(б) Сохраняемое состояние UI.** `view` (Все/Мой день/Планируется/
Важно), `listId`, `sort`, `showDone` записываются в `localStorage` под
ключом `bot_reminder_ui` при каждом изменении. До первого `load()` —
функция `restoreUI()` устанавливает значения в селекторах, чтобы
первый запрос сразу шёл в нужный view (а не сначала «Все», потом
переключение). `localStorage` доступен в Telegram WebView, и у каждого
пользователя свой WebView, поэтому изоляция гарантирована без
user_id-префикса в ключе.

**Результат:** 279 тестов остаются зелёными (frontend-only); ruff чист.

**Статус:** PR #38 → merge → авто-деплой. Дальше — по обратной связи
от пользователя.

---

## Этап 42: Фаза 10.5 — picker часовых поясов

**Дата:** 2026-05-21

**Описание:** Ветка `phase/10.5-timezones`. Пользователь подтвердил,
что залипания UI пропали, и попросил **«добавить больше часовых
поясов»**. До этого PR `/timezone` принимал свободный ввод IANA-имени
через `uiPrompt` — большинству пользователей это бесполезно, IANA
помнят только инженеры (`Europe/Moscow` против `Москва`).

**Backend.** `tzutil.list_common_timezones()` — курируемый список
58 общеупотребительных зон, сгруппирован по регионам Россия / СНГ /
Европа / Азия / Америка / Океания / Африка / Прочее. Для каждой
зоны вычисляется текущее смещение от UTC через `zoneinfo` (учитывает
DST), форматируется как `UTC+03:00` / `UTC-05:00`. Возвращает список
с полями `{tz, label, group, offset, offset_minutes}`, отсортированный
от запада к востоку по `offset_minutes`. `GET /api/timezones` (под
initData) отдаёт это. Закрыты Россия (12), СНГ (11), Европа (11),
Азия (10), Америка (10), Океания (4), Африка (3), UTC.

**Frontend.** Универсальный модал `uiSelect(title, options, current)`:
поиск по подстроке (фильтрует элементы и скрывает пустые группы),
группировка через `<div class="modal-group">`, подсветка текущего
значения, ESC/BackButton = отмена. CSS — пилюли через `.modal-item`,
прокручиваемый список `.modal-items` с `max-height:60vh`. Замена
старого `uiPrompt` в обработчике `#tzBtn`: грузим `/timezones`,
маппим в `{value: z.tz, label: "(UTC+03:00) Москва — Europe/Moscow",
group: z.group}`, открываем `uiSelect`. На успехе — `uiToast("Часовой
пояс сохранён", "ok")` вместо blocking `uiAlert`.

**Результат:** 283 теста зелёные (+4: содержимое list_common_timezones,
сортировка запад→восток, все зоны валидны через `valid_timezone`, API
401 без авторизации и валидная структура с авторизацией);
`bot.py`/`tzutil.py`/`scheduler.py` 100%, `database.py`/`webapp.py`
99%, `config.py` 80%, TOTAL 99.75%; ruff чист.

**Статус:** PR #39 → merge → авто-деплой. Дальше по списку
пользователя: 10.6 (drag-and-drop), 10.7 (undo для удаления),
10.8 (виджет статистики).

---

## Этап 43: Фаза 10.6 — drag-and-drop переупорядочивание

**Дата:** 2026-05-21

**Описание:** Ветка `phase/10.6-drag-drop`. Дополняет существующие
кнопки ▲/▼ полноценным drag-and-drop, который удобнее для перемещения
задачи на несколько позиций сразу.

**Backend.** Новая `database.reorder_task(task_id, after_task_id)`:
- ловит `task_id`, его `user_id`+`list_id`, проверяет, что задача
  активна (а то перенумерование выполненных бессмысленно);
- собирает всех активных «соседей» в той же подгруппе (тот же user
  + тот же `list_id`, включая `IS NULL`), отсортированных по
  текущему `order_index, created_at, id`;
- убирает `task_id` из последовательности и вставляет либо после
  `after_task_id`, либо в начало (`after=None`);
- если `after_task_id` указан, но не в той же подгруппе → False
  (например, пытаются вставить задачу из «без списка» после задачи
  в именованном списке — отвергаем);
- в одной транзакции переписывает `order_index = 1..N`. На сбое в
  середине UPDATE — `ROLLBACK`, порядок остаётся прежним (есть тест).

API: `POST /api/tasks/{id}/reorder {after: int|null}`. 404 на чужую
задачу (через `_require_own_task` обоих id), 409 на несовместимую
подгруппу.

**Frontend.** Ручка `⠿` (Braille Pattern Dots) слева в строке —
`touch-action:none`, чтобы тач-устройства не интерпретировали
свайп как прокрутку списка. Pointer Events (один код для мыши и
тача) с `setPointerCapture`:
- `pointerdown` на ручке → `li.dragging` (opacity .55);
- `pointermove` → `document.elementFromPoint` находит наведённую
  `li`, по половине высоты решаем «выше/ниже» и подкрашиваем
  `.drop-above` / `.drop-below` (тонкая полоса акцентным цветом);
- `pointerup` → высчитываем `after_id` (id предыдущей `li`
  относительно нового положения, `null` если перед первой),
  оптимистично переставляем DOM, шлём POST на `/reorder`. На
  ошибке — `load()` синхронизирует с сервером.

Drag отключён в smart-views (My Day / Planned / Important), при
поиске и при заданной сортировке: в этих режимах порядок строится
не из `order_index`, и тащить там нечего.

**Результат:** 289 тестов зелёных (+6: drag из конца в начало,
после соседа, изоляция по списку, реордер внутри именованного
списка, отказ на выполненной/несуществующей/чужой `after`,
rollback на сбое, API 200/404/409); ruff чист; TOTAL **99.70%**.

**Статус:** PR #40 → merge → авто-деплой. Дальше — 10.7 (undo для
удаления) и 10.8 (виджет статистики).

---

## Этап 44: Фаза 10.7 — undo для удаления списка

**Дата:** 2026-05-21

**Описание:** Ветка `phase/10.7-undo-delete`. До этого PR удаление
списка было необратимым: `delete_list` cascade'ом отвязывал задачи
и `DELETE FROM lists`. Теперь soft-delete с 24-часовым окном
восстановления.

**БД.** Колонка `lists.deleted_at TEXT` (миграция идемпотентна,
`CREATE TABLE` тоже обновлён). `delete_list(id)` теперь ставит
`deleted_at = CURRENT_TIMESTAMP` только если запись активна
(`AND deleted_at IS NULL`) — повторный delete даёт `False`.
`get_lists(user_id, include_deleted=False)` фильтрует удалённые по
умолчанию; `include_deleted=True` нужен только для endpoint
восстановления. Новые функции:
- `restore_list(id)` — снимает `deleted_at`. False, если не было
  удалено (idempotency).
- `purge_deleted_lists(older_than_hours=24)` — физическое удаление:
  одной транзакцией NULL'ит `tasks.list_id` для всех затронутых
  списков и `DELETE FROM lists`. Использует `datetime('now', '-N hours')`
  для сравнения с `deleted_at`. Rollback на сбое. Возвращает счётчик.

**Scheduler.** В `scheduler.setup_scheduler()` добавлен второй job
`purge_deleted` (`interval, hours=1`) → `_purge_old_soft_deletes()`.
Обёртка `_purge_old_soft_deletes` глотает любые исключения с
`logger.error` — иначе APScheduler пометил бы job сломанным.

**Импорт.** `import_user_data` в merge-режиме теперь явно фильтрует
по `deleted_at IS NULL` при сопоставлении имён списков, чтобы импорт
не оживлял удалённый список как побочный эффект (пользователь явно
его удалил — импорт должен создать новый).

**API.** `POST /api/lists/{id}/restore` (initData auth). Использует
`get_lists(include_deleted=True)` для определения принадлежности и
статуса: 404, если списка нет / он чужой / он не был удалён.
Существующий `DELETE /api/lists/{id}` сохраняет интерфейс, но теперь
выполняет soft-delete.

**Frontend.** Замена `uiConfirm` на оптимистичный паттерн «удали +
покажи undo»:
- сразу скрываем список (`load()`),
- `uiUndoToast(text, action, ms)` показывает тост с кнопкой
  «Отменить» (8 сек), при клике зовёт `POST /restore`;
- по таймауту тост исчезает без действия — у пользователя остаётся
  24 часа до физического purge'а (но через UI оттуда уже не
  достать; это сознательно — UI отражает «удалено», а 24 часа —
  страховка на случай ошибочного DELETE).
- Тост стилизован под dark, кнопка action голубая (`#60a5fa`).

**Тесты.** +8: soft-delete не дёргает задачи, idempotent повторный
delete, restore возвращает + idempotent; `purge_deleted_lists`
удаляет старые и отвязывает задачи; `import_user_data` merge не
переиспользует soft-deleted список; API restore 200/404 (своя
активная, чужая, своя удалённая); scheduler регистрирует оба job'а;
purge-wrapper глотает ошибки и логирует. Обновлён `test_delete_list_*`
под новую семантику. 294 теста зелёные, TOTAL **99.47%**, ruff чист.

**Статус:** PR #41 → merge → авто-деплой. Дальше — 10.8 (виджет
статистики в Mini App).

---

## Этап 45: Фаза 10.8 — виджет статистики в Mini App

**Дата:** 2026-05-21

**Описание:** Ветка `phase/10.8-stats-widget`. Frontend-only. Делает
видимым `/api/stats` (Phase 10.3) — до этого момент данные были, но
пользователь о них не знал. Бэйдж в шапке справа от заголовка
показывает три ключевые цифры: «N активн. · ★ M · 📋 K», по клику —
полная разбивка.

**Шапка.** `<header>` теперь flex: `<h1>Мои задачи</h1>` слева,
`#statsBadge` справа. Бэйдж стилизован под pill (`background:
var(--card)`, скруглённые углы, hover-border). Внутри — `.num`
(основной цвет), `.imp` (жёлтый для звёзд, как у `.star.on`).

**Логика.** `refreshStats()` вызывается из конца `load()`, делает
`api("/stats", {_silent: true})`. Флаг `_silent` уже был в api(), но
охватывал только HTTP-ошибки — теперь и сетевые. Это важно: бэйдж —
fire-and-forget, не должен сыпать тостами «Нет сети» при каждом
повторном `load()` если стат-эндпоинт недоступен.

Клик по бэйджу открывает `uiAlert` с многострочным текстом:
активные, важные, выполненные, списки, открытые подзадачи, дата
самой старой активной задачи (отформатирована через
`Date.toLocaleDateString` в локали пользователя).

**Результат:** 294 теста зелёные (frontend-only, бэкенд не
изменился); ruff чист.

**Статус:** PR #42 → merge → авто-деплой. Список запросов
пользователя (часовые пояса, drag-and-drop, undo для удаления,
виджет статистики) — **закрыт**. Дальше — по новой обратной связи.