# Напоминалка — Windows (MSIX через PWA Builder)

Сборка идёт онлайн через [PWA Builder](https://www.pwabuilder.com/),
**без локальной установки чего-либо** (никакого Rust, никакого
Visual Studio). На выходе — `.msix`-пакет с тестовым сертификатом,
устанавливается как обычное Windows-приложение.

Внутри окна — тот же UI, что в Telegram Mini App. Бэкенд общий
(`app.reminderr.ru`). Авторизация — по API-токену (`/token` в боте).

## Однократная сборка

1. Открой https://www.pwabuilder.com/
2. В большое поле URL вставь: `https://app.reminderr.ru/` → Start.
3. Подожди, пока PWA Builder проверит manifest и service worker —
   должны быть три зелёных галки (Manifest / Service Worker / HTTPS).
4. Нажми **«Package for stores»** → **Windows**.
5. **Windows Package Options** — заполни так:
   - **Package ID**: `Reminderr.Napominalka`
   - **Publisher ID**: `CN=Reminderr`
   - **Publisher display name**: `Reminderr`
   - Остальное (AI / All Settings) можно не трогать.
6. Жми **«Download Package»**. Получишь ZIP-архив со следующим:
   - `Reminderr.Napominalka_x.x.x.x_x64.msix` — сам пакет приложения.
   - `Reminderr.Napominalka_x.x.x.x.cer` — тестовый сертификат подписи.
   - `Install.ps1` — скрипт-установщик (ставит сертификат в Trusted
     Root + затем сам MSIX).
   - `README.html` — инструкция от PWA Builder.

## Установка на Windows

1. Распакуй ZIP.
2. **Включи «Режим разработчика»** один раз (Windows требует его для
   установки MSIX, подписанного локальным сертификатом):
   - `Параметры → Конфиденциальность и безопасность → Для разработчиков →
     "Режим разработчика" = Вкл`.
3. **Запусти `Install.ps1`** — правой кнопкой → **«Выполнить с помощью
   PowerShell»**. Скрипт:
   - попросит подтверждение установки сертификата в Trusted Root —
     соглашайся (`Y`);
   - установит сам MSIX.
4. **Если PowerShell ругается на политику выполнения**: открой
   PowerShell от Администратора и выполни:
   ```powershell
   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
   .\Install.ps1
   ```
5. После установки — иконка приложения в Пуске → клик → открывается
   как обычное Windows-окно (не браузерное). При первом запуске
   попросит API-токен — получи `/token` в боте.

## Обновление

Обновления **самого UI** прилетают автоматически с `app.reminderr.ru`
(service worker делает network-first cache). Переустанавливать MSIX не
надо.

Если изменится **обёртка** (имя пакета, иконка, manifest), снова
PWA Builder → Download → запустить новый `Install.ps1`. Тем же
Publisher ID (важно — иначе Windows воспримет как другое приложение).

## Что НЕТ в этом MVP (Phase 13.0)

- ❌ Системные ОС-уведомления (только Telegram-уведомления от бота). PWA
  Notification API технически работает, но требует регистрации Push API
  и сервера — займёмся в Phase 13.1+.
- ❌ Системный трей с непрочитанными.
- ❌ Авто-старт с Windows.
- ❌ Глобальные горячие клавиши.
- ❌ Хранение токена в Windows Credential Manager (пока — localStorage
  внутри MSIX, как в PWA).

Эти возможности требуют переход с PWA Builder MSIX на нативную
обёртку — Tauri (Rust + WebView2) или WinUI 3. Делаем по мере
необходимости в Phase 13.1+, под конкретные задачи (особенно когда
дойдёт до per-task notification routing с настоящими ОС-будильниками).

## Подпись и SmartScreen

Тестовый сертификат из PWA Builder подходит только для **локальной
установки**. Если придётся раздавать .msix другим людям, нужен
**code signing certificate** от трастового CA (~$200/год). Откладываю,
пока пользователь один.

## Альтернатива — Microsoft Store

Тот же `.msix` можно загрузить в **Microsoft Store** через Partner
Center (нужен ~$19 разовый платёж за dev-аккаунт). После публикации
любой пользователь сможет ставить из Store без возни с сертификатами.
Не делаем сейчас — single-user проект, sideloading достаточно.
