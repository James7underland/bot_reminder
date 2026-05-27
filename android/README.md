# Напоминалка — Android (TWA через PWA Builder)

Андроид-обёртка генерируется **онлайн** через [PWA Builder](https://www.pwabuilder.com/),
без установки Android SDK у тебя локально. Получаешь подписанный
`.apk` за 5 минут.

Внутри APK — **Trusted Web Activity (TWA)**: тот же Mini App
(`app.reminderr.ru/`), но запакованный в нативное Android-приложение
с иконкой в лаунчере, своим окном без браузерной адресной строки.

## Однократная сборка APK

1. Открой https://www.pwabuilder.com/
2. В большое поле URL вставь: `https://app.reminderr.ru/`.
3. Подожди, пока PWA Builder проверит manifest и service worker — должно
   быть три зелёных галки (Manifest / Service Worker / HTTPS).
4. Нажми **«Package for stores»** → выбери **Android**.
5. **Package options** (значения по умолчанию подходят, но обрати внимание):
   - Host: `app.reminderr.ru`
   - Start URL: `/`
   - App ID (package name): `ru.reminderr.android` — *запомни*.
   - Version: `0.1.0`
   - Display mode: `standalone`
6. Раздел **Signing key** — выбери `Generate new` (PWA Builder
   сгенерирует и упакует подписанный APK + отдельный keystore-файл).
   **СОХРАНИ keystore-файл и пароли** — они нужны для будущих обновлений
   приложения (иначе придётся ставить как «новое»).
7. Нажми **Download** — получишь архив со следующими файлами:
   - `app-release-signed.apk` — то, что ставится на устройство.
   - `signing.keystore` — твой ключ (**не теряй**).
   - `signing-key-info.txt` — пароли (**не теряй**).
   - `assetlinks.json` — конфиг для Digital Asset Links (см. ниже).

## Digital Asset Links — чтобы TWA было без browser-bar

По умолчанию TWA откроется с тонкой полосой «Хром-вкладки» сверху. Чтобы
её убрать, **Chrome требует подтверждения**, что сайт `app.reminderr.ru`
принадлежит тому же владельцу, что и подписанный APK.

1. Открой скачанный `assetlinks.json`. Внутри будет SHA-256 fingerprint
   из твоего keystore — он привязан именно к этой подписи APK.
2. **Замени** содержимое файла `static/.well-known/assetlinks.json` в
   этом репозитории на содержимое скачанного. Закоммить и задеплой —
   webapp начнёт отдавать его по URL
   `https://app.reminderr.ru/.well-known/assetlinks.json`.
3. Установи APK на телефон → открой → polossa должна исчезнуть.
   Если не исчезла после первого запуска — переустанови APK.

Подробности: https://developer.chrome.com/docs/android/trusted-web-activity/quick-start

## Установка APK на телефон

Так как APK не из Google Play, нужно разрешить установку из неизвестных
источников:

1. Перекинь `app-release-signed.apk` на телефон (Telegram self-chat,
   USB, Email).
2. Открой файл → Android спросит разрешение «Установка из неизвестных
   источников» для приложения, через которое открываешь (Telegram /
   браузер / Files). Разреши.
3. После установки — обычная иконка в лаунчере. Открывается как
   нативное приложение.

## Первый запуск

Появится тот же модал ввода API-токена. Получи токен в боте: `/token`,
вставь — больше спрашивать не будет.

## Обновление приложения

При выходе новой версии Mini App ничего не нужно делать — TWA каждый
раз грузит свежий HTML/JS с `app.reminderr.ru` (service worker кеширует
shell, но обновление по network-first). APK переустанавливать не надо.

APK переустанавливается, только если меняется **обёртка** (имя/иконка/
manifest на стороне TWA). Тогда снова PWA Builder → Download → install
поверх старого. Тем же keystore (важно).

## Что НЕТ в этом MVP

- ❌ Нативный AlarmManager-будильник (PWA-Notification API работает на
  Android Chrome, но не вызывает full-screen alarm).
- ❌ Виджеты на главный экран.
- ❌ Share target (нельзя «поделиться → Напоминалка»).
- ❌ Foreground service для гарантированной доставки уведомлений.

Эти возможности требуют переезд с TWA на **Capacitor** + установку
Android Studio локально. Сделаем в Phase 13.1+ под конкретные нужды.
