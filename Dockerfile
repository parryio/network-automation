FROM python:3.11-slim AS build
WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --prefix=/install -r requirements.txt

FROM python:3.11-slim AS runtime
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=build /install /usr/local
COPY . .
EXPOSE 8501
CMD ["streamlit", "run", "ui/app.py", "--", "--alarms", "demo/alarms/*.json", "--out", "outputs"]
