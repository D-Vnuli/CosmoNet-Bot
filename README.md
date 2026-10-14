# 🌌 CosmoNet VPN

> **Проект полностью закрыт и больше не используется.** Репозиторий сохранён как архив последней версии; поддержка, развёртывание, платежи и новые подписки не ведутся. Описанные ниже возможности отражают состояние проекта на момент закрытия.

CosmoNet — VPN-сервис с управлением подпиской через Telegram-бот и Windows-клиент. Бот создаёт и продлевает VPN-доступ в 3X-UI, выдаёт персональную конфигурацию, принимает оплату и обслуживает защищённый API для приложения Windows.

Актуальная Windows-версия клиента: **0.2.25**. Исходный код клиента находится в отдельном репозитории CosmoNet-App.

## Возможности

### Пользователь

- регистрация по `/start` и просмотр статуса подписки;
- бесплатный пробный период: 24 часа, 1 устройство, 500 МБ трафика;
- тарифы на 7 или 30 дней с лимитом устройств;
- оплата картой или через СБП в YooKassa;
- оплата через Telegram Stars;
- автоматическое создание нового VPN-профиля или продление существующего без смены конфигурации;
- персональная ссылка подписки и инструкции для Android, iOS, Windows и macOS;
- вход в Windows-клиент через подтверждение в Telegram;
- обратная связь со скриншотом или текстом для поддержки.

### Администратор

- статистика бота и VPN-профилей 3X-UI;
- список активных и неактивных подписок;
- проверка доступности 3X-UI;
- рассылка текста или одной фотографии по выбранному сегменту;
- уведомления об окончании подписки;
- получение обращений пользователей с их Telegram ID и контактными данными.

## Тарифы и оплата

| Тариф | Срок | Устройства | Цена картой/СБП | Telegram Stars |
|---|---:|---:|---:|---:|
| Promo | 24 часа | 1 | бесплатно | — |
| Demo | 7 дней | 1 | 50 ₽ | 30 ⭐ |
| Lite | 30 дней | 1 | 129 ₽ | 79 ⭐ |
| Standard | 30 дней | 3 | 199 ₽ | 119 ⭐ |
| Family | 30 дней | 5 | 279 ₽ | 169 ⭐ |

Цены Stars настраиваются переменными окружения. Стоимость в рублях и параметры тарифа заданы в `services/tariff_service.py`.

Оплата картой и СБП проходит на стороне YooKassa. После подтверждённого webhook бот сопоставляет платёж с заказом и выдаёт или продлевает доступ. Повторная доставка одного платёжного события не создаёт второе продление. Telegram Stars обрабатываются через стандартные платёжные обновления Telegram.

## Как устроено

```text
Пользователь
    │
    ├── Telegram-бот ── YooKassa / Telegram Stars
    │        │
    │        ├── SQLite: пользователи, заказы, платежи
    │        └── 3X-UI: VPN-профили, срок доступа, лимит устройств
    │
    └── CosmoNet для Windows ── защищённый API бота ── 3X-UI
```

Telegram ID используется как идентификатор клиента 3X-UI. SQLite хранит данные бота и заказов, а 3X-UI остаётся источником состояния VPN-профиля: статуса, срока действия и лимита устройств.

Встроенный `aiohttp` API обслуживает авторизацию приложения, получение данных подписки, обратную связь, проверку обновлений Windows-клиента и создание платёжной ссылки YooKassa для авторизованного пользователя.

## Технологии

- Python 3.10+
- aiogram 3
- aiohttp
- SQLite
- 3X-UI API
- YooKassa API
- unittest

## Структура

```text
CosmoNet-Bot/
├── bot.py                          # запуск бота и HTTP API
├── config.py                       # настройки из .env
├── database.py                     # SQLite: пользователи, заказы и платежи
├── handlers/
│   ├── admin.py                    # админ-панель и рассылки
│   └── menu.py                     # пользовательские сценарии и оплата
├── keyboards/                      # меню, тарифы и кнопки
├── services/
│   ├── app_auth_service.py         # авторизация Windows-клиента
│   ├── app_feedback_api.py         # API приложения и YooKassa webhook
│   ├── stars_payment_service.py    # Telegram Stars
│   ├── subscription_service.py     # выдача и продление доступа
│   ├── tariff_service.py           # тарифы и цены
│   ├── yookassa_payment_service.py # YooKassa
│   └── xui_service.py              # 3X-UI
├── tests/                          # автоматические тесты
├── .env.example                    # пример переменных окружения
└── requirements.txt
```

## Локальный запуск

```bash
git clone <URL-репозитория>
cd CosmoNet-Bot
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python bot.py
```

Linux/macOS:

```bash
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python bot.py
```

При первом запуске база SQLite создаётся в `database/cosmonet.db`.

## Настройка окружения

Минимальный набор переменных:

```env
BOT_TOKEN=YOUR_BOT_TOKEN
BOT_USERNAME=your_bot_username
ADMIN_IDS=123456789

XUI_BASE_URL=https://panel.example.com
XUI_API_TOKEN=YOUR_XUI_API_TOKEN
XUI_SUB_BASE_URL=https://sub.example.com
XUI_INBOUND_ID=3

YOOKASSA_SHOP_ID=YOUR_SHOP_ID
YOOKASSA_SECRET_KEY=YOUR_SECRET_KEY
YOOKASSA_RETURN_URL=https://example.com/payment-return

APP_API_HOST=127.0.0.1
APP_API_PORT=8080
PAY_SUPPORT_CONTACT=@your_username
```

| Переменная | Назначение |
|---|---|
| `BOT_TOKEN` | токен бота от BotFather |
| `BOT_USERNAME` | username бота без `@`; нужен для авторизации приложения |
| `ADMIN_IDS` | Telegram ID администраторов через запятую |
| `XUI_BASE_URL` / `XUI_API_TOKEN` | доступ к панели 3X-UI |
| `XUI_SUB_BASE_URL` | публичный адрес ссылок подписки |
| `XUI_INBOUND_ID` | VLESS inbound для новых клиентов |
| `YOOKASSA_*` | реквизиты YooKassa и адрес возврата после оплаты |
| `STARS_PRICE_*` | стоимость платных тарифов в Telegram Stars |
| `APP_API_HOST` / `APP_API_PORT` | адрес HTTP API для Windows-клиента |
| `PAY_SUPPORT_CONTACT` | контакт команды `/paysupport` |

Полный список, включая настройки временного VPN для авторизации Telegram и манифест Windows-обновлений, находится в [.env.example](.env.example).

Для приёма YooKassa webhook настройте публичную доставку на маршрут:

```text
POST /payments/yookassa/result
```

Не добавляйте `.env`, SQLite-базу, ключи 3X-UI или реквизиты YooKassa в Git.

## CosmoNet для Windows

Windows-клиент подключается к API по HTTPS, получает подписку после подтверждения входа в Telegram и запускает VPN через Mihomo. В приложении доступна оплата картой или СБП: для авторизованного пользователя API создаёт ссылку YooKassa, а после успешной оплаты бот обновляет подписку.

- Репозиторий: CosmoNet-App
- Версия: `0.2.25`
- API приложения: авторизация, подписка, обратная связь, обновления и YooKassa

## Тесты

```bash
python -B -m unittest discover -s tests -v
```

Тесты покрывают тарифы, пробный период, Telegram Stars, YooKassa, защиту от повторной обработки платежей, выдачу и продление через 3X-UI, API приложения, обратную связь, рассылки и права администратора.

## Безопасность

- храните токены и секреты только в `.env` или защищённом хранилище;
- используйте HTTPS для панели 3X-UI, API и публичных webhook;
- ограничьте сетевой доступ к 3X-UI и внутреннему API;
- регулярно создавайте резервные копии SQLite и конфигурации панели;
- перед обновлением платёжного сценария проверяйте его в тестовом окружении.
