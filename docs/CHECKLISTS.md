# Проверки: перед выпуском и при ручном ревью

> **Что это:** два списка проверок в одном файле. Первый прогоняется перед
> выпуском, второй — руками, для того, что не ловится гейтами.
> План работ — [../PLAN.md](../PLAN.md).

---

# I. Перед выпуском

## Pre-release Quality Gates
- `python -m ruff check src tests pages app.py`
- `python -m mypy`
- `python -m pytest --cov=src/apris`
- `python -m bandit -q -r src/apris -x src/apris/crypto_ponzi -s B101`
- `python -m radon cc src/apris/cheops -s -n B`
- `lint-imports`

## Runtime Smoke
- `scripts/app.ps1 start`
- `scripts/app.ps1 status`
- `scripts/app.ps1 open`
- `scripts/app.ps1 stop`
- `scripts/app.ps1 status`

## Container Smoke
- `docker compose up -d --build`
- `docker compose ps`
- `curl http://127.0.0.1:8000/api/v1/health`
- `curl http://127.0.0.1:8501/_stcore/health`
- `docker compose down -v`

## User Scenario Smoke
- Scanner batch run (synthetic mode)
- Scanner API-down path shows actionable message and retry button
- Dashboard opens and displays risk rows
- Manual check page scores a case and renders explanation
- API endpoints healthy: `/api/v1/health`, `/api/v2/health/model`, `/api/v2/health/runtime`

## Regression Notes
- v1 endpoints must remain available without payload/response breaking changes.
- UI scanner must use API batch path (`/api/v2/score/batch`) and must not call model inference directly.
- `CHEOPS_API_BASE_URL` and `CHEOPS_API_TIMEOUT` must be honored by frontend API client.

---

# II. Ручное ревью

Используется для критичных модулей: `domain`, `risk scoring`, `etl`, `api contracts`.

## 1) Domain Invariants
- Все инварианты явно проверяются и тестируются.
- Ошибки валидации возвращают понятные причины.
- Нет неявных fallback, скрывающих поврежденные входные данные.

## 2) API Contract Integrity
- Request/response схемы версионированы.
- Изменения контрактов сопровождаются миграционной заметкой.
- Ошибки 4xx/5xx разделены корректно.

## 3) ML/Scoring Correctness
- Нет leakage между train/val/test.
- Калибровка не ломает ranking по high-risk кейсам.
- Fallback поведение детерминировано и наблюдаемо.

## 4) Code Quality
- Функции > 40 строк обоснованы или декомпозированы.
- Нет дублирования бизнес-логики между слоями.
- Исключения поднимаются с сохранением контекста.

## 5) Architecture Purity
- Слои не нарушены (проверка import-linter + ручная проверка PR diff).
- Interface слой не содержит бизнес-логику.
- Application слой не зависит от конкретного web framework.

## 6) Reliability & Observability
- Health-check и error-pathы покрыты тестами.
- Ключевые операции имеют структурируемые логи.
- Для деградаций задана стратегия (retry/fallback/abort) и она протестирована.
