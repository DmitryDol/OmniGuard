# OmniGuard

Десктопное приложение для видеонаблюдения с интеллектуальным обнаружением людей в охраняемых зонах.

## 1. Обзор проекта

OmniGuard — это настольное приложение для видеонаблюдения, построенное на Python с использованием PySide6 (Qt) и нейросетевой модели YOLOv5 nano для детекции людей в реальном времени. Приложение позволяет подключаться к IP-камерам или веб-камерам, задавать произвольные полигональные охраняемые зоны, записывать видео при обнаружении человека в зоне и отправлять email-уведомления. Также реализована трансляция видеопотока по сокетам на мобильное Android-приложение.

## 2. Стек технологий

### Десктопное приложение

- **Язык**: Python 3.13
- **GUI фреймворк**: PySide6 (Qt 6)
- **Менеджер пакетов**: uv
- **Конфигурация**: pydantic-settings (`.env`)
- **Линтер**: Ruff
- **Ключевые библиотеки**:
  - `opencv-python`: Захват и обработка видео
  - `torch` / `torchvision`: Инференс нейросети
  - `supervision`: Аннотации и полигональные зоны детекции
  - `numpy`: Работа с массивами данных и кадрами

### Нейросетевая модель

- **Архитектура**: YOLOv5 nano (`yolov5n.pt`)
- **Класс детекции**: Только люди (class 0)
- **Порог уверенности**: Настраивается через `.env` (по умолчанию 0.4)

### База данных

- **СУБД**: PostgreSQL (запускается через Docker Compose)
- **Драйвер**: QPSQL (Qt SQL)

### Уведомления

- **Протокол**: SMTP (Gmail)
- **Формат**: Email с прикрепленным изображением-кадром

### Мобильное приложение

- **Платформа**: Android (готовый APK в `apk file/`)
- **Протокол связи**: TCP-сокеты (передача JPEG-кадров)

## 3. Архитектура

Приложение состоит из нескольких модулей:

1.  **`main.py`** — Точка входа. Содержит главное окно приложения (`HumanDetectorDesktopApp`) и поток обработки видео (`VideoThread`). Управляет GUI, камерами, детектором, записью видео и сокет-трансляцией.
2.  **`config.py`** — Централизованная конфигурация. Загружает настройки из `.env` файла через `pydantic-settings`. Содержит настройку логирования.
3.  **`personDetector.py`** — Модуль детекции людей. Оборачивает модель YOLOv5n, обрабатывает кадры, определяет наличие людей в полигональных зонах с помощью библиотеки `supervision`.
4.  **`camera.py`** — Класс камеры. Обертка над `cv2.VideoCapture` с поддержкой IP-камер (RTSP/HTTP через FFmpeg) и локальных веб-камер.
5.  **`connection.py`** — Слой доступа к данным. CRUD-операции для таблиц `cameras` и `zones` в PostgreSQL через Qt SQL (QPSQL).
6.  **`zone_redactor.py`** — Визуальный редактор охраняемых зон. Позволяет создавать, редактировать и удалять произвольные полигональные зоны поверх кадра с камеры (drag & drop вершин).
7.  **`email_server.py`** — Сервис email-уведомлений. Отправляет письмо с изображением при обнаружении человека в зоне через Gmail SMTP.
8.  **`out_of_date_video_cleaner.py`** — Автоочистка старых видеозаписей. Удаляет `.avi` файлы старше заданного времени жизни (по умолчанию 48 часов).

### Структура каталогов

```
OmniGuard/
├── main.py                      # Главное приложение и VideoThread
├── config.py                    # Конфигурация (pydantic-settings) и логирование
├── camera.py                    # Класс камеры (cv2.VideoCapture)
├── connection.py                # Доступ к БД (Qt SQL / PostgreSQL)
├── personDetector.py            # Детектор людей (YOLOv5n + supervision)
├── zone_redactor.py             # Визуальный редактор полигональных зон
├── email_server.py              # Email-уведомления (Gmail SMTP)
├── out_of_date_video_cleaner.py # Автоочистка старых видео
├── yolov5n.pt                   # Веса модели YOLOv5 nano
├── pyproject.toml               # Зависимости, метаданные и конфигурация Ruff
├── uv.lock                      # Lockfile зависимостей
├── .env                         # Переменные окружения (не в git)
├── .env.example                 # Шаблон переменных окружения
├── .gitignore                   # Правила исключений для git
├── docker-compose.yml           # Docker Compose для PostgreSQL
├── UIFiles/                     # Qt Designer UI файлы и сгенерированный Python-код
│   ├── main_window.ui
│   ├── change_email.ui
│   ├── add_edit_camera.ui
│   ├── cameras_list.ui
│   ├── zone_redactor.ui
│   └── ui_*.py                  # Сгенерированные Python-файлы (pyside6-uic)
├── data/
│   └── videos/                  # Хранилище записанных видео
├── apk file/
│   └── app-debug.apk            # Android-приложение для просмотра потока
└── plan.md                      # План развития проекта
```

## 4. Ключевые возможности

- **Детекция людей в реальном времени** — YOLOv5 nano с пропуском кадров (каждый N-й кадр) для оптимизации производительности
- **Полигональные охраняемые зоны** — Визуальный редактор для создания произвольных многоугольных зон с возможностью перетаскивания вершин
- **Поддержка нескольких камер** — Подключение IP-камер (RTSP/HTTP) и локальных веб-камер, переключение через выпадающий список
- **Запись видео** — Автоматическая запись в `.avi` при включенном детекторе с таймштампом в имени файла
- **Email-уведомления** — Отправка письма с кадром обнаружения через Gmail SMTP (с защитой от спама — не чаще раза в 5 минут)
- **Стриминг на мобильное устройство** — Трансляция видеопотока по TCP-сокетам на Android-клиент
- **Автоочистка** — Удаление видеозаписей старше заданного срока (по умолчанию 48 часов) при запуске приложения
- **Управление камерами** — CRUD для камер (IP, FPS, разрешение, имя) через GUI и PostgreSQL
- **Централизованная конфигурация** — Все настройки вынесены в `.env` файл

## 5. Установка и запуск

### 5.1. Предварительные требования

- [Python 3.13+](https://www.python.org/downloads/)
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (менеджер пакетов)
- [Docker](https://docs.docker.com/get-started/get-docker/) и [Docker Compose](https://docs.docker.com/compose/install/) (для PostgreSQL)
- [Git](https://git-scm.com/downloads)
- **PostgreSQL 17 Client Tools** (только клиент, см. шаг 5.3)

### 5.2. Клонирование репозитория

```bash
git clone https://github.com/DmitryDol/OmniGuard.git
cd OmniGuard
```

### 5.3. Установка PostgreSQL Client Tools (Windows)

> Qt's QPSQL драйвер требует `libpq.dll` из PostgreSQL клиентских инструментов. Без этого приложение не запустится.

**Через winget:**
```powershell
winget install PostgreSQL.PostgreSQL.17
```

После установки убедись, что путь `C:\Program Files\PostgreSQL\17\bin` добавлен в системный PATH (установщик делает это автоматически). Перезапусти терминал и проверь:

```powershell
Get-Item "C:\Program Files\PostgreSQL\17\bin\libpq.dll"
```

> При установке через EDB installer выбери **только** «Command Line Tools» — сам сервер PostgreSQL не нужен, он запускается в Docker.

### 5.4. Настройка окружения

Создайте файл `.env` на основе шаблона и при необходимости измените значения:

```bash
cp .env.example .env
```

Содержимое `.env.example`:

```env
# PostgreSQL config
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=your_password_here
DB_NAME=omniguard_db

# Socket server config (for mobile app streaming)
SOCKET_SERVER_IP=0.0.0.0
SOCKET_SERVER_PORT=8000

# Email notifications config (Gmail SMTP)
SMTP_SENDER_EMAIL=your_email@gmail.com
SMTP_SENDER_PASSWORD=your_app_password_here
SMTP_RECEIVER_EMAIL=receiver@example.com

# Video recording config
VIDEO_STORAGE_PATH=data/videos/
VIDEO_LIFETIME_HOURS=48

# Detection config
DETECTION_EVERY_N_FRAMES=5
DETECTION_CONFIDENCE_THRESHOLD=0.4
```

> ⚠️ Для email-уведомлений через Gmail необходимо использовать [пароль приложения](https://support.google.com/accounts/answer/185833), а не пароль от аккаунта.

### 5.5. Запуск базы данных

PostgreSQL запускается через Docker Compose. Параметры подключения берутся из `.env` файла:

```bash
docker compose up -d
```

Проверьте, что контейнер запущен и здоров:

```bash
docker compose ps
```

Ожидаемый результат:

```
NAME             IMAGE           STATUS                   PORTS
omniguard-db     postgres:17     Up X seconds (healthy)   0.0.0.0:5432->5432/tcp
```

При необходимости остановить БД:

```bash
docker compose down
```

### 5.6. Установка зависимостей Python

```bash
uv sync
```

Эта команда автоматически создаст виртуальное окружение (`.venv`) и установит все зависимости из `pyproject.toml`.

### 5.7. Запуск приложения

```bash
uv run main.py
```

При первом запуске приложение автоматически создаст необходимые таблицы в базе данных (`cameras`, `zones`).

## 6. Использование

1. Запустите приложение (`uv run main.py`)
2. Выберите камеру в выпадающем списке (при первом запуске будет добавлена веб-камера по умолчанию)
3. Добавьте IP-камеры через **Меню → Настройки камер**
4. Настройте охраняемые зоны через **Меню → Настройки зонирования**
5. Настройте email-уведомления через **Меню → Настройки почты**
6. Нажмите **«Включить распознавание людей на видео»** для запуска детектора

### Конвертация UI файлов

При изменении `.ui` файлов в Qt Designer, необходимо сконвертировать их в Python:

```bash
pyside6-uic UIFiles/main_window.ui -o UIFiles/ui_main_window.py
pyside6-uic UIFiles/change_email.ui -o UIFiles/ui_change_email.py
pyside6-uic UIFiles/add_edit_camera.ui -o UIFiles/ui_add_edit_camera.py
pyside6-uic UIFiles/cameras_list.ui -o UIFiles/ui_cameras_list.py
pyside6-uic UIFiles/zone_redactor.ui -o UIFiles/ui_zone_redactor.py
```

## 7. План развития

Подробный план улучшений и новых возможностей описан в файле [`plan.md`](plan.md).
