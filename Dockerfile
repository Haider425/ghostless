FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY pyproject.toml README.md LICENSE ./
COPY tracker ./tracker
RUN pip install --no-cache-dir .

COPY companies.yaml ./

RUN useradd --create-home tracker
USER tracker

ENTRYPOINT ["jobtracker"]
CMD ["verify"]
