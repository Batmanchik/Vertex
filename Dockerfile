FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLBACKEND=Agg

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# pages/ и app.py были интерфейсом на Streamlit. Витрина переехала на ту же
# страницу, что отдаёт API, и обеих строк здесь больше нет.
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY scripts ./scripts
COPY docs ./docs
# artifacts/ не копируется: docker-compose монтирует каталог томом, чтобы
# пересчитанный прогон подхватывался без пересборки образа.

RUN python -m pip install --upgrade pip \
    && python -m pip install .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "apris.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
