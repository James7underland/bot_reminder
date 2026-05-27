# Напоминалка — Windows desktop (Tauri)

Нативная обёртка Mini App для Windows. Использует **системный WebView**
(Edge WebView2, на Windows 10/11 уже предустановлен), потому бандл
получается лёгким (~5 МБ).

Внутри окна — тот же UI, что в Telegram Mini App. Бэкенд — общий
(`app.reminderr.ru`). Авторизация — по API-токену (см. ниже).

## Что внутри

- `src-tauri/` — Rust-проект Tauri 2.
- `src-tauri/tauri.conf.json` — настройки окна (размеры, заголовок,
  URL, иконки, инсталлятор).
- `src-tauri/src/lib.rs` + `main.rs` — минимальный бутстрап Tauri.
  Native-кода пока нет.
- `src-tauri/icons/icon.png` — источник 512×512, из которого
  генерируются все остальные форматы иконок.
- `package.json` — обёртка для запуска Tauri CLI через `npm`.

## Однократная настройка

1. **Установить Node.js** (≥ 18): https://nodejs.org/ — LTS.
2. **Установить Rust**:
   ```powershell
   winget install Rustlang.Rustup
   ```
   После установки перезапустить терминал, проверить: `cargo --version`.
3. **WebView2** на Windows 10/11 — уже стоит. Если нет, инсталлятор
   Tauri сам его поставит на первом запуске.
4. **Установить npm-зависимости**:
   ```powershell
   cd desktop
   npm install
   ```
5. **Сгенерировать иконки** (один раз — Tauri сам сделает 32/128/256/ico):
   ```powershell
   npm run tauri icon src-tauri/icons/icon.png
   ```

## Сборка

**Разработка** — окно с hot-reload (изменения в `tauri.conf.json` сразу
применяются):
```powershell
npm run dev
```

**Релиз** — `.msi` и `.exe` (NSIS) инсталляторы:
```powershell
npm run build
```

Готовые файлы появятся в `src-tauri/target/release/bundle/`:
- `msi/Напоминалка_0.1.0_x64_ru-RU.msi` — для install через `msiexec`.
- `nsis/Напоминалка_0.1.0_x64-setup.exe` — обычный setup-wizard.

Любой можно запустить → приложение установится в `%LocalAppData%\Programs\Напоминалка`,
появится в Пуске и на рабочем столе.

## Первый запуск

При первом запуске откроется тот же модал ввода API-токена, что и в PWA.
Получи токен в боте командой `/token`, вставь — больше спрашивать не
будет.

## Что НЕТ в этом MVP (Phase 13.0)

- ❌ Системные ОС-уведомления (только Telegram-уведомления от бота).
- ❌ Системный трей с непрочитанными.
- ❌ Авто-старт с Windows.
- ❌ Глобальные горячие клавиши.
- ❌ Хранение токена в Windows Credential Manager (пока — localStorage,
  как в PWA).

Эти возможности добавятся прицельно через
[Tauri-плагины](https://v2.tauri.app/plugin/) в следующих фазах под
конкретные задачи (см. Phase 13.1+: per-task notification routing).

## Подпись и SmartScreen

Релизный `.exe` пока не подписан → при первом запуске Windows покажет
«SmartScreen: неизвестный издатель». Нажми «Подробнее → Выполнить в
любом случае». Чтобы убрать — нужен **code signing certificate**
(~$200/год); решение откладывается, пока пользователь один.
